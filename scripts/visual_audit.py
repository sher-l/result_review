#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Prepare Layer 2 visual audit assets with machine prescreen support."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PureWindowsPath

from audit_runtime import append_event, infer_project_id, load_case_manifest, stable_hash, write_json
from policy_loader import load_policy

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_PIL = False

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_TESSERACT = False


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
VISUAL_REVIEWABLE_EXTS = IMAGE_EXTS | {".pdf", ".svg"}
VISUAL_RESULT_SCHEMA_VERSION = "1.0"
FONT_MISMATCH_MIN_BLOCKS = 4
HIGH_RISK_TYPES = {
    "single_cell",
    "umap_tsne",
    "survival_km",
    "roc",
    "nomogram",
    "docking",
    "clinical_subgroup",
    "ihc",
    "cnv_mutation",
}
COMMON_CHECKS = [
    "Image is readable and not truncated/corrupted",
    "Title/subtitle matches this project and section context",
    "Axes or labels are present and legible",
    "Legend/annotation matches the claimed groups or entities",
]
TYPE_SPECIFIC_CHECKS = {
    "volcano": [
        "Threshold guides and direction of up/down regulation are plausible",
        "Highlighted genes match the report text",
    ],
    "heatmap": [
        "Color direction and clustering presentation are plausible",
        "Gene/sample labels are consistent with the report text",
    ],
    "survival_km": [
        "Group labels and p-value are visible",
        "Curve direction matches the written conclusion",
    ],
    "roc": [
        "AUC label is visible and matches the written claim",
        "Diagonal reference line is present",
    ],
    "umap_tsne": [
        "Cluster labels are legible",
        "Reported cell types and cluster counts look consistent",
    ],
    "boxplot_violin": [
        "Group labels are correct",
        "Significance annotations match the written claim",
    ],
    "nomogram": [
        "Variables and scales are legible",
        "Calibration or validation panel exists when claimed",
    ],
    "docking": [
        "Protein/ligand labels are present",
        "Binding score or energy annotation exists when claimed",
    ],
    "single_cell": [
        "Cell type labels and panel titles are consistent",
        "QC-before/QC-after panels are not obviously reused",
    ],
}
TYPE_KEYWORDS = {
    "volcano": ["volcano", "logfc", "difference", "差异", "火山"],
    "heatmap": ["heatmap", "热图", "cluster heatmap"],
    "venn": ["venn", "韦恩"],
    "ppi": ["ppi", "string", "network"],
    "gsea": ["gsea", "enrichment score", "富集"],
    "kegg_go": ["kegg", "go ", "pathway", "enrichment", "通路", "功能"],
    "survival_km": ["kaplan", "survival", "km", "生存", "预后"],
    "roc": ["roc", "auc"],
    "umap_tsne": ["umap", "tsne", "t-sne"],
    "forest": ["forest", "hazard", "hr", "or"],
    "nomogram": ["nomogram", "列线图", "calibration"],
    "boxplot_violin": ["boxplot", "violin", "箱线", "小提琴"],
    "clinical_subgroup": ["clinical", "stage", "grade", "subgroup", "年龄", "分期", "分组"],
    "expression": ["expression", "表达"],
    "correlation": ["correlation", "corr", "相关"],
    "network": ["network", "interaction"],
    "docking": ["docking", "对接", "binding"],
    "flowchart": ["flowchart", "workflow", "流程"],
    "pca_oplsda": ["pca", "opls", "score plot"],
    "bar_chart": ["bar", "柱状"],
    "scatter": ["scatter", "散点"],
    "immune": ["immune", "cibersort", "ssgsea", "免疫"],
    "methylation": ["methylation", "甲基化"],
    "wgcna": ["wgcna", "共表达"],
    "drug": ["drug", "药物", "cmap"],
    "single_cell": ["single cell", "scrna", "单细胞", "cluster"],
    "lasso": ["lasso", "random forest", "随机森林"],
    "ihc": ["ihc", "immunohistochem", "免疫组化", "染色"],
    "cnv_mutation": ["mutation", "cnv", "copy number", "突变"],
    "cell_communication": ["cellchat", "cell communication", "细胞通讯"],
    "trajectory": ["trajectory", "pseudotime", "monocle", "拟时序"],
}


def default_review_lane() -> str:
    lane = str(load_policy().get("review_lane_policy", {}).get("default_lane", "strict"))
    return lane if lane in {"standard", "strict"} else "strict"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Layer 2 visual audit artifacts.")
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument("--project-dir", help="Optional raw project directory", default=None)
    parser.add_argument(
        "--review-lane",
        choices=("standard", "strict"),
        default=default_review_lane(),
        help="standard: review only flagged/high-risk figures; strict: review all figures",
    )
    return parser.parse_args()


def discover_images(review_dir: Path) -> list[dict]:
    images_dir = review_dir / "images"
    if not images_dir.exists():
        return []

    images = []
    for path in sorted(images_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            images.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "ext": path.suffix.lower(),
                }
            )
    return images


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def map_images_to_context(review_dir: Path, images: list[dict]) -> list[dict]:
    report_text_path = review_dir / "report_text.txt"
    if not report_text_path.exists():
        for image in images:
            image.setdefault("report_refs", [])
            image.setdefault("section", "")
            image.setdefault("caption_context", "")
            image.setdefault("figure_id", "")
            image.setdefault("is_cover", False)
        return images

    lines = report_text_path.read_text(encoding="utf-8").splitlines()
    sections = []
    structure_path = review_dir / "report_structure.json"
    if structure_path.exists():
        try:
            sections = json.loads(structure_path.read_text(encoding="utf-8")).get("sections", [])
        except json.JSONDecodeError:
            sections = []

    def get_section(line_num: int) -> str:
        current = ""
        for section in sections:
            if isinstance(section, dict) and section.get("line", 0) <= line_num:
                section_id = section.get("id", "?")
                title = section.get("title", "")
                current = f"{section_id} {title}".strip()
        return current

    cover_end_line = 0
    for idx, line in enumerate(lines[:30], start=1):
        if re.search(r"\d{2}[A-Z]{3}\d{3}[A-Z]?\b", line):
            cover_end_line = max(cover_end_line, idx + 3)
        if re.search(r"研究方向|项目编号|单号", line):
            cover_end_line = max(cover_end_line, idx + 3)

    image_pattern = re.compile(r"\[IMAGE:\s*([^\]]+)\]")
    figure_pattern = re.compile(
        r"(Fig(?:ure)?\.?\s*\d+(?:[.\-]\d+)?|图\s*\d+(?:[.\-]\d+)?)",
        re.IGNORECASE,
    )

    for image in images:
        image["report_refs"] = []
        image["section"] = ""
        image["caption_context"] = ""
        image["figure_id"] = ""
        image["is_cover"] = False

    for line_idx, line in enumerate(lines, start=1):
        for match in image_pattern.finditer(line):
            img_name = match.group(1).strip()
            target = next(
                (
                    image
                    for image in images
                    if image["filename"] == img_name
                    and image.get("origin", "report_embedded_assets") == "report_embedded_assets"
                ),
                None,
            )
            if target is None:
                continue

            ctx_start = max(0, line_idx - 4)
            ctx_end = min(len(lines), line_idx + 3)
            context_lines = lines[ctx_start:ctx_end]
            context = "\n".join(context_lines)
            caption = ""
            figure_id = ""
            nearby_candidates = []
            for nearby_idx in range(max(1, line_idx - 2), min(len(lines), line_idx + 3) + 1):
                nearby_line = lines[nearby_idx - 1]
                fig_match = figure_pattern.search(nearby_line)
                if fig_match:
                    nearby_candidates.append((abs(nearby_idx - line_idx), nearby_idx, fig_match.group(1).strip(), nearby_line))
            if nearby_candidates:
                _, _, figure_id, caption_line = sorted(nearby_candidates, key=lambda item: (item[0], item[1]))[0]
                caption = caption_line.strip()[:200]

            target["report_refs"].append({"line": line_idx, "context": context[:500]})
            if line_idx <= cover_end_line:
                target["is_cover"] = True
            if not target["section"]:
                target["section"] = get_section(line_idx)
            if not target["caption_context"] and caption:
                target["caption_context"] = caption
            if not target["figure_id"] and figure_id:
                target["figure_id"] = figure_id

    return images


def classify_image_type(image: dict) -> str:
    if image.get("is_cover"):
        return "cover_decoration"

    context = " ".join(
        [
            image.get("caption_context", ""),
            image.get("section", ""),
            image.get("filename", ""),
        ]
    ).lower()

    for image_type, keywords in TYPE_KEYWORDS.items():
        if any(keyword in context for keyword in keywords):
            return image_type
    return "unknown"


def _asset_record(path: Path, *, origin: str, relative_path: str, recognized_unsupported: set[str]) -> dict:
    suffix = path.suffix.lower()
    probe = {
        "filename": path.name,
        "caption_context": relative_path,
        "section": "",
        "is_cover": False,
    }
    guessed_type = classify_image_type(probe)
    try:
        source_hash = sha256_file(path)
        size_bytes = path.stat().st_size
    except OSError:
        source_hash = ""
        size_bytes = 0
    return {
        "asset_id": f"va:{stable_hash([origin, relative_path], length=16)}",
        "origin": origin,
        "filename": path.name,
        "relative_path": relative_path.replace("\\", "/"),
        "path": str(path),
        "ext": suffix,
        "size_bytes": size_bytes,
        "source_sha256": source_hash,
        "format_status": "supported" if suffix in VISUAL_REVIEWABLE_EXTS else "unsupported",
        "recognized_unsupported": suffix in recognized_unsupported,
        "guessed_type": guessed_type,
        "high_risk": guessed_type in HIGH_RISK_TYPES,
    }


def _project_root(review_dir: Path, project_dir: Path | None = None) -> Path | None:
    configured_root = project_dir
    case_manifest = load_case_manifest(review_dir)
    project_structure = case_manifest
    if configured_root is None:
        structure_path = review_dir / "project_structure.json"
        if structure_path.exists():
            try:
                project_structure = json.loads(structure_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                project_structure = {}
        configured = project_structure.get("metadata", {}).get("project_dir")
        if not configured:
            configured = load_case_manifest(review_dir).get("project_dir")
        configured_root = Path(configured) if configured else None
    if configured_root is not None and configured_root.is_dir():
        return configured_root

    # Archiving moves the project package but preserves its path below the
    # project-id container. Re-resolve that exact relative suffix from the
    # manifest-owned archive destination rather than treating the old visual
    # inventory as stale.
    archived_to = str(case_manifest.get("archived_to", "")).strip()
    if configured_root is None or not archived_to:
        return configured_root
    archive_root = Path(archived_to)
    if not archive_root.is_dir():
        return configured_root
    if archive_root.name == configured_root.name:
        return archive_root
    for parent in (configured_root, *configured_root.parents):
        if parent.name != review_dir.name:
            continue
        try:
            archived_project = archive_root / configured_root.relative_to(parent)
        except ValueError:
            continue
        if archived_project.is_dir():
            return archived_project
    return configured_root


def _resolve_project_visual_path(project_root: Path, raw_path: object) -> tuple[Path, str]:
    """Resolve one declared delivery figure without allowing it to leave project_root."""
    relative_path = str(raw_path).replace("\\", "/")
    declared_path = Path(relative_path)
    if declared_path.is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise ValueError(f"visual inventory path must be relative to project directory: {relative_path}")
    resolved_root = project_root.resolve()
    candidate = (resolved_root / declared_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"visual inventory path escapes project directory: {relative_path}") from exc
    return candidate, relative_path


def discover_visual_assets(review_dir: Path, project_dir: Path | None = None) -> list[dict]:
    """Inventory report assets and all project delivery figures.

    Delivery traversal is bounded by the already generated project_structure image
    list; this function never recursively walks a project tree. Risk classification
    decides the checks, not whether a delivered figure enters the conserved inventory.
    """

    policy = load_policy().get("visual_closure_policy", {})
    recognized_unsupported = {
        str(item).lower() for item in policy.get("recognized_unsupported_formats", [".emf", ".wmf"])
    }
    assets: list[dict] = []
    seen_paths: set[str] = set()

    images_dir = review_dir / "images"
    if images_dir.exists():
        for path in sorted(images_dir.iterdir()):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            seen_paths.add(resolved)
            assets.append(
                _asset_record(
                    path,
                    origin="report_embedded_assets",
                    relative_path=f"images/{path.name}",
                    recognized_unsupported=recognized_unsupported,
                )
            )

    structure_path = review_dir / "project_structure.json"
    root = _project_root(review_dir, project_dir)
    if structure_path.exists() and root is not None:
        try:
            structure = json.loads(structure_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            structure = {}
        for item in structure.get("image_files", []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            path, relative_path = _resolve_project_visual_path(root, item["path"])
            guessed_type = classify_image_type(
                {"filename": Path(relative_path).name, "caption_context": relative_path, "section": ""}
            )
            if not path.is_file() or str(path.resolve()) in seen_paths:
                continue
            seen_paths.add(str(path.resolve()))
            asset = _asset_record(
                path,
                origin="project_delivery_figures",
                relative_path=relative_path,
                recognized_unsupported=recognized_unsupported,
            )
            asset["guessed_type"] = guessed_type
            asset["high_risk"] = guessed_type in HIGH_RISK_TYPES
            assets.append(asset)

    return sorted(assets, key=lambda item: (item["origin"], item["relative_path"]))


def get_checks_for_type(image_type: str) -> list[str]:
    return COMMON_CHECKS + TYPE_SPECIFIC_CHECKS.get(image_type, [])


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def extract_image_text(image_path: Path) -> str:
    if not (_HAS_PIL and _HAS_TESSERACT):
        return ""
    try:  # pragma: no cover - OCR dependency varies by machine
        with Image.open(image_path) as image:
            text = pytesseract.image_to_string(image, lang="eng")
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def extract_text_blocks(image_path: Path) -> list[dict]:
    if not (_HAS_PIL and _HAS_TESSERACT):
        return []
    try:  # pragma: no cover - OCR dependency varies by machine
        with Image.open(image_path) as image:
            data = pytesseract.image_to_data(image, lang="eng", output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    blocks = []
    total = len(data.get("text", []))
    for index in range(total):
        raw_text = str(data["text"][index]).strip()
        normalized = re.sub(r"\s+", " ", raw_text)
        if len(re.sub(r"[^A-Za-z0-9]", "", normalized)) < 2:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 40:
            continue
        width = int(data["width"][index])
        height = int(data["height"][index])
        if width <= 0 or height <= 0:
            continue
        blocks.append(
            {
                "text": normalized,
                "conf": confidence,
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": width,
                "height": height,
                "area": width * height,
            }
        )
    return blocks


def _font_style_vector(image: "Image.Image", block: dict) -> tuple[float, float, float] | None:
    left = max(int(block["left"]) - 1, 0)
    top = max(int(block["top"]) - 1, 0)
    right = min(left + int(block["width"]) + 2, image.width)
    bottom = min(top + int(block["height"]) + 2, image.height)
    if right <= left or bottom <= top:
        return None

    crop = image.crop((left, top, right, bottom)).convert("L")
    pixels = list(crop.getdata())
    total = max(len(pixels), 1)
    ink = [1 if pixel < 190 else 0 for pixel in pixels]
    fill_ratio = sum(ink) / total
    if fill_ratio <= 0.01:
        return None

    width = crop.width
    height = crop.height
    edge_count = 0
    for y in range(height):
        row_start = y * width
        for x in range(width - 1):
            edge_count += abs(ink[row_start + x] - ink[row_start + x + 1])
    for y in range(height - 1):
        row_start = y * width
        next_row = (y + 1) * width
        for x in range(width):
            edge_count += abs(ink[row_start + x] - ink[next_row + x])

    edge_density = edge_count / total
    aspect_ratio = width / max(height, 1)
    return (round(aspect_ratio, 4), round(fill_ratio, 4), round(edge_density, 4))


def detect_font_style_mismatch(image_path: Path) -> dict:
    if not (_HAS_PIL and _HAS_TESSERACT):
        return {"detected": False, "reason": "ocr_unavailable"}

    blocks = extract_text_blocks(image_path)
    if len(blocks) < FONT_MISMATCH_MIN_BLOCKS:
        return {"detected": False, "reason": "insufficient_text_blocks", "count": len(blocks)}

    heights = sorted(block["height"] for block in blocks)
    median_height = heights[len(heights) // 2]
    comparable_blocks = [
        block
        for block in blocks
        if median_height * 0.7 <= block["height"] <= median_height * 1.45
    ]
    if len(comparable_blocks) < FONT_MISMATCH_MIN_BLOCKS:
        return {"detected": False, "reason": "insufficient_comparable_blocks", "count": len(comparable_blocks)}

    try:  # pragma: no cover - image decoding varies by machine
        with Image.open(image_path) as image:
            vectors = []
            for block in comparable_blocks:
                vector = _font_style_vector(image, block)
                if vector is None:
                    continue
                vectors.append({"block": block, "vector": vector})
    except Exception:
        return {"detected": False, "reason": "image_open_failed"}

    if len(vectors) < FONT_MISMATCH_MIN_BLOCKS:
        return {"detected": False, "reason": "insufficient_vectors", "count": len(vectors)}

    clusters: list[list[dict]] = []
    threshold = 0.18
    for item in vectors:
        assigned = False
        for cluster in clusters:
            centroid = tuple(sum(member["vector"][i] for member in cluster) / len(cluster) for i in range(3))
            distance = math.sqrt(sum((item["vector"][i] - centroid[i]) ** 2 for i in range(3)))
            if distance <= threshold:
                cluster.append(item)
                assigned = True
                break
        if not assigned:
            clusters.append([item])

    cluster_sizes = sorted((len(cluster) for cluster in clusters), reverse=True)
    if len(cluster_sizes) < 2:
        return {"detected": False, "reason": "single_style_cluster", "count": len(vectors)}

    dominant = cluster_sizes[0]
    secondary = cluster_sizes[1]
    if secondary < 2 or secondary / len(vectors) < 0.25:
        return {"detected": False, "reason": "secondary_cluster_too_small", "clusters": cluster_sizes}

    sample_texts = []
    for cluster in sorted(clusters, key=len, reverse=True)[:2]:
        sample_texts.append([member["block"]["text"] for member in cluster[:3]])
    return {
        "detected": True,
        "reason": "multiple_font_style_clusters",
        "clusters": cluster_sizes,
        "sample_texts": sample_texts,
    }


def predict_visual_family(image_path: Path) -> str:
    if not _HAS_PIL:
        return "unknown"
    try:
        with Image.open(image_path) as image:
            pixels = list(image.convert("RGB").resize((96, 96)).getdata())
    except Exception:
        return "unknown"

    total = max(len(pixels), 1)
    white_ratio = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235) / total
    dark_ratio = sum(1 for r, g, b in pixels if r < 40 and g < 40 and b < 40) / total
    unique_colors = len(set(pixels))
    if white_ratio > 0.90 and dark_ratio > 0.02 and unique_colors < 64:
        return "text_page"
    if unique_colors > 256 and white_ratio < 0.70:
        return "heatmap_like"
    if white_ratio > 0.55:
        return "chart_like"
    return "other"


def expected_visual_family(image_type: str) -> str:
    mapping = {
        "heatmap": "heatmap_like",
        "kegg_go": "chart_like",
        "gsea": "chart_like",
        "volcano": "chart_like",
        "roc": "chart_like",
        "forest": "chart_like",
        "umap_tsne": "chart_like",
        "boxplot_violin": "chart_like",
        "nomogram": "chart_like",
        "flowchart": "chart_like",
        "network": "chart_like",
        "single_cell": "chart_like",
    }
    return mapping.get(image_type, "unknown")


def run_visual_prefilter(review_dir: Path, images: list[dict]) -> dict:
    case_manifest = load_case_manifest(review_dir)
    current_project_id = case_manifest.get("project_id") or infer_project_id(review_dir)
    foreign_ids = set(case_manifest.get("foreign_project_ids", []))
    image_flags = {}
    exact_hashes: dict[str, str] = {}

    for image in images:
        path = Path(image["path"])
        flags = []
        sha1 = ""
        try:
            sha1 = sha1_file(path)
        except OSError:
            pass
        if sha1:
            if sha1 in exact_hashes:
                flags.append(
                    {
                        "type": "duplicate_image",
                        "severity": "CRITICAL",
                        "message": f"Exact duplicate of {exact_hashes[sha1]}",
                    }
                )
            else:
                exact_hashes[sha1] = image["filename"]

        ocr_text = extract_image_text(path)
        if ocr_text:
            project_ids = set(re.findall(r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b", ocr_text))
            foreign_hit = sorted((project_ids | foreign_ids) - ({current_project_id} if current_project_id else set()))
            if foreign_hit:
                flags.append(
                    {
                        "type": "project_id_mismatch",
                        "severity": "CRITICAL",
                        "message": f"OCR contains foreign project id(s): {', '.join(foreign_hit)}",
                    }
                )

        predicted = predict_visual_family(path)
        expected = expected_visual_family(image.get("guessed_type", "unknown"))
        if expected != "unknown" and predicted == "text_page":
            flags.append(
                {
                    "type": "obvious_wrong_figure",
                    "severity": "MAJOR",
                    "message": f"Expected {expected}, but image looks like a text page",
                }
            )

        font_mismatch = detect_font_style_mismatch(path)
        if font_mismatch.get("detected"):
            cluster_summary = ",".join(str(item) for item in font_mismatch.get("clusters", []))
            flags.append(
                {
                    "type": "font_style_mismatch",
                    "severity": "WARNING",
                    "message": f"Likely inconsistent font styles detected (clusters={cluster_summary})",
                }
            )

        image_key = image.get("asset_id") or image["filename"]
        image_flags[image_key] = {
            "asset_id": image.get("asset_id", ""),
            "filename": image["filename"],
            "ocr_text": ocr_text[:200],
            "predicted_family": predicted,
            "font_analysis": font_mismatch,
            "flags": flags,
        }

    summary = {
        "total_images": len(images),
        "flagged_images": sum(1 for item in image_flags.values() if item["flags"]),
        "duplicate_image": sum(
            1 for item in image_flags.values() if any(flag["type"] == "duplicate_image" for flag in item["flags"])
        ),
        "project_id_mismatch": sum(
            1 for item in image_flags.values() if any(flag["type"] == "project_id_mismatch" for flag in item["flags"])
        ),
        "obvious_wrong_figure": sum(
            1 for item in image_flags.values() if any(flag["type"] == "obvious_wrong_figure" for flag in item["flags"])
        ),
        "font_style_mismatch": sum(
            1 for item in image_flags.values() if any(flag["type"] == "font_style_mismatch" for flag in item["flags"])
        ),
    }
    return {"summary": summary, "images": image_flags}


def generate_checklist(images: list[dict], review_lane: str, visual_prefilter: dict) -> list[dict]:
    checklist = []
    flagged_lookup = visual_prefilter.get("images", {})

    for index, image in enumerate(images, start=1):
        image_type = classify_image_type(image)
        image["guessed_type"] = image_type
        image_key = image.get("asset_id") or image["filename"]
        prefetched = flagged_lookup.get(image_key, flagged_lookup.get(image["filename"], {}))
        flags = prefetched.get("flags", [])
        skip_reason = ""
        needs_audit = True

        if image_type == "cover_decoration":
            needs_audit = False
            skip_reason = "Cover decoration or logo"
        elif review_lane == "standard" and image["size_bytes"] < 2000:
            needs_audit = False
            skip_reason = f"Very small asset ({image['size_bytes']}B)"
        elif review_lane == "standard" and not flags and image_type not in HIGH_RISK_TYPES:
            needs_audit = False
            skip_reason = "Standard lane: low-risk image without machine flags"

        checklist.append(
            {
                "index": index,
                "asset_id": image.get("asset_id", ""),
                "origin": image.get("origin", "report_embedded_assets"),
                "filename": image["filename"],
                "path": image["path"],
                "size_bytes": image["size_bytes"],
                "figure_id": image.get("figure_id", ""),
                "section": image.get("section", ""),
                "caption": image.get("caption_context", ""),
                "guessed_type": image_type,
                "needs_audit": needs_audit,
                "review_lane": review_lane,
                "machine_flags": flags,
                "machine_prefilter": prefetched,
                "report_refs": image.get("report_refs", []),
                "checks": get_checks_for_type(image_type),
                "skip_reason": skip_reason,
            }
        )
    return checklist


def generate_figure_audit_template(checklist: list[dict], review_dir: Path, visual_prefilter: dict, review_lane: str) -> str:
    project_id = infer_project_id(review_dir)
    total = len(checklist)
    to_audit = sum(1 for item in checklist if item["needs_audit"])
    skipped = total - to_audit
    summary = visual_prefilter.get("summary", {})

    lines = [
        "# Layer 2 Visual Audit",
        "",
        f"**Project**: {project_id}",
        f"**Generated At**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Review Lane**: {review_lane}",
        "",
        "## Scope",
        "",
        f"- Total images: {total}",
        f"- Human review required: {to_audit}",
        f"- Skipped by lane/filter: {skipped}",
        f"- Machine-flagged images: {summary.get('flagged_images', 0)}",
        f"- Duplicate-image alerts: {summary.get('duplicate_image', 0)}",
        f"- Project-id mismatch alerts: {summary.get('project_id_mismatch', 0)}",
        f"- Obvious wrong-figure alerts: {summary.get('obvious_wrong_figure', 0)}",
        f"- Font-style mismatch alerts: {summary.get('font_style_mismatch', 0)}",
        "",
        "## Machine Prescreen Summary",
        "",
        f"- Prescreen file: `visual_prefilter.json`",
        "- Standard lane: only machine-flagged or high-risk figures require human review.",
        "- Strict lane: every non-decoration figure requires human review.",
        "",
        "## Figure Review Log",
        "",
    ]

    for item in checklist:
        lines.append(f"### #{item['index']}: {item['filename']}")
        lines.append("")
        if not item["needs_audit"]:
            lines.append(f"- Status: skipped")
            lines.append(f"- Reason: {item.get('skip_reason', '-')}")
            lines.append("")
            continue

        lines.append(f"- Figure ID: {item.get('figure_id') or '-'}")
        lines.append(f"- Section: {item.get('section') or '-'}")
        lines.append(f"- Guessed Type: {item.get('guessed_type') or 'unknown'}")
        lines.append(f"- Caption Context: {item.get('caption') or '-'}")
        if item["machine_flags"]:
            lines.append("- Machine Flags:")
            for flag in item["machine_flags"]:
                lines.append(f"  - [{flag['severity']}] {flag['type']}: {flag['message']}")
        else:
            lines.append("- Machine Flags: none")
        lines.append("")
        lines.append("| Check | Result | Notes |")
        lines.append("|---|---|---|")
        for check in item["checks"]:
            lines.append(f"| {check} | TODO | |")
        lines.append("")
        lines.append("- Finding: TODO")
        lines.append("- Severity: TODO")
        lines.append("")

    return "\n".join(lines)


def _initial_derivative_evidence(asset: dict, inventory: list[dict]) -> dict:
    source_stem = Path(asset["relative_path"]).stem.lower()
    candidate = next(
        (
            item
            for item in inventory
            if item["asset_id"] != asset["asset_id"]
            and item["origin"] == asset["origin"]
            and item["format_status"] == "supported"
            and Path(item["relative_path"]).stem.lower() == source_stem
        ),
        None,
    )
    if candidate is None:
        return {}
    return {
        "derivative_asset_id": candidate["asset_id"],
        "source_sha256": asset["source_sha256"],
        "derivative_sha256": candidate["source_sha256"],
        "review_status": "pending",
        "reviewed_by": "",
        "reviewed_at": "",
    }


def build_visual_audit_result(
    review_dir: Path,
    inventory: list[dict],
    checklist: list[dict],
    review_lane: str,
) -> dict:
    checklist_by_id = {item.get("asset_id"): item for item in checklist if item.get("asset_id")}
    result_assets = []
    for asset in inventory:
        checklist_item = checklist_by_id.get(asset["asset_id"], {})
        supported = asset["format_status"] == "supported"
        needs_audit = bool(checklist_item.get("needs_audit", asset.get("high_risk", False)))
        if supported and not needs_audit:
            outcome = "skipped"
            reason = checklist_item.get("skip_reason") or "Policy-approved low-risk visual skip"
        elif supported:
            outcome = "pending"
            reason = ""
        else:
            outcome = "unsupported"
            reason = f"Unsupported source format: {asset['ext'] or '[no extension]'}"

        result_assets.append(
            {
                **asset,
                "needs_audit": needs_audit,
                "machine_flags": checklist_item.get("machine_flags", []),
                "outcome": outcome,
                "reason": reason,
                "review": {
                    "status": "pending" if needs_audit and supported else "not_required",
                    "reviewer": "",
                    "completed_at": "",
                    "conclusion": "",
                },
                "waiver": {},
                "derivative_evidence": _initial_derivative_evidence(asset, inventory)
                if not supported
                else {},
                "alternative_evidence": {},
            }
        )

    counts = Counter(item["outcome"] for item in result_assets)
    asset_counts = {
        "asset_total": len(result_assets),
        "reviewed": counts.get("reviewed", 0),
        "skipped": counts.get("skipped", 0),
        "unsupported": counts.get("unsupported", 0),
        "unaccounted": counts.get("pending", 0),
    }
    return {
        "schema_version": VISUAL_RESULT_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "project_id": infer_project_id(review_dir),
        "review_lane": review_lane,
        "policy_mode": load_policy().get("visual_closure_policy", {}).get("mode", "enforce"),
        "status": "skipped" if not result_assets else "prepared",
        "passed": not result_assets,
        "asset_counts": asset_counts,
        "conservation": {
            "invariant": "asset_total=reviewed+skipped+unsupported",
            "passed": not result_assets,
        },
        "assets": result_assets,
        "validation_errors": [] if not result_assets else ["human visual review is not complete"],
    }


def _valid_waiver(waiver: object) -> bool:
    return isinstance(waiver, dict) and all(
        str(waiver.get(field, "")).strip() for field in ("reason", "approved_by", "approved_at")
    )


def _valid_alternative_evidence(evidence: object) -> bool:
    return isinstance(evidence, dict) and all(
        str(evidence.get(field, "")).strip()
        for field in ("type", "reference", "reason", "reviewed_by", "reviewed_at")
    )


def _validate_derivative_evidence(
    review_dir: Path,
    source_asset: dict,
    evidence: object,
    current_by_id: dict[str, dict],
) -> tuple[bool, str]:
    if not isinstance(evidence, dict) or not evidence:
        return False, "derivative evidence is missing"
    if evidence.get("source_sha256") != source_asset.get("source_sha256"):
        return False, "derivative evidence source hash is stale"
    if evidence.get("review_status") != "completed":
        return False, "derivative evidence has not been reviewed"
    if not str(evidence.get("reviewed_by", "")).strip() or not str(evidence.get("reviewed_at", "")).strip():
        return False, "derivative review identity or timestamp is missing"

    derivative_id = str(evidence.get("derivative_asset_id", "")).strip()
    if derivative_id:
        derivative = current_by_id.get(derivative_id)
        if derivative is None:
            return False, "derivative asset is not in the conserved inventory"
        actual_hash = derivative.get("source_sha256", "")
    else:
        raw_path = str(evidence.get("path") or evidence.get("derivative_path") or "").strip()
        if not raw_path:
            return False, "derivative path or asset id is missing"
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = review_dir / candidate
        if not candidate.is_file():
            return False, "derivative file does not exist"
        actual_hash = sha256_file(candidate)
    if not actual_hash or evidence.get("derivative_sha256") != actual_hash:
        return False, "derivative evidence hash is stale"
    return True, ""


def validate_visual_audit_result(review_dir: Path, result: dict, policy: dict | None = None) -> dict:
    closure_policy = (policy or load_policy()).get("visual_closure_policy", {})
    errors: list[dict] = []

    def add_error(error_id: str, message: str, asset_id: str = "") -> None:
        errors.append({"id": error_id, "message": message, "asset_id": asset_id})

    if result.get("schema_version") != VISUAL_RESULT_SCHEMA_VERSION:
        add_error("visual_closure:schema", f"Expected schema {VISUAL_RESULT_SCHEMA_VERSION}.")
    if result.get("project_id") != infer_project_id(review_dir):
        add_error("visual_closure:project_id", "Visual result project id does not match the review directory.")
    if result.get("status") not in {"completed", "skipped"}:
        add_error("visual_closure:status", "Visual result status must be completed or skipped.")

    current_inventory = discover_visual_assets(review_dir)
    strict_lane = result.get("review_lane") == "strict"
    contextualized = map_images_to_context(
        review_dir, [dict(item) for item in current_inventory if item["format_status"] == "supported"]
    )
    contextualized_by_id = {item["asset_id"]: item for item in contextualized}
    for item in current_inventory:
        contextual = contextualized_by_id.get(item["asset_id"])
        if contextual:
            item["guessed_type"] = classify_image_type(contextual)
            item["high_risk"] = item["guessed_type"] in HIGH_RISK_TYPES
    current_by_id = {item["asset_id"]: item for item in current_inventory}
    recorded_assets = result.get("assets", []) if isinstance(result.get("assets"), list) else []
    recorded_by_id: dict[str, dict] = {}
    for item in recorded_assets:
        asset_id = str(item.get("asset_id", "")).strip() if isinstance(item, dict) else ""
        if not asset_id or asset_id in recorded_by_id:
            add_error("visual_closure:asset_id", "Every asset must have a unique asset_id.", asset_id)
            continue
        recorded_by_id[asset_id] = item

    missing_ids = sorted(set(current_by_id) - set(recorded_by_id))
    extra_ids = sorted(set(recorded_by_id) - set(current_by_id))
    if missing_ids:
        add_error("visual_closure:inventory_missing", f"Missing current assets: {', '.join(missing_ids)}")
    if extra_ids:
        add_error("visual_closure:inventory_extra", f"Stale or extra assets: {', '.join(extra_ids)}")

    actual_counts = Counter()
    for asset_id, item in recorded_by_id.items():
        current = current_by_id.get(asset_id)
        if current is None:
            continue
        if not current.get("source_sha256") or item.get("source_sha256") != current.get("source_sha256"):
            add_error("visual_closure:source_hash", "Source asset hash is missing or stale.", asset_id)
        outcome = str(item.get("outcome", "")).strip()
        if outcome in {"reviewed", "skipped", "unsupported"}:
            actual_counts[outcome] += 1
        else:
            actual_counts["unaccounted"] += 1

        if current["format_status"] == "supported":
            if outcome == "reviewed":
                review = item.get("review", {})
                if not isinstance(review, dict) or review.get("status") != "completed" or not all(
                    str(review.get(field, "")).strip()
                    for field in ("reviewer", "completed_at", "conclusion")
                ):
                    add_error("visual_closure:review_evidence", "Completed human review evidence is incomplete.", asset_id)
            elif outcome == "skipped":
                if not str(item.get("reason", "")).strip():
                    add_error("visual_closure:skip_reason", "Skipped assets require a reason.", asset_id)
                if strict_lane and current.get("guessed_type") != "cover_decoration":
                    add_error(
                        "visual_closure:strict_skip",
                        "Strict visual lane requires every non-decoration figure to be reviewed.",
                        asset_id,
                    )
                if current.get("high_risk") or item.get("machine_flags"):
                    add_error("visual_closure:high_risk_skip", "High-risk or machine-flagged assets cannot be skipped.", asset_id)
            else:
                add_error("visual_closure:supported_outcome", "Supported assets must be reviewed or explicitly skipped.", asset_id)
            continue

        if outcome != "unsupported":
            add_error("visual_closure:unsupported_outcome", "Unsupported assets must remain classified as unsupported.", asset_id)
            continue
        if not str(item.get("reason", "")).strip():
            add_error("visual_closure:unsupported_reason", "Unsupported assets require a reason.", asset_id)
        derivative_ok, derivative_message = _validate_derivative_evidence(
            review_dir, current, item.get("derivative_evidence"), current_by_id
        )
        alternative_ok = _valid_alternative_evidence(item.get("alternative_evidence"))
        if current.get("high_risk"):
            if closure_policy.get("high_risk_unsupported_requires_derivative_or_alternative_evidence", True):
                if not derivative_ok and not alternative_ok:
                    add_error(
                        "visual_closure:high_risk_derivative",
                        derivative_message or "High-risk unsupported asset requires derivative or alternative evidence.",
                        asset_id,
                    )
        elif strict_lane and not derivative_ok and not alternative_ok:
            add_error(
                "visual_closure:strict_unsupported",
                "Strict visual lane requires reviewed derivative or alternative evidence for unsupported assets.",
                asset_id,
            )
        elif not derivative_ok and not alternative_ok and not _valid_waiver(item.get("waiver")):
            add_error(
                "visual_closure:unsupported_resolution",
                "Unsupported asset requires reviewed derivative evidence, alternative evidence, or an approved waiver.",
                asset_id,
            )

    calculated_counts = {
        "asset_total": len(recorded_by_id),
        "reviewed": actual_counts.get("reviewed", 0),
        "skipped": actual_counts.get("skipped", 0),
        "unsupported": actual_counts.get("unsupported", 0),
        "unaccounted": actual_counts.get("unaccounted", 0),
    }
    declared_counts = result.get("asset_counts", {})
    if any(declared_counts.get(key) != value for key, value in calculated_counts.items()):
        add_error("visual_closure:declared_counts", "Declared asset counts do not match the asset records.")
    invariant_ok = (
        calculated_counts["asset_total"]
        == calculated_counts["reviewed"] + calculated_counts["skipped"] + calculated_counts["unsupported"]
        and calculated_counts["unaccounted"] == 0
        and calculated_counts["asset_total"] == len(current_inventory)
    )
    if not invariant_ok:
        add_error("visual_closure:conservation", "Asset conservation invariant failed or unaccounted assets remain.")

    return {
        "passed": not errors,
        "mode": closure_policy.get("mode", "enforce"),
        "asset_counts": calculated_counts,
        "conservation_passed": invariant_ok,
        "errors": errors,
    }


def prepare_visual_audit(
    review_dir: Path,
    project_dir: Path | None = None,
    review_lane: str | None = None,
) -> dict:
    review_lane = review_lane or default_review_lane()
    inventory = discover_visual_assets(review_dir, project_dir)
    images = [dict(item) for item in inventory if item["format_status"] == "supported"]
    images = map_images_to_context(review_dir, images)
    for image in images:
        image["guessed_type"] = classify_image_type(image)
        image["high_risk"] = image["guessed_type"] in HIGH_RISK_TYPES

    visual_prefilter = run_visual_prefilter(review_dir, images)
    checklist = generate_checklist(images, review_lane, visual_prefilter)
    classified_by_id = {item["asset_id"]: item for item in checklist if item.get("asset_id")}
    for asset in inventory:
        classified = classified_by_id.get(asset["asset_id"])
        if classified:
            asset["guessed_type"] = classified["guessed_type"]
            asset["high_risk"] = classified["guessed_type"] in HIGH_RISK_TYPES

    checklist_path = review_dir / "visual_audit_checklist.json"
    prefilter_path = review_dir / "visual_prefilter.json"
    template_path = review_dir / "figure_audit.md"
    visual_result_path = review_dir / load_policy().get("visual_closure_policy", {}).get(
        "result_json", "visual_audit_result.json"
    )

    write_json(prefilter_path, visual_prefilter)
    write_json(checklist_path, checklist)
    template_path.write_text(
        generate_figure_audit_template(checklist, review_dir, visual_prefilter, review_lane),
        encoding="utf-8",
    )
    visual_result = build_visual_audit_result(review_dir, inventory, checklist, review_lane)
    write_json(visual_result_path, visual_result)

    type_distribution = dict(
        sorted(
            Counter(item["guessed_type"] for item in checklist if item["needs_audit"]).items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
    )
    result = {
        "status": "prepared" if inventory else "skipped",
        "review_lane": review_lane,
        "total_images": len(inventory),
        "supported_images": len(images),
        "unsupported_images": sum(1 for item in inventory if item["format_status"] == "unsupported"),
        "to_audit": sum(1 for item in checklist if item["needs_audit"]),
        "skipped": sum(1 for item in checklist if not item["needs_audit"]),
        "mapped": sum(1 for image in images if image.get("figure_id") or image.get("report_refs") or image.get("is_cover")),
        "type_distribution": type_distribution,
        "machine_prefilter_summary": visual_prefilter.get("summary", {}),
        "checklist_path": str(checklist_path),
        "prefilter_path": str(prefilter_path),
        "template_path": str(template_path),
        "visual_result_path": str(visual_result_path),
    }
    append_event(
        review_dir,
        "visual_audit_prepared" if inventory else "visual_audit_skipped",
        actor="visual_audit",
        phase="visual_audit_ready",
        outputs=[str(prefilter_path), str(checklist_path), str(template_path), str(visual_result_path)],
        details={
            "review_lane": review_lane,
            "to_audit": result["to_audit"],
            "flagged_images": visual_prefilter.get("summary", {}).get("flagged_images", 0),
            "unsupported_images": result["unsupported_images"],
            "reason": "no_images" if not inventory else "",
        },
    )
    return result


def main() -> None:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise SystemExit(f"Review directory does not exist: {review_dir}")

    project_dir = Path(args.project_dir) if args.project_dir else None
    result = prepare_visual_audit(review_dir, project_dir=project_dir, review_lane=args.review_lane)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
