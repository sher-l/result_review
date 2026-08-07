"""项目交付物结构预解析器：从项目目录提取结构化索引

将项目交付目录转化为机器可读的结构化数据，供机械检查和 AI 审查使用。
与 parse_report_structure.py（报告文本索引）配对形成完整 Layer 0。

用法:
    python parse_project_structure.py <项目目录> [输出JSON路径]

输出 JSON 包含:
    - modules: 分析模块列表（编号目录、文件统计、类型识别）
    - code_files: 代码文件清单（R/Python，提取包名和关键参数）
    - data_files: 数据文件清单（CSV/TSV 维度、RDS 等）
    - image_files: 图片文件清单
    - parameter_index: 关键参数索引（logFC、p值、包名）
    - geo_references: GEO 数据集引用（从代码中提取）
    - project_id_references: 项目编号引用（检测外来 ID）
"""
import csv
import json
import re
import sys
from pathlib import Path
from itertools import islice


# 文件类型分类
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.svg', '.bmp', '.gif'}
DATA_EXTS = {'.csv', '.tsv', '.txt', '.xlsx', '.xls'}
BINARY_DATA_EXTS = {'.rds', '.rdata', '.rda', '.h5', '.h5ad', '.h5seurat', '.loom'}
CODE_EXTS = {'.r', '.R', '.py', '.rmd', '.qmd'}
CONFIG_EXTS = {'.ini', '.cfg', '.yaml', '.yml', '.toml', '.json'}
PDF_EXT = {'.pdf'}
IGNORE_DIRS = {'.git', '__pycache__', '.Rproj.user', '.snakemake', 'renv', 'packrat'}
DELIVERY_RESULT_ROOT_NAMES = {
    '结果文件', '结果', '分析结果', 'results', 'result', 'Result', 'Results'
}
DELIVERY_CODE_ROOT_NAMES = {
    '代码', 'code', 'script', 'scripts'
}
DELIVERY_ATTACHMENT_ROOT_NAMES = {
    '附件', '附件-前期结果', 'supplement', 'supplements'
}


def scan_modules(project_dir: Path) -> list[dict]:
    """扫描分析模块（编号目录如 01_DEGs, 14_singcell）"""
    modules = []
    module_pattern = re.compile(r'^(\d+)[_\-.](.+)')

    for d in sorted(project_dir.iterdir()):
        if not d.is_dir() or d.name in IGNORE_DIRS:
            continue

        m = module_pattern.match(d.name)
        if not m:
            # 非编号目录（script, check_reports 等）
            if d.name.lower() in ('script', 'scripts', 'code', 'check_reports'):
                continue  # 跳过辅助目录
            # 仍然记录但标记为非模块
            modules.append({
                'name': d.name,
                'number': None,
                'is_module': False,
                'path': str(d.relative_to(project_dir)),
            })
            continue

        # 统计文件
        all_files = list(islice(d.rglob('*'), 2000))
        files = [f for f in all_files if f.is_file()]

        n_code = sum(1 for f in files if f.suffix.lower() in CODE_EXTS)
        n_csv = sum(1 for f in files if f.suffix.lower() in DATA_EXTS | BINARY_DATA_EXTS)
        n_img = sum(1 for f in files if f.suffix.lower() in IMG_EXTS)
        n_pdf = sum(1 for f in files if f.suffix.lower() in PDF_EXT)
        n_rds = sum(1 for f in files if f.suffix.lower() in BINARY_DATA_EXTS)

        # 子目录
        subdirs = [sd.name for sd in d.iterdir() if sd.is_dir()]

        modules.append({
            'name': d.name,
            'number': int(m.group(1)),
            'label': m.group(2),
            'is_module': True,
            'path': str(d.relative_to(project_dir)),
            'subdirs': subdirs,
            'file_counts': {
                'total': len(files),
                'code': n_code,
                'csv': n_csv,
                'images': n_img,
                'pdf': n_pdf,
                'binary_data': n_rds,
            },
        })

    return modules


def detect_delivery_roots(project_dir: Path) -> dict:
    """识别项目交付根目录口径，避免只按“结果文件/”判断。"""
    result_roots = []
    code_roots = []
    attachment_roots = []

    for d in sorted(project_dir.iterdir()):
        if not d.is_dir() or d.name in IGNORE_DIRS:
            continue
        if d.name in DELIVERY_RESULT_ROOT_NAMES:
            result_roots.append(str(d.relative_to(project_dir)))
        if d.name in DELIVERY_CODE_ROOT_NAMES:
            code_roots.append(str(d.relative_to(project_dir)))
        if d.name in DELIVERY_ATTACHMENT_ROOT_NAMES:
            attachment_roots.append(str(d.relative_to(project_dir)))

    if result_roots:
        layout = 'segmented_delivery'
    elif code_roots or attachment_roots:
        layout = 'mixed_delivery'
    else:
        layout = 'flat_delivery'

    return {
        'layout': layout,
        'result_roots': result_roots,
        'code_roots': code_roots,
        'attachment_roots': attachment_roots,
    }


def _candidate_module_roots(project_dir: Path) -> list[Path]:
    roots = [project_dir]
    for d in sorted(project_dir.iterdir()):
        if not d.is_dir() or d.name in IGNORE_DIRS:
            continue
        if d.name in DELIVERY_RESULT_ROOT_NAMES:
            roots.append(d)
    return roots


def scan_modules(project_dir: Path) -> list[dict]:
    """扫描分析模块，支持顶层和“分析结果/结果文件/”二级交付结构。"""
    modules = []
    module_pattern = re.compile(r'^(\d+)[_\-.](.+)')
    seen_paths = set()

    for root in _candidate_module_roots(project_dir):
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name in IGNORE_DIRS:
                continue

            rel_path = str(d.relative_to(project_dir))
            if rel_path in seen_paths:
                continue
            seen_paths.add(rel_path)

            m = module_pattern.match(d.name)
            if not m:
                if root == project_dir and d.name.lower() not in ('script', 'scripts', 'code', 'check_reports'):
                    all_files = list(islice(d.rglob('*'), 2000))
                    files = [f for f in all_files if f.is_file()]
                    n_code = sum(1 for f in files if f.suffix.lower() in CODE_EXTS)
                    n_csv = sum(1 for f in files if f.suffix.lower() in DATA_EXTS | BINARY_DATA_EXTS)
                    n_img = sum(1 for f in files if f.suffix.lower() in IMG_EXTS)
                    n_pdf = sum(1 for f in files if f.suffix.lower() in PDF_EXT)
                    n_rds = sum(1 for f in files if f.suffix.lower() in BINARY_DATA_EXTS)
                    subdirs = [sd.name for sd in d.iterdir() if sd.is_dir()]
                    modules.append({
                        'name': d.name,
                        'number': None,
                        'is_module': False,
                        'path': rel_path,
                        'subdirs': subdirs,
                        'file_counts': {
                            'total': len(files),
                            'code': n_code,
                            'csv': n_csv,
                            'images': n_img,
                            'pdf': n_pdf,
                            'binary_data': n_rds,
                        },
                    })
                continue

            all_files = list(islice(d.rglob('*'), 2000))
            files = [f for f in all_files if f.is_file()]
            n_code = sum(1 for f in files if f.suffix.lower() in CODE_EXTS)
            n_csv = sum(1 for f in files if f.suffix.lower() in DATA_EXTS | BINARY_DATA_EXTS)
            n_img = sum(1 for f in files if f.suffix.lower() in IMG_EXTS)
            n_pdf = sum(1 for f in files if f.suffix.lower() in PDF_EXT)
            n_rds = sum(1 for f in files if f.suffix.lower() in BINARY_DATA_EXTS)
            subdirs = [sd.name for sd in d.iterdir() if sd.is_dir()]

            modules.append({
                'name': d.name,
                'number': int(m.group(1)),
                'label': m.group(2),
                'is_module': True,
                'path': rel_path,
                'subdirs': subdirs,
                'file_counts': {
                    'total': len(files),
                    'code': n_code,
                    'csv': n_csv,
                    'images': n_img,
                    'pdf': n_pdf,
                    'binary_data': n_rds,
                },
            })

    return modules


def scan_code_files(project_dir: Path) -> list[dict]:
    """扫描所有代码文件，提取包名和关键参数"""
    code_files = []

    for f in sorted(project_dir.rglob('*')):
        if not f.is_file() or f.suffix.lower() not in CODE_EXTS:
            continue
        if any(p in f.parts for p in IGNORE_DIRS):
            continue

        try:
            content = f.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        lines = content.splitlines()
        lang = 'R' if f.suffix.lower() in {'.r', '.rmd', '.qmd'} else 'Python'

        # 提取包/库引用
        packages = _extract_packages(lines, lang)

        # 提取关键参数
        params = _extract_parameters(lines)

        # 提取输入/输出文件引用
        io_files = _extract_io_references(lines)

        # 提取 GEO/TCGA 引用
        gse_refs = set(re.findall(r'\b(GSE\d{4,8})\b', content))
        tcga_refs = set(re.findall(r'\b(TCGA-[A-Z]{2,6})\b', content))

        # 提取项目编号引用
        proj_ids = set(re.findall(r'\b(\d{2}Y[A-Z]{2,3}\d{2,4}F)\b', content))

        code_files.append({
            'path': str(f.relative_to(project_dir)),
            'language': lang,
            'lines': len(lines),
            'packages': sorted(packages),
            'parameters': params,
            'io_references': io_files[:30],  # 限制输出大小
            'gse_refs': sorted(gse_refs),
            'tcga_refs': sorted(tcga_refs),
            'project_ids': sorted(proj_ids),
        })

    return code_files


def scan_config_files(project_dir: Path) -> list[dict]:
    """扫描配置文件，补充代码外的参数来源。"""
    config_files = []

    for f in sorted(project_dir.rglob('*')):
        if not f.is_file() or f.suffix.lower() not in CONFIG_EXTS:
            continue
        if any(part in f.parts for part in IGNORE_DIRS):
            continue
        try:
            content = f.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        lines = content.splitlines()
        params = _extract_parameters(lines, allow_config_patterns=True)
        if not params and f.suffix.lower() == '.json':
            continue
        config_files.append({
            'path': str(f.relative_to(project_dir)),
            'format': f.suffix.lower().lstrip('.'),
            'lines': len(lines),
            'parameters': params,
        })

    return config_files


def _extract_packages(lines: list[str], lang: str) -> set[str]:
    """从代码中提取包/库引用"""
    packages = set()

    if lang == 'R':
        # library(xxx), require(xxx), xxx::yyy
        for line in lines:
            # library/require
            for m in re.finditer(r'(?:library|require)\s*\(\s*["\']?(\w+)', line):
                packages.add(m.group(1))
            # namespace::function
            for m in re.finditer(r'(\w+)::', line):
                packages.add(m.group(1))
    else:
        # import xxx, from xxx import
        for line in lines:
            m = re.match(r'^(?:import|from)\s+([\w.]+)', line.strip())
            if m:
                packages.add(m.group(1).split('.')[0])

    # 过滤常见非包名
    packages -= {'base', 'utils', 'stats', 'graphics', 'grDevices',
                 'methods', 'datasets', 'tools', 'parallel', 'os', 'sys', 're'}
    return packages


def _extract_parameters(lines: list[str], allow_config_patterns: bool = False) -> list[dict]:
    """从代码中提取关键分析参数"""
    params = []

    patterns = [
        # logFC 阈值
        (re.compile(r'(?:logFC|log2FC|logFoldChange|logfc_cutoff|logFC_threshold)\s*[<=>\-]+\s*([\d.]+)', re.I),
         'logFC_threshold'),
        # p 值阈值
        (re.compile(r'(?:pvalue|p\.value|P\.thres|p_threshold|p_cutoff|alpha)\s*[<=>\-]+\s*([\d.eE\-]+)', re.I),
         'p_value_threshold'),
        (re.compile(r'adj\.P\.Val\s*<\s*([\d.eE\-]+)', re.I), 'adj_p_threshold'),
        # FDR
        (re.compile(r'(?:FDR|q\.value|padj)\s*[<=>\-]+\s*([\d.eE\-]+)', re.I),
         'fdr_threshold'),
        # Top N
        (re.compile(r'(?:top|TopN|n_top|top_n)\s*[<=>\-]+\s*(\d+)', re.I),
         'top_n'),
        # 分辨率（Seurat）
        (re.compile(r'resolution\s*=\s*([\d.]+)', re.I),
         'clustering_resolution'),
        # nFeature/nCount 阈值（单细胞 QC）
        (re.compile(r'nFeature_RNA\s*[<>]=?\s*(\d+)'),
         'nFeature_threshold'),
        (re.compile(r'nCount_RNA\s*[<>]=?\s*(\d+)'),
         'nCount_threshold'),
        (re.compile(r'percent\.mt\s*[<>]=?\s*([\d.]+)'),
         'mito_threshold'),
        # 软阈值（WGCNA）
        (re.compile(r'(?:soft\.?[Tt]hreshold|power)\s*[<=>\-]+\s*(\d+)'),
         'wgcna_soft_threshold'),
    ]

    config_patterns = [
        (re.compile(r'(?:logFC|log2FC|logfc_cutoff|fc_cutoff|fold_change)\s*[:=]\s*["\']?([\d.]+)', re.I),
         'logFC_threshold'),
        (re.compile(r'(?:pvalue|p_value|p_cutoff|p_threshold|alpha)\s*[:=]\s*["\']?([\d.eE\-]+)', re.I),
         'p_value_threshold'),
        (re.compile(r'(?:fdr|padj|q_value|adj_p)\s*[:=]\s*["\']?([\d.eE\-]+)', re.I),
         'fdr_threshold'),
        (re.compile(r'(?:resolution|cluster_resolution)\s*[:=]\s*["\']?([\d.]+)', re.I),
         'clustering_resolution'),
        (re.compile(r'(?:top_n|topn|n_top)\s*[:=]\s*["\']?(\d+)', re.I),
         'top_n'),
        (re.compile(r'(?:soft_threshold|softpower|power)\s*[:=]\s*["\']?(\d+)', re.I),
         'wgcna_soft_threshold'),
    ]
    if allow_config_patterns:
        patterns.extend(config_patterns)

    for i, line in enumerate(lines):
        for pattern, param_type in patterns:
            for m in pattern.finditer(line):
                params.append({
                    'type': param_type,
                    'value': m.group(1),
                    'line': i + 1,
                    'context': line.strip()[:100],
                    'source': 'config' if allow_config_patterns else 'code',
                })

    return params


def _extract_io_references(lines: list[str]) -> list[dict]:
    """提取代码中的输入/输出文件路径引用"""
    refs = []

    io_pattern = re.compile(
        r'(?:read[._]|load|write[._]|save|read\.csv|read\.table|fread|readRDS|'
        r'saveRDS|write\.csv|ggsave|pdf\(|png\(|tiff\(|fwrite)'
        r'\s*\(\s*["\']([^"\']+)["\']',
        re.I
    )

    for i, line in enumerate(lines):
        for m in io_pattern.finditer(line):
            filepath = m.group(1)
            # 判断读写方向
            func_match = re.search(r'(read|load|write|save|ggsave|pdf|png|tiff|fwrite)', line, re.I)
            direction = 'output' if func_match and func_match.group(1).lower() in (
                'write', 'save', 'ggsave', 'pdf', 'png', 'tiff', 'fwrite', 'saverds'
            ) else 'input'
            refs.append({
                'path': filepath,
                'direction': direction,
                'line': i + 1,
            })

    return refs


def scan_data_files(project_dir: Path) -> list[dict]:
    """扫描数据文件（CSV/TSV 维度，RDS 等）"""
    data_files = []

    for f in sorted(project_dir.rglob('*')):
        if not f.is_file():
            continue
        if any(p in f.parts for p in IGNORE_DIRS):
            continue

        ext = f.suffix.lower()
        try:
            size = f.stat().st_size
        except OSError:
            continue

        if ext in {'.csv', '.tsv'}:
            rows, cols, header = _csv_dimensions(f, ext)
            data_files.append({
                'path': str(f.relative_to(project_dir)),
                'type': 'csv' if ext == '.csv' else 'tsv',
                'size_bytes': size,
                'rows': rows,
                'cols': cols,
                'header': header[:10] if header else [],  # 前10列名
            })
        elif ext in DATA_EXTS | BINARY_DATA_EXTS:
            data_files.append({
                'path': str(f.relative_to(project_dir)),
                'type': ext.lstrip('.'),
                'size_bytes': size,
            })

    return data_files


def _csv_dimensions(filepath: Path, ext: str) -> tuple[int, int, list[str]]:
    """快速获取 CSV/TSV 行数、列数、表头"""
    delimiter = '\t' if ext == '.tsv' else ','
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
            # 读取前5行判断
            sample_lines = list(islice(fh, 5))
            if not sample_lines:
                return 0, 0, []

            # 自动检测分隔符
            if delimiter == ',' and '\t' in sample_lines[0] and ',' not in sample_lines[0]:
                delimiter = '\t'

            reader = csv.reader(sample_lines, delimiter=delimiter)
            rows_sample = list(reader)
            if not rows_sample:
                return 0, 0, []

            header = rows_sample[0]
            cols = len(header)

            # 快速行数（计数行而非完整解析）
            fh.seek(0)
            row_count = sum(1 for _ in fh) - 1  # 减去表头
            return max(row_count, 0), cols, header
    except Exception:
        return -1, -1, []


def scan_image_files(project_dir: Path) -> list[dict]:
    """扫描图片文件"""
    images = []
    for f in sorted(project_dir.rglob('*')):
        if not f.is_file() or f.suffix.lower() not in IMG_EXTS | PDF_EXT:
            continue
        if any(p in f.parts for p in IGNORE_DIRS):
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue

        # 确定所属模块
        module = None
        rel = f.relative_to(project_dir)
        if len(rel.parts) > 1:
            module = rel.parts[0]

        images.append({
            'path': str(rel),
            'type': f.suffix.lstrip('.').lower(),
            'size_bytes': size,
            'module': module,
        })

    return images


def build_parameter_index(code_files: list[dict], config_files: list[dict] | None = None) -> dict:
    """从代码文件和配置文件中汇总参数索引。"""
    index = {}
    for cf in code_files:
        for param in cf.get('parameters', []):
            ptype = param['type']
            if ptype not in index:
                index[ptype] = []
            index[ptype].append({
                'value': param['value'],
                'file': cf['path'],
                'line': param['line'],
                'source': param.get('source', 'code'),
            })
    for cf in config_files or []:
        for param in cf.get('parameters', []):
            ptype = param['type']
            if ptype not in index:
                index[ptype] = []
            index[ptype].append({
                'value': param['value'],
                'file': cf['path'],
                'line': param['line'],
                'source': param.get('source', 'config'),
            })
    return index


def build_geo_index(code_files: list[dict], modules: list[dict]) -> list[dict]:
    """从代码和目录中汇总 GEO 引用"""
    geo_refs = {}

    # 从代码中
    for cf in code_files:
        for gse in cf.get('gse_refs', []):
            if gse not in geo_refs:
                geo_refs[gse] = {'id': gse, 'found_in_code': [], 'found_in_dirs': False}
            geo_refs[gse]['found_in_code'].append(cf['path'])

    # 从目录名中
    for mod in modules:
        for subdir in mod.get('subdirs', []):
            if subdir.startswith('GSE'):
                gse = re.match(r'(GSE\d+)', subdir)
                if gse:
                    gse_id = gse.group(1)
                    if gse_id not in geo_refs:
                        geo_refs[gse_id] = {'id': gse_id, 'found_in_code': [], 'found_in_dirs': True}
                    else:
                        geo_refs[gse_id]['found_in_dirs'] = True
        # 模块名本身
        if mod['name'].startswith('GSE'):
            gse = re.match(r'(GSE\d+)', mod['name'])
            if gse:
                gse_id = gse.group(1)
                if gse_id not in geo_refs:
                    geo_refs[gse_id] = {'id': gse_id, 'found_in_code': [], 'found_in_dirs': True}
                else:
                    geo_refs[gse_id]['found_in_dirs'] = True

    return sorted(geo_refs.values(), key=lambda x: x['id'])


def build_project_id_index(code_files: list[dict], current_project_id: str) -> list[dict]:
    """从代码中汇总项目编号引用，标记外来 ID"""
    all_ids = {}
    for cf in code_files:
        for pid in cf.get('project_ids', []):
            if pid not in all_ids:
                all_ids[pid] = {'id': pid, 'is_foreign': pid != current_project_id, 'found_in': []}
            all_ids[pid]['found_in'].append(cf['path'])

    return sorted(all_ids.values(), key=lambda x: (not x['is_foreign'], x['id']))


def parse_project(project_dir: Path) -> dict:
    """主解析入口"""
    # 提取项目编号
    proj_id_match = re.search(r'(\d{2}Y[A-Z]{2,3}\d{2,4}F)', project_dir.name)
    current_proj_id = proj_id_match.group(1) if proj_id_match else ''

    modules = scan_modules(project_dir)
    code_files = scan_code_files(project_dir)
    config_files = scan_config_files(project_dir)
    data_files = scan_data_files(project_dir)
    image_files = scan_image_files(project_dir)
    delivery_roots = detect_delivery_roots(project_dir)

    param_index = build_parameter_index(code_files, config_files)
    geo_index = build_geo_index(code_files, modules)
    proj_id_index = build_project_id_index(code_files, current_proj_id)

    # 汇总包列表
    all_packages = set()
    for cf in code_files:
        all_packages.update(cf.get('packages', []))

    return {
        'metadata': {
            'project_dir': str(project_dir),
            'project_id': current_proj_id,
            'delivery_layout': delivery_roots['layout'],
            'delivery_result_roots': delivery_roots['result_roots'],
            'delivery_code_roots': delivery_roots['code_roots'],
            'delivery_attachment_roots': delivery_roots['attachment_roots'],
            'total_modules': sum(1 for m in modules if m.get('is_module')),
            'total_code_files': len(code_files),
            'total_config_files': len(config_files),
            'total_data_files': len(data_files),
            'total_images': len(image_files),
            'all_packages': sorted(all_packages),
        },
        'modules': modules,
        'code_files': code_files,
        'config_files': config_files,
        'data_files': data_files,
        'image_files': image_files,
        'parameter_index': param_index,
        'geo_references': geo_index,
        'project_id_references': proj_id_index,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    if not project_dir.exists():
        print(f"ERROR: {project_dir} 不存在")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else project_dir / 'project_structure.json'

    result = parse_project(project_dir)

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"项目结构索引: {out_path}")
    print(f"  模块: {result['metadata']['total_modules']}")
    print(f"  代码文件: {result['metadata']['total_code_files']}")
    print(f"  数据文件: {result['metadata']['total_data_files']}")
    print(f"  图片文件: {result['metadata']['total_images']}")
    print(f"  使用包: {len(result['metadata']['all_packages'])}")
    print(f"  GEO引用: {len(result['geo_references'])}")

    # 显示参数索引摘要
    if result['parameter_index']:
        print(f"  关键参数:")
        for ptype, vals in result['parameter_index'].items():
            unique_vals = set(v['value'] for v in vals)
            print(f"    {ptype}: {', '.join(sorted(unique_vals))}")

    # 显示外来项目编号
    foreign_ids = [p for p in result['project_id_references'] if p['is_foreign']]
    if foreign_ids:
        print(f"  ⚠️ 外来项目编号: {[p['id'] for p in foreign_ids]}")


if __name__ == '__main__':
    main()
