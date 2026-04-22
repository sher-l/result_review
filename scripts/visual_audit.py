#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Prepare Layer 2 visual audit assets with machine prescreen support."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from audit_runtime import append_event, infer_project_id, load_case_manifest, write_json

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Layer 2 visual audit artifacts.")
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument("--project-dir", help="Optional raw project directory", default=None)
    parser.add_argument(
        "--review-lane",
        choices=("standard", "strict"),
        default="standard",
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
            target = next((image for image in images if image["filename"] == img_name), None)
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

        image_flags[image["filename"]] = {
            "ocr_text": ocr_text[:200],
            "predicted_family": predicted,
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
    }
    return {"summary": summary, "images": image_flags}


def generate_checklist(images: list[dict], review_lane: str, visual_prefilter: dict) -> list[dict]:
    checklist = []
    flagged_lookup = visual_prefilter.get("images", {})

    for index, image in enumerate(images, start=1):
        image_type = classify_image_type(image)
        image["guessed_type"] = image_type
        flags = flagged_lookup.get(image["filename"], {}).get("flags", [])
        skip_reason = ""
        needs_audit = True

        if image["size_bytes"] < 2000:
            needs_audit = False
            skip_reason = f"Very small asset ({image['size_bytes']}B)"
        elif image_type == "cover_decoration":
            needs_audit = False
            skip_reason = "Cover decoration or logo"
        elif review_lane == "standard" and not flags and image_type not in HIGH_RISK_TYPES:
            needs_audit = False
            skip_reason = "Standard lane: low-risk image without machine flags"

        checklist.append(
            {
                "index": index,
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
                "machine_prefilter": flagged_lookup.get(image["filename"], {}),
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


def prepare_visual_audit(review_dir: Path, project_dir: Path | None = None, review_lane: str = "standard") -> dict:
    del project_dir  # Reserved for compatibility with prior entrypoint.

    images = discover_images(review_dir)
    if not images:
        append_event(review_dir, "visual_audit_skipped", actor="visual_audit", details={"reason": "no_images"})
        return {"total_images": 0, "status": "skipped", "review_lane": review_lane}

    images = map_images_to_context(review_dir, images)
    for image in images:
        image["guessed_type"] = classify_image_type(image)

    visual_prefilter = run_visual_prefilter(review_dir, images)
    checklist = generate_checklist(images, review_lane, visual_prefilter)

    checklist_path = review_dir / "visual_audit_checklist.json"
    prefilter_path = review_dir / "visual_prefilter.json"
    template_path = review_dir / "figure_audit.md"

    write_json(prefilter_path, visual_prefilter)
    write_json(checklist_path, checklist)
    template_path.write_text(
        generate_figure_audit_template(checklist, review_dir, visual_prefilter, review_lane),
        encoding="utf-8",
    )

    type_distribution = dict(
        sorted(
            Counter(item["guessed_type"] for item in checklist if item["needs_audit"]).items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
    )
    result = {
        "status": "prepared",
        "review_lane": review_lane,
        "total_images": len(images),
        "to_audit": sum(1 for item in checklist if item["needs_audit"]),
        "skipped": sum(1 for item in checklist if not item["needs_audit"]),
        "mapped": sum(1 for image in images if image.get("figure_id") or image.get("report_refs") or image.get("is_cover")),
        "type_distribution": type_distribution,
        "machine_prefilter_summary": visual_prefilter.get("summary", {}),
        "checklist_path": str(checklist_path),
        "prefilter_path": str(prefilter_path),
        "template_path": str(template_path),
    }
    append_event(
        review_dir,
        "visual_audit_prepared",
        actor="visual_audit",
        outputs=[str(prefilter_path), str(checklist_path), str(template_path)],
        details={
            "review_lane": review_lane,
            "to_audit": result["to_audit"],
            "flagged_images": visual_prefilter.get("summary", {}).get("flagged_images", 0),
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
