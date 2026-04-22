"""机械检查器：基于预解析 JSON + 项目目录执行确定性审查

接收 parse_report_structure.py 的输出 JSON，结合项目目录结构，
执行一系列不需要 AI 判断的确定性检查。

用法:
    python mechanical_checks.py <report_structure.json> <项目目录> [输出路径]

检查项:
    MC-001: 图编号-章节不匹配（来自预解析）
    MC-002: 中文术语异常（来自预解析）
    MC-003: 章节编号跳号（来自预解析）
    MC-004: 报告模块 vs 交付目录一致性
    MC-005: 流程图关键词 vs 交付物对照
    MC-006: 复制粘贴残留检测（外来项目ID/GEO/疾病名）
    MC-007: 数字求和校验（"共X=上调Y+下调Z"）
    MC-008: 代码级交叉校验（代码中外来项目ID/GEO引用不一致）
    MC-009: 报告参数vs代码参数交叉校验（logFC/adj_p/resolution）
    MC-010: 报告分析方法vs代码包名一致性（LASSO→glmnet等）
    MC-011: 代码中硬编码绝对路径检测（背景提示，默认不单独判错）
    MC-012: 报告引用结果文件/目录存在性验证
    MC-013: 图编号连续性检测（重复/缺失）
"""
import json
import re
import sys
from pathlib import Path


# 严重度定义
FATAL = 'FATAL'
CRITICAL = 'CRITICAL'
MAJOR = 'MAJOR'
WARNING = 'WARNING'
INFO = 'INFO'


def _find_matching_dirs(project_dir: Path, keywords: list[str]) -> list[Path]:
    matches = []
    lowered_keywords = [k.lower() for k in keywords]
    for d in project_dir.rglob('*'):
        if d.is_dir() and any(k in d.name.lower() for k in lowered_keywords):
            matches.append(d)
    return matches


def _dir_has_files(path: Path) -> bool:
    try:
        return any(p.is_file() for p in path.rglob('*'))
    except OSError:
        return False


def _looks_like_deg_result_table(data_file: dict) -> bool:
    header = [str(h).lower() for h in data_file.get('header', [])]
    if not header:
        return False
    deg_markers = {
        'logfc', 'log2fc', 'logfoldchange', 'pvalue', 'p.value', 'padj',
        'adj.p.val', 'adj_p_val', 'fdr', 'regulation', 'direction'
    }
    return any(col in deg_markers for col in header)


def check_figure_mismatches(structure: dict) -> list[dict]:
    """MC-001: 图编号-章节不匹配

    增加系统性命名规范检测：
    1. 固定偏移：所有 fig 前缀与 section 有相同偏移（如 Fig 1.x 总在 section 2）
    2. 一一映射：每个 fig 前缀始终出现在同一个 section（即使偏移不同）
    满足任一条件则判定为命名规范，降级为 INFO。
    """
    mismatches = structure.get('figure_mismatches', [])
    if not mismatches:
        return []

    from collections import Counter, defaultdict

    # 提取 (fig_prefix, section) 对
    offsets = []
    fig_prefix_to_sections = defaultdict(set)
    parsed_count = 0
    for fm in mismatches:
        fig_id = fm.get('fig_id', '')
        section = fm.get('in_section', '')
        fig_match = re.match(r'(?:Fig\.?|图)\s*(\d+)', fig_id, re.IGNORECASE)
        if fig_match:
            prefix = fig_match.group(1)
            fig_prefix_to_sections[prefix].add(str(section))
            sec_match = re.match(r'(\d+)', str(section))
            if sec_match:
                fig_num = int(prefix)
                sec_num = int(sec_match.group(1))
                offsets.append(sec_num - fig_num)
                parsed_count += 1

    is_systematic = False
    detection_reason = ''

    # 方法1: 固定偏移检测（>= 80% 的 mismatch 有相同偏移量）
    if len(offsets) >= 3:
        offset_counts = Counter(offsets)
        most_common_offset, most_common_count = offset_counts.most_common(1)[0]
        if most_common_count / len(offsets) >= 0.8:
            is_systematic = True
            detection_reason = f'固定偏移={most_common_offset}'

    # 方法2: 一一映射检测（每个 fig 前缀始终对应同一 section）
    if not is_systematic and len(fig_prefix_to_sections) >= 3:
        all_consistent = all(len(secs) == 1 for secs in fig_prefix_to_sections.values())
        if all_consistent:
            is_systematic = True
            detection_reason = f'{len(fig_prefix_to_sections)}个前缀各自映射到固定章节'

    issues = []
    if is_systematic:
        issues.append({
            'code': 'MC-001',
            'severity': INFO,
            'message': f"检测到系统性图编号命名规范（{len(mismatches)}处，{detection_reason}），非逐图错误",
            'detail': '图编号前缀与章节号存在一致映射关系，为报告命名规范而非复制粘贴残留',
        })
    else:
        for fm in mismatches:
            issues.append({
                'code': 'MC-001',
                'severity': MAJOR,
                'message': f"图编号与章节不匹配: {fm['fig_id']} 出现在章节 {fm['in_section']}",
                'line': fm['line'],
                'context': fm.get('context', ''),
                'detail': f"图编号前缀应与所在章节匹配（复制粘贴残留？）",
            })
    return issues


def check_chinese_anomalies(structure: dict) -> list[dict]:
    """MC-002: 中文术语异常"""
    issues = []
    for ca in structure.get('chinese_anomalies', []):
        if ca['description'] == '缺"免"字':
            severity = FATAL
        elif ca['description'] in ('输入法错误', '错字'):
            severity = CRITICAL
        else:
            severity = WARNING
        issues.append({
            'code': 'MC-002',
            'severity': severity,
            'message': f"中文异常: '{ca['text']}' → '{ca['correct']}' ({ca['description']})",
            'line': ca['line'],
            'context': ca.get('context', ''),
        })
    return issues


def check_section_gaps(structure: dict) -> list[dict]:
    """MC-003: 章节编号跳号（跳跃≥3个编号升级为CRITICAL）"""
    issues = []
    for gap in structure.get('section_numbering_gaps', []):
        n_missing = len(gap['missing'])
        severity = CRITICAL if n_missing >= 3 else WARNING
        issues.append({
            'code': 'MC-003',
            'severity': severity,
            'message': f"章节编号跳号: {gap['prev']} → {gap['curr']}（缺少 {n_missing} 个: {', '.join(gap['missing'][:5])}{'...' if n_missing > 5 else ''}）",
            'line': gap['line'],
        })
    return issues


def check_modules_vs_directories(structure: dict, project_dir: Path) -> list[dict]:
    """MC-004: 报告模块 vs 交付目录一致性

    将报告中描述的分析模块与实际交付目录对照，发现缺失或多余的交付物。
    """
    issues = []

    # 收集项目所有目录（含子目录，忽略 rawdata/script/check_reports）
    ignore_dirs = {'00_rawdata', 'rawdata', 'script', 'scripts', 'check_reports', '.git'}
    delivery_dirs = set()
    if project_dir.exists():
        for d in project_dir.rglob('*'):
            if d.is_dir() and d.name not in ignore_dirs:
                delivery_dirs.add(d.name)

    # 报告中的模块关键词 → 可能对应的目录名模式
    # 这个映射表覆盖常见生信分析模块
    module_dir_map = {
        '差异分析': ['DEGs', 'DEG', 'limma', 'DESeq'],
        '差异表达': ['DEGs', 'DEG', 'limma', 'DESeq'],
        'WGCNA': ['WGCNA'],
        'Venn': ['Venn', 'venn'],
        'PPI': ['PPI', 'ppi', 'STRING'],
        '富集分析': ['Enrichment', 'enrichment', 'GO_KEGG', 'KEGG'],
        '功能富集': ['Enrichment', 'enrichment', 'GO_KEGG'],
        '机器学习': ['ML', 'Machine_Learning', 'machine_learning', 'LASSO'],
        'LASSO': ['ML', 'LASSO', 'lasso'],
        'ROC': ['Exp_roc', 'ROC', 'roc', 'validation'],
        '免疫浸润': ['ssGSEA', 'immune', 'Immune', 'CIBERSORT', 'immuneInfiltration'],
        'ssGSEA': ['ssGSEA', 'immune'],
        'GSEA': ['GSEA', 'gsea'],
        '基因相关性': ['Gene_cor', 'correlation', 'Cor'],
        '药物预测': ['Drug_prediction', 'Drug', 'drug', 'CMap', 'CMAP'],
        '分子对接': ['Molecular_docking', 'Docking', 'docking', 'Autodock'],
        '单细胞': ['singcell', 'scRNA', 'singlecell', 'single_cell', 'scRNAseq'],
        '空间转录': ['Spatial', 'spatial', 'ST_', 'visium'],
        '生存分析': ['Survival', 'survival', 'surv', 'KM'],
        '预后模型': ['Prognosis', 'prognosis', 'nomogram', 'Nomogram'],
        'MR分析': ['MR', 'Mendelian'],
        '孟德尔随机化': ['MR', 'Mendelian'],
        '网络药理学': ['Network_pharmacology', 'network_pharm', 'NP'],
        '网络毒理学': ['Network_toxicology', 'network_tox', 'NT'],
        '拟时序': ['Trajectory', 'trajectory', 'pseudotime', 'Monocle'],
        '细胞通讯': ['CellChat', 'cellchat', 'CellPhone', 'cell_communication'],
        'scTenifoldKnk': ['TenifoldKnk', 'tenifold', 'knockout', 'virtual_knockout'],
        'scTenifoldNet': ['TenifoldNet', 'tenifold'],
        'SCENIC': ['SCENIC', 'scenic', 'regulon'],
        'CNV分析': ['CNV', 'cnv', 'InferCNV', 'infercnv'],
        '蛋白组': ['proteom', 'Proteom', 'protein'],
        '甲基化': ['MethSurv', 'methylation', 'Methyl'],
        '代谢物': ['metabol', 'Metabol', 'metabo'],
        'PCA分析': ['PCA', 'pca'],
        '列线图': ['Nomogram', 'nomogram', 'Nomo', 'Calibrat'],
        'SHAP': ['SHAP', 'shap'],
        'OPLS-DA': ['OPLS', 'opls'],
        'MCODE': ['MCODE', 'mcode'],
        'TIDE': ['TIDE', 'tide'],
        'CPTAC': ['CPTAC', 'cptac'],
        'ESTIMATE': ['ESTIMATE', 'estimate'],
        '拓扑分析': ['Topo', 'topo', 'CytoNCA', 'cytonca'],
    }

    # 从报告 sections 的标题中提取模块关键词
    sections = structure.get('sections', [])
    report_modules_found = {}  # keyword → section info
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        title = sec.get('title', '')
        for keyword, dir_patterns in module_dir_map.items():
            if keyword in title:
                report_modules_found[keyword] = {
                    'section': sec.get('id'),
                    'title': title,
                    'expected_dirs': dir_patterns,
                    'line': sec.get('line', 0),
                }

    # 检查报告中提到的模块是否有对应交付目录
    # 同时尝试中文关键词匹配（许多项目使用中文目录名如"6-功能富集分析"）
    for keyword, info in report_modules_found.items():
        found = False
        for dir_name in delivery_dirs:
            # 方法1：英文模式匹配
            for pat in info['expected_dirs']:
                if pat.lower() in dir_name.lower():
                    found = True
                    break
            # 方法2：中文关键词匹配（目录名含报告关键词）
            if not found and keyword in dir_name:
                found = True
            if found:
                break
        if not found:
            issues.append({
                'code': 'MC-004',
                'severity': WARNING,
                'message': f"报告模块 '{keyword}' (§{info['section']}) 在交付目录中未找到匹配",
                'line': info['line'],
                'detail': f"章节: {info['title']}，期望目录含: {info['expected_dirs']}",
            })

    return issues


def check_flowchart_vs_delivery(structure: dict, project_dir: Path, report_lines: list[str]) -> list[dict]:
    """MC-005: 流程图中提到的方法/工具 vs 交付物对照

    从报告全文中收集方法/工具关键词，与交付目录对照。
    特别关注流程图附近提到但无交付物的方法。
    """
    issues = []

    # 收集项目交付目录（包括子目录）
    all_dirs = set()
    if project_dir.exists():
        for d in project_dir.rglob('*'):
            if d.is_dir():
                all_dirs.add(d.name.lower())

    # 需要交付物的方法关键词 → 期望目录名
    method_delivery_map = {
        'scTenifoldKnk': ['tenifoldknk', 'tenifold', 'knockout', 'virtual_knockout'],
        'scTenifoldNet': ['tenifoldnet', 'tenifold'],
        'SCENIC': ['scenic', 'regulon'],
        'InferCNV': ['infercnv', 'cnv'],
        'CytoTRACE': ['cytotrace'],
        'Monocle': ['monocle', 'trajectory', 'pseudotime'],
        'CellChat': ['cellchat', 'cell_communication'],
        'NicheNet': ['nichenet'],
        'RCTD': ['rctd'],
        'BayesSpace': ['bayesspace'],
        'STdeconvolve': ['stdeconvolve'],
        'SpaceRanger': ['spaceranger'],
        'Seurat': [],  # 太通用，跳过
    }

    # 搜索全文中出现的方法关键词
    full_text = '\n'.join(report_lines)
    for method, expected_dirs in method_delivery_map.items():
        if not expected_dirs:
            continue
        # 在全文中搜索（不区分大小写）
        if re.search(re.escape(method), full_text, re.IGNORECASE):
            found_dir = False
            for ed in expected_dirs:
                if any(ed in d for d in all_dirs):
                    found_dir = True
                    break
            if not found_dir:
                # 确认方法在哪些行出现
                mention_lines = []
                for idx, line in enumerate(report_lines):
                    if re.search(re.escape(method), line, re.IGNORECASE):
                        mention_lines.append(idx + 1)
                issues.append({
                    'code': 'MC-005',
                    'severity': WARNING,
                    'message': f"流程图/报告提到 '{method}'，但按当前目录命名规则未匹配到对应结果",
                    'line': mention_lines[0] if mention_lines else 0,
                    'detail': f"'{method}' 在 {len(mention_lines)} 处被提及 (L{', L'.join(str(l) for l in mention_lines[:5])})"
                             f"，但未找到 {expected_dirs} 相关目录；需AI复核是否属于命名映射不足导致的误报",
                })

    return issues


def check_copypaste_forensics(structure: dict, project_dir: Path, report_lines: list[str]) -> list[dict]:
    """MC-006: 复制粘贴残留检测

    检测报告中是否存在不属于本项目的信息：
    1. 外来项目编号 (YXX + 3位数字 + F)
    2. 不匹配的 GEO/TCGA 数据集
    3. 不匹配的疾病名（如在 UC 报告中出现"食管癌"）
    """
    issues = []

    # 提取当前项目编号
    folder_name = project_dir.name
    proj_id_match = re.search(r'(\d{2}Y[A-Z]{2,3}\d{2,4}F)', folder_name)
    current_proj_id = proj_id_match.group(1) if proj_id_match else ''

    # 提取当前项目疾病关键词（从文件夹名）
    disease_keywords = set()
    # 从文件夹名中提取中文部分
    cn_parts = re.findall(r'[\u4e00-\u9fff]+', folder_name)
    for part in cn_parts:
        if len(part) >= 2:
            disease_keywords.add(part)

    # 1. 检查外来项目编号
    proj_id_pattern = re.compile(r'\b(\d{2}Y[A-Z]{2,3}\d{2,4}F)\b')
    for idx, line in enumerate(report_lines):
        for m in proj_id_pattern.finditer(line):
            found_id = m.group(1)
            if current_proj_id and found_id != current_proj_id:
                issues.append({
                    'code': 'MC-006',
                    'severity': FATAL,
                    'message': f"发现外来项目编号: {found_id}（当前项目: {current_proj_id}）",
                    'line': idx + 1,
                    'context': line.strip()[:100],
                    'detail': '可能是复制粘贴残留',
                })

    # 2. 检查公开数据集（GEO/ArrayExpress）是否与 rawdata 目录匹配
    rawdata_datasets = set()
    rawdata_dir = project_dir / '00_rawdata'
    dataset_prefixes = ('GSE', 'E-MTAB-', 'E-GEOD-', 'PRJNA', 'SRP')
    if rawdata_dir.exists():
        for d in rawdata_dir.iterdir():
            if d.is_dir() and any(d.name.startswith(p) for p in dataset_prefixes):
                rawdata_datasets.add(d.name)
    # 也检查顶层
    for d in project_dir.iterdir():
        if d.is_dir() and any(d.name.startswith(p) for p in dataset_prefixes):
            rawdata_datasets.add(d.name)

    if rawdata_datasets:
        # 扩展匹配模式：GSE + E-MTAB + PRJNA + SRP
        dataset_pattern = re.compile(r'\b(GSE\d{4,8}|E-MTAB-\d{3,6}|E-GEOD-\d{3,6}|PRJNA\d{4,8}|SRP\d{4,8})\b')
        report_datasets = set()
        for idx, line in enumerate(report_lines):
            for m in dataset_pattern.finditer(line):
                report_datasets.add(m.group(1))

        # 报告中提到但 rawdata 中没有的
        for ds in report_datasets - rawdata_datasets:
            issues.append({
                'code': 'MC-006',
                'severity': INFO,
                'message': f"报告提及 {ds}，但 00_rawdata/ 中无对应目录",
                'detail': '可能是外部验证数据集或引用文献数据',
            })

        # rawdata 中有但报告中完全未提及的
        for ds in rawdata_datasets - report_datasets:
            issues.append({
                'code': 'MC-006',
                'severity': WARNING,
                'message': f"rawdata 中有 {ds} 目录，但报告全文未提及",
                'detail': '数据集可能遗漏，或使用了不同名称',
            })

    # 3. 通用模板残留检测：检查报告中是否有来自其他疾病/实验模板的术语
    # 这些词不太可能出现在非对应类型的项目中
    _TEMPLATE_RESIDUAL_GROUPS = {
        '脑缺血模板': {
            'keywords': ['Sham', 'MCAO', '脑缺血再灌注', 'OGD/R', '假手术组', 'middle cerebral artery'],
            'excludes': ['脑缺血', '脑卒中', '中风', 'stroke', 'cerebral'],  # 本身是脑缺血项目则跳过
        },
        '肿瘤模板': {
            'keywords': ['Tumor', 'Cancer', 'Malignant', '癌旁组织'],
            'excludes': ['癌', 'tumor', 'cancer', '肿瘤', 'carcinoma', 'TCGA'],
        },
        '心肌模板': {
            'keywords': ['心肌梗死', 'MI/R', '心肌缺血再灌注', 'Langendorff'],
            'excludes': ['心肌', '心脏', 'cardiac', 'myocard'],
        },
        '糖尿病模板': {
            'keywords': ['STZ诱导', 'db/db小鼠', 'ob/ob小鼠', '高糖培养'],
            'excludes': ['糖尿病', 'diabetes', 'diabetic', 'DM'],
        },
        '临床统计模板': {
            'keywords': ['Cox回归', 'Kaplan-Meier', '生存曲线', 'OS分析'],
            'excludes': ['生存', 'survival', 'prognosis', '预后', 'Cox'],
        },
    }

    full_text = '\n'.join(report_lines)
    folder_lower = folder_name.lower()

    # 构建排除区域：参考文献段落和 KEGG/GO 通路名不应触发模板残留告警
    # 识别参考文献区域（从"参考文献"或"References"开始到末尾）
    ref_start_idx = len(report_lines)
    for i, line in enumerate(report_lines):
        if re.match(r'^\s*(参考文献|References|REFERENCES)', line):
            ref_start_idx = i
            break
    body_text = '\n'.join(report_lines[:ref_start_idx])

    # KEGG/GO 通路名正则：排除出现在典型通路名格式中的关键词
    # 如 "Breast cancer"、"Chemical carcinogenesis" 等是合法通路名
    kegg_go_pattern = re.compile(
        r'(?:pathway|signaling|metabolism|biosynthesis|carcinogenesis|degradation|'
        r'resistance|interaction|response|proliferation|differentiation|apoptosis)'
        r'[^.\n]{0,50}',
        re.IGNORECASE
    )

    for group_name, group_cfg in _TEMPLATE_RESIDUAL_GROUPS.items():
        # 如果项目本身就是该类型，跳过（检查文件夹名 + 报告章节标题）
        # 这样即使文件夹名没有关键词，只要报告中有相关分析模块也会跳过
        if any(ex.lower() in folder_lower for ex in group_cfg['excludes']):
            continue
        # 扩展排除：检查报告章节标题是否包含排除关键词
        section_titles = ' '.join(
            sec.get('title', '') for sec in structure.get('sections', [])
            if isinstance(sec, dict)
        ).lower()
        if any(ex.lower() in section_titles for ex in group_cfg['excludes']):
            continue
        for kw in group_cfg['keywords']:
            kw_pattern = re.compile(re.escape(kw), re.IGNORECASE)
            # 只搜索正文（排除参考文献区域）
            matches = kw_pattern.findall(body_text)
            if not matches:
                continue

            # 过滤掉出现在 KEGG/GO 通路名上下文中的匹配
            # 逐行检查，只保留不在通路名上下文中的匹配
            real_matches = 0
            for line in report_lines[:ref_start_idx]:
                if kw_pattern.search(line):
                    # 检查该行是否包含典型通路名上下文
                    line_lower = line.lower()
                    in_pathway_context = bool(kegg_go_pattern.search(line_lower))
                    # 检查是否在富集分析结果段落中（含 GO/KEGG 等标识）
                    in_enrichment = any(tag in line_lower for tag in [
                        'kegg', 'go ', 'gene ontology', 'pathway', 'enrichment',
                        'signaling', 'p.adjust', 'qvalue', 'hsa0', 'R-HSA-',
                    ])
                    if not in_pathway_context and not in_enrichment:
                        real_matches += 1

            if real_matches > 0:
                # 模板残留属严重质量问题，升级为 CRITICAL（Iter5）
                issues.append({
                    'code': 'MC-006',
                    'severity': CRITICAL,
                    'message': f"疑似模板残留: 发现'{kw}'（来自{group_name}）出现{real_matches}次（正文中，排除通路名和参考文献）",
                    'detail': f'当前项目不属于{group_name}适用范围，可能是复制粘贴残留',
                })
            elif len(matches) > 0:
                # 只在通路名/参考文献中出现，降级为 INFO
                issues.append({
                    'code': 'MC-006',
                    'severity': INFO,
                    'message': f"'{kw}'出现{len(matches)}次，但均在KEGG/GO通路名或参考文献中，非模板残留",
                    'detail': f'来自{group_name}检查组，上下文判定为合法引用',
                })

    return issues


def check_numeric_sums(structure: dict, report_lines: list[str]) -> list[dict]:
    """MC-007: 数字求和校验

    检测 "共X个=上调Y+下调Z" 或 "共N例（实验组n1+对照组n2）" 类型的数字一致性。
    """
    issues = []

    # 模式1: "共X个差异/DEG/基因...上调Y...下调Z"（同一段落内）
    # 在相邻行或同行中搜索
    for idx, line in enumerate(report_lines):
        # 合并当前行和下一行作为上下文
        context = line
        if idx + 1 < len(report_lines):
            context += ' ' + report_lines[idx + 1]

        # 模式: "共N个DEG（上调X，下调Y）"
        m = re.search(
            r'(?:共|合计|总计|筛选出|获得|鉴定|得到)\s*(\d+)\s*(?:个|条)?\s*'
            r'(?:差异|DEGs?|基因|靶点|候选).*?'
            r'(?:上调|上升|高表达)\s*(\d+).*?'
            r'(?:下调|下降|低表达)\s*(\d+)',
            context
        )
        if m:
            total = int(m.group(1))
            up = int(m.group(2))
            down = int(m.group(3))
            if total != up + down:
                issues.append({
                    'code': 'MC-007',
                    'severity': CRITICAL,
                    'message': f"数字不一致: 共{total} ≠ 上调{up} + 下调{down} = {up + down}",
                    'line': idx + 1,
                    'context': line.strip()[:100],
                })

        # 模式: "共N例（实验组X例，对照组Y例）"——仅匹配明确含"例"的分组
        m2 = re.search(
            r'(?:共|合计|总计|纳入)\s*(\d+)\s*例'
            r'[^。；\n]{0,30}?(\d+)\s*例'
            r'[^。；\n]{0,30}?(\d+)\s*例',
            context
        )
        if m2:
            total_s = int(m2.group(1))
            part1 = int(m2.group(2))
            part2 = int(m2.group(3))
            if total_s != part1 + part2 and total_s > 10:
                issues.append({
                    'code': 'MC-007',
                    'severity': WARNING,
                    'message': f"样本数可能不一致: 共{total_s}例 vs {part1}例+{part2}例={part1 + part2}",
                    'line': idx + 1,
                    'context': line.strip()[:100],
                    'detail': '请AI确认是否为分组求和关系',
                })

    return issues


def check_code_forensics(proj_struct: dict, project_dir: Path, report_lines: list[str] = None) -> list[dict]:
    """MC-008: 代码级交叉校验（基于 project_structure.json）

    利用 parse_project_structure.py 提取的代码信息做进一步检查：
    1. 代码中出现外来项目编号
    2. 代码中引用的 GEO 数据集在 rawdata 目录中不存在
    3. 代码中引用了报告未提及的 GEO（跨项目代码污染）
    """
    issues = []

    # 1. 代码中的外来项目 ID
    for ref in proj_struct.get('project_id_references', []):
        if ref.get('is_foreign'):
            files = ref.get('found_in', [])
            foreign_project_id = ref.get('project_id') or ref.get('id') or ref.get('value') or 'UNKNOWN'
            issues.append({
                'code': 'MC-008',
                'severity': CRITICAL,
                'message': f"代码中发现外来项目编号: {foreign_project_id}",
                'detail': f"出现在: {', '.join(files[:5])}",
            })

    # 收集报告中提及的所有 GEO ID（用于交叉检测）
    report_gse = set()
    if report_lines:
        gse_pat = re.compile(r'\b(GSE\d{4,8}|E-MTAB-\d{3,6})\b')
        for line in report_lines:
            for m in gse_pat.finditer(line):
                report_gse.add(m.group(1))

    # 2. 代码中的 GEO 引用 vs rawdata 目录 + 报告交叉检测
    for geo in proj_struct.get('geo_references', []):
        geo_id = geo.get('geo_id') or geo.get('id', '')
        in_code = geo.get('found_in_code', [])
        in_dirs = geo.get('found_in_dirs', False)
        in_report = geo_id in report_gse

        if in_code and not in_dirs and not in_report:
            # 代码引用了，但 rawdata 和报告中都没有 → 高度可疑跨项目残留
            issues.append({
                'code': 'MC-008',
                'severity': MAJOR,
                'message': f"代码引用 {geo_id}，但报告和 rawdata 中均未提及（疑似跨项目代码污染）",
                'detail': f"引用代码: {', '.join(in_code[:3])}，此数据集可能来自其他项目的代码复制",
            })
        elif in_code and not in_dirs and in_report:
            # 代码和报告都有但 rawdata 没有 → 可能在线下载
            issues.append({
                'code': 'MC-008',
                'severity': INFO,
                'message': f"代码引用 {geo_id} 但 rawdata 目录中无对应文件夹",
                'detail': f"报告中已提及此数据集，可能为在线下载模式",
            })

    return issues


def check_parameter_consistency(report_struct: dict, proj_struct: dict) -> list[dict]:
    """MC-009: 报告描述参数 vs 代码实际参数交叉校验

    比较报告方法部分描述的关键阈值与代码中实际使用的参数：
    1. DEG logFC 阈值
    2. DEG adj_p / FDR 阈值
    3. 单细胞聚类 resolution
    4. WGCNA soft threshold 有无记录
    """
    issues = []
    if not proj_struct:
        return issues

    param_idx = proj_struct.get('parameter_index', {})
    report_nums = report_struct.get('numbers_in_context', [])

    # --- 辅助：从报告提取特定类型的数值 ---
    def _report_vals(num_type: str, min_val=None, max_val=None) -> set:
        vals = set()
        for n in report_nums:
            if n['type'] != num_type:
                continue
            try:
                v = float(n['value'])
                if min_val is not None and v <= min_val:
                    continue
                if max_val is not None and v >= max_val:
                    continue
                vals.add(v)
            except (ValueError, TypeError):
                pass
        return vals

    def _code_vals(param_key: str, file_filter=None) -> set:
        vals = set()
        for entry in param_idx.get(param_key, []):
            try:
                v = float(entry['value'])
                if file_filter and not file_filter(entry.get('file', '')):
                    continue
                vals.add(v)
            except (ValueError, TypeError):
                pass
        return vals

    def _is_deg_file(f: str) -> bool:
        fl = f.lower()
        return 'deg' in fl or '01_' in fl

    # 1. logFC 阈值: 报告 vs DEG 代码
    report_logfc = _report_vals('log2fc_threshold', min_val=0)
    code_deg_logfc = _code_vals('logFC_threshold', _is_deg_file)
    if not code_deg_logfc:
        # 如果找不到 DEG 专用，取所有正值
        code_deg_logfc = {v for v in _code_vals('logFC_threshold') if v > 0}

    if report_logfc and code_deg_logfc:
        for rv in report_logfc:
            if rv not in code_deg_logfc:
                issues.append({
                    'code': 'MC-009',
                    'severity': MAJOR,
                    'message': f"报告描述 logFC 阈值 {rv}，但 DEG 代码中使用的是 {sorted(code_deg_logfc)}",
                    'detail': '报告描述的筛选标准与代码实际参数不一致',
                })

    # 2. adj_p / FDR 阈值: 报告 vs DEG 代码
    report_fdr = _report_vals('fdr_value', min_val=0, max_val=1)
    code_deg_adjp = _code_vals('adj_p_threshold', _is_deg_file)
    if not code_deg_adjp:
        code_deg_adjp = _code_vals('adj_p_threshold')

    if report_fdr and code_deg_adjp:
        for rv in report_fdr:
            if rv not in code_deg_adjp:
                issues.append({
                    'code': 'MC-009',
                    'severity': MAJOR,
                    'message': f"报告描述 FDR/adj.P 阈值 {rv}，但 DEG 代码中使用的是 {sorted(code_deg_adjp)}",
                    'detail': '筛选标准口径不一致',
                })

    # 3. 聚类 resolution: 报告 vs 代码
    report_nums_text = ' '.join(
        n['context'] for n in report_nums
        if 'resolution' in n.get('context', '').lower()
    )
    report_res = set()
    for m in re.finditer(r'resolution\s*[=:：]\s*([\d.]+)', report_nums_text, re.IGNORECASE):
        try:
            report_res.add(float(m.group(1)))
        except ValueError:
            pass

    code_res = _code_vals('clustering_resolution')
    if report_res and code_res:
        for rv in report_res:
            if rv not in code_res:
                issues.append({
                    'code': 'MC-009',
                    'severity': WARNING,
                    'message': f"报告描述 resolution={rv}，但代码中使用的是 {sorted(code_res)}",
                    'detail': '聚类分辨率参数不一致',
                })

    return issues


# MC-010 方法-包名映射: {报告中关键词 → 期望R/Python包名列表}
_METHOD_PACKAGE_MAP = {
    # 机器学习
    'LASSO': ['glmnet'],
    'lasso': ['glmnet'],
    '随机森林': ['randomForest', 'ranger'],
    'Random Forest': ['randomForest', 'ranger'],
    'SVM': ['e1071', 'kernlab'],
    '支持向量机': ['e1071', 'kernlab'],
    'XGBoost': ['xgboost'],
    # 加权协表达
    'WGCNA': ['WGCNA'],
    # 单细胞
    'Seurat': ['Seurat'],
    'CellChat': ['CellChat'],
    'monocle': ['monocle', 'monocle3'],
    '拟时序': ['monocle', 'monocle3', 'slingshot'],
    'Pseudotime': ['monocle', 'monocle3', 'slingshot'],
    'AUCell': ['AUCell'],
    'scMetabolism': ['scMetabolism'],
    'SCENIC': ['SCENIC', 'GENIE3'],
    'SingleR': ['SingleR', 'celldex'],
    'harmony': ['harmony'],
    'clustree': ['clustree'],
    # 富集分析
    'GSEA': ['clusterProfiler', 'fgsea'],
    'ssGSEA': ['GSVA', 'gsva'],
    'GSVA': ['GSVA', 'gsva'],
    'GO富集': ['clusterProfiler'],
    'KEGG富集': ['clusterProfiler'],
    # 网络毒理学 / 网络药理学
    'AutoDock': [],  # 外部工具，不需要 R 包
    'Cytoscape': [],
    # 生存分析
    'Cox回归': ['survival', 'survminer'],
    'Kaplan-Meier': ['survival', 'survminer'],
    'KM生存': ['survival', 'survminer'],
    # 免疫浸润
    'CIBERSORT': ['IOBR', 'CIBERSORT'],
    'ssGSEA免疫': ['GSVA'],
    'ESTIMATE': ['estimate', 'IOBR'],
    # 空间转录
    'STdeconvolve': ['STdeconvolve'],
    'SCP': ['SCP'],
}


def check_method_package_consistency(report_lines: list[str], proj_struct: dict) -> list[dict]:
    """MC-010: 报告提及的分析方法 vs 代码中实际加载的包

    检查报告中描述的分析方法是否有对应的 R/Python 包在代码中被引用。
    """
    issues = []
    if not proj_struct:
        return issues

    all_packages = set(proj_struct.get('metadata', {}).get('all_packages', []))
    if not all_packages:
        return issues

    report_text = '\n'.join(report_lines)

    for method_keyword, expected_pkgs in _METHOD_PACKAGE_MAP.items():
        if not expected_pkgs:
            continue  # 外部工具，跳过
        if method_keyword not in report_text:
            continue

        # 检查是否有至少一个期望包存在
        found = any(pkg in all_packages for pkg in expected_pkgs)
        if not found:
            issues.append({
                'code': 'MC-010',
                'severity': WARNING,
                'message': f"报告提及 '{method_keyword}'，但代码中未找到对应包 {expected_pkgs}",
                'detail': f"可能使用了替代包或方法名与实际不符",
            })

    return issues


def check_hardcoded_paths(proj_struct: dict) -> list[dict]:
    """MC-011: 代码中硬编码绝对路径检测

    检查代码文件的 IO 引用中是否包含硬编码的绝对路径。
    这类路径默认只作为背景提示，不因审核机器不同而单独升级为实质问题。
    """
    issues = []
    if not proj_struct:
        return issues

    # 收集所有绝对路径及其来源
    abs_paths = {}  # {路径前缀 → [文件列表]}
    for cf in proj_struct.get('code_files', []):
        for io_ref in cf.get('io_references', []):
            p = io_ref.get('path', '')
            # 检查 Linux 绝对路径
            if p.startswith('/') and not p.startswith('//'):
                # 取路径前缀（到第3层）作为key避免重复
                parts = p.split('/')
                prefix = '/'.join(parts[:4]) if len(parts) > 3 else p
                abs_paths.setdefault(prefix, set()).add(cf['path'])
            # 检查 Windows 绝对路径
            elif len(p) > 2 and p[1] == ':':
                prefix = p[:20]
                abs_paths.setdefault(prefix, set()).add(cf['path'])

    for prefix, files in abs_paths.items():
        files_str = ', '.join(sorted(files)[:3])
        issues.append({
            'code': 'MC-011',
            'severity': INFO,
            'message': f"代码中硬编码绝对路径: {prefix}...",
            'detail': f"出现在: {files_str}（共{len(files)}个文件，默认仅作背景记录；需AI判断是否暴露错误项目/错误来源）",
        })

    return issues


def check_report_file_references(report_lines: list[str], project_dir: Path) -> list[dict]:
    """MC-012: 报告引用结果文件/目录存在性验证

    检查报告中提到的"结果文件见XXX"/"详见XXX"是否在项目目录中实际存在。
    """
    issues = []

    # 提取报告中引用的文件/目录名
    ref_pattern = re.compile(
        r'(?:结果文件[见：:]\s*(?:文件夹)?|详见结果文件[：:]?\s*|'
        r'详见文件[：:]?\s*|见结果文件[夹：:]\s*)'
        r'([0-9]{2}_[A-Za-z_]+(?:/[^\s，。；）\)]*)?)',
    )

    # 也匹配更具体的文件路径引用
    specific_pattern = re.compile(
        r'(?:结果文件|详见)[：:]*\s*([0-9]{2}_[A-Za-z_]+/[\w\-.]+\.\w{2,4})'
    )

    checked_refs = set()

    for idx, line in enumerate(report_lines):
        # 通用目录引用
        for m in ref_pattern.finditer(line):
            ref = m.group(1).rstrip('，。；）)、')
            if ref in checked_refs:
                continue
            checked_refs.add(ref)

            # 检查目录/文件是否存在
            ref_path = project_dir / ref
            if not ref_path.exists():
                # 也尝试在结果文件子目录中查找
                found = False
                for subdir in project_dir.iterdir():
                    if subdir.is_dir() and (subdir / ref.split('/')[0] if '/' in ref else subdir).exists():
                        found = True
                        break
                if not found:
                    issues.append({
                        'code': 'MC-012',
                        'severity': MAJOR,
                        'message': f"报告引用 '{ref}' 但项目目录中不存在",
                        'line': idx + 1,
                        'context': line.strip()[:100],
                        'detail': '报告声称的结果文件/目录缺失',
                    })

        # 具体文件引用
        for m in specific_pattern.finditer(line):
            ref = m.group(1).rstrip('，。；）)')
            if ref in checked_refs:
                continue
            checked_refs.add(ref)

            ref_path = project_dir / ref
            if not ref_path.exists():
                issues.append({
                    'code': 'MC-012',
                    'severity': MAJOR,
                    'message': f"报告引用具体文件 '{ref}' 但不存在",
                    'line': idx + 1,
                    'context': line.strip()[:100],
                    'detail': '报告声称的具体结果文件缺失',
                })

    return issues


def check_delivery_completeness(proj_struct: dict, structure: dict) -> list[dict]:
    """MC-014: 交付完整性检测

    检查：
    1. 零代码文件交付（项目有多个分析模块但无代码 → CRITICAL）
    2. 模块缺少数据文件（有代码但无 CSV/数据文件 → WARNING）
    """
    issues = []
    metadata = proj_struct.get('metadata', {})
    total_code = metadata.get('total_code_files', 0)
    total_modules = metadata.get('total_modules', 0)

    # 1. 零代码检测
    if total_code == 0 and total_modules > 0:
        issues.append({
            'code': 'MC-014',
            'severity': CRITICAL,
            'message': f"项目包含 {total_modules} 个分析模块，但未交付任何代码文件",
            'detail': '缺少代码导致分析结果完全不可复现，应要求补充所有 R/Python 脚本',
        })

    # 2. 模块无数据文件检测
    modules = proj_struct.get('modules', [])
    for mod in modules:
        if isinstance(mod, dict):
            code_count = mod.get('code_files', 0)
            data_count = mod.get('data_files', 0)
            name = mod.get('name', mod.get('dir_name', ''))
            # 有代码但无数据，可能缺少分析结果 CSV
            if code_count > 0 and data_count == 0:
                issues.append({
                    'code': 'MC-014',
                    'severity': WARNING,
                    'message': f"模块 '{name}' 有 {code_count} 个代码文件但无数据/结果文件",
                    'detail': '可能缺少分析结果 CSV 或中间数据文件',
                })

    return issues


def check_deg_table_type(report_lines: list[str], proj_struct: dict) -> list[dict]:
    """MC-015: 区分表达矩阵和正式 DEG 结果表。"""
    issues = []
    if not proj_struct:
        return issues

    report_text = '\n'.join(report_lines)
    if 'DEG' not in report_text and '差异表达' not in report_text:
        return issues

    deg_files = []
    for data_file in proj_struct.get('data_files', []):
        path_lower = data_file.get('path', '').lower()
        if 'deg' in path_lower or '01_deg' in path_lower or '01_degs' in path_lower:
            deg_files.append(data_file)

    if deg_files and not any(_looks_like_deg_result_table(df) for df in deg_files):
        sample = deg_files[0]
        issues.append({
            'code': 'MC-015',
            'severity': MAJOR,
            'message': "DEG 目录下未识别到标准差异分析结果表",
            'detail': f"当前代表文件为 {sample.get('path')}，表头更像表达矩阵而非 logFC/padj 结果表",
        })

    return issues


def check_high_risk_module_consistency(report_lines: list[str], structure: dict, proj_struct: dict, project_dir: Path) -> list[dict]:
    """MC-016: 高风险模块正文-文件-图件一致性检查。"""
    issues = []
    report_text = '\n'.join(report_lines)
    image_lines = [marker.get('line', 0) for marker in structure.get('image_markers', [])]

    md_lines = []
    for idx, line in enumerate(report_lines, start=1):
        if '分子动力学' in line or 'MD模拟' in line or 'Gromacs' in line or 'RMSD' in line or 'RMSF' in line:
            md_lines.append(idx)

    if md_lines:
        md_dirs = _find_matching_dirs(project_dir, ['动力学', 'md'])
        if md_dirs and not any(_dir_has_files(d) for d in md_dirs):
            issues.append({
                'code': 'MC-016',
                'severity': CRITICAL,
                'message': "正文宣称存在分子动力学结果，但对应结果目录为空",
                'detail': f"检测到 MD 相关目录 {', '.join(str(d.relative_to(project_dir)) for d in md_dirs[:3])}，但目录内无文件",
            })

        first_md_line = min(md_lines)
        has_image_after_md = any(line_no >= first_md_line for line_no in image_lines)
        if not has_image_after_md:
            issues.append({
                'code': 'MC-016',
                'severity': CRITICAL,
                'message': "正文存在 MD 结果描述，但提取图片中未见对应图件",
                'detail': f"MD 相关描述最早出现在报告第 {first_md_line} 行之后，但未再出现图片标记",
            })

    if proj_struct:
        code_paths = [cf.get('path', '').lower() for cf in proj_struct.get('code_files', [])]
        if ('分子对接' in report_text or 'docking' in report_text.lower()) and not any(
            any(keyword in path for keyword in ('dock', 'docking', 'autodock', 'vina', 'cbdock'))
            for path in code_paths
        ):
            issues.append({
                'code': 'MC-016',
                'severity': CRITICAL,
                'message': "报告包含分子对接模块，但交付代码中未识别到对接脚本",
                'detail': "高风险模块有结果描述但无代码交付，不能直接视为可复现",
            })
        if ('分子动力学' in report_text or 'md模拟' in report_text.lower() or 'gromacs' in report_text.lower()) and not any(
            any(keyword in path for keyword in ('md', 'gromacs', 'dynamics', 'molecular_dynamics'))
            for path in code_paths
        ):
            issues.append({
                'code': 'MC-016',
                'severity': CRITICAL,
                'message': "报告包含分子动力学模块，但交付代码中未识别到 MD 脚本",
                'detail': "高风险模块有结果描述但无代码交付，不能直接视为可复现",
            })

    return issues


def check_docking_md_target_consistency(report_lines: list[str]) -> list[dict]:
    """MC-017: docking 得分表与 MD 选择对象一致性检查。"""
    issues = []
    score_map = {}
    selection_target = None
    score_pattern = re.compile(r'^\s*([A-Z0-9]+)\s*\|.*?\|\s*(-?\d+(?:\.\d+)?)\s*$')
    selection_pattern = re.compile(r'选择\s*([A-Z0-9]+)\s*[-–—]')

    for line in report_lines:
        m = score_pattern.match(line.strip())
        if m:
            try:
                score_map[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
        if selection_target is None and ('分子动力学' in line or 'MD' in line):
            sm = selection_pattern.search(line)
            if sm:
                selection_target = sm.group(1)

    if score_map and selection_target:
        best_target = min(score_map.items(), key=lambda item: item[1])[0]
        if best_target != selection_target:
            issues.append({
                'code': 'MC-017',
                'severity': MAJOR,
                'message': f"MD 选择对象与 docking 最低结合能不一致：最低为 {best_target}，正文选择 {selection_target}",
                'detail': f"得分表：{best_target}={score_map[best_target]}；所选对象：{selection_target}={score_map.get(selection_target, 'NA')}",
            })

    return issues


def check_figure_range_claims(report_lines: list[str], structure: dict) -> list[dict]:
    """MC-018: 检查正文宣称的图号范围是否真的连续存在。"""
    issues = []
    range_pattern = re.compile(r'Fig\.?\s*(\d+)-(\d+)\s*[-~至]\s*Fig\.?\s*(\d+)-(\d+)', re.IGNORECASE)

    for idx, line in enumerate(report_lines, start=1):
        for m in range_pattern.finditer(line):
            prefix1, start_no, prefix2, end_no = m.groups()
            if prefix1 != prefix2:
                continue
            prefix = prefix1
            missing = []
            for n in range(int(start_no), int(end_no) + 1):
                variants = [f'Fig.{prefix}-{n}', f'Fig{prefix}-{n}']
                if not any(any(v in report_line.replace(' ', '') for v in variants) for report_line in report_lines):
                    missing.append(f'Fig.{prefix}-{n}')
            if missing:
                issues.append({
                    'code': 'MC-018',
                    'severity': MAJOR,
                    'message': f"正文宣称图号范围连续，但实际缺少 {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
                    'line': idx,
                    'context': line.strip()[:100],
                    'detail': "这通常意味着图号跳变、图注漏改或正文引用未同步。",
                })

    return issues


def check_figure_numbering_continuity(structure: dict) -> list[dict]:
    """MC-013: 图编号连续性检测

    检测图编号序列中的重复和缺失：
    1. 同一章节前缀下图编号不连续（如 图2.1→图2.3，缺失图2.2）
    2. 同一图编号在不同行/章节中重复出现（排除同行同节的重复引用）
    """
    issues = []
    figure_refs = structure.get('figure_refs', [])
    if not figure_refs:
        return issues

    # 提取图编号的数字部分，按章节前缀分组
    fig_pattern = re.compile(r'图\s*(\d+(?:\.\d+)*)')
    # 收集每个图编号的出现位置 {fig_id: [(line, section), ...]}
    fig_locations: dict[str, list[tuple[int, str]]] = {}
    fig_numbers_by_prefix: dict[str, set[str]] = {}

    for ref in figure_refs:
        fig_id = ref.get('fig_id', '')
        m = fig_pattern.match(fig_id.replace(' ', ''))
        if not m:
            continue
        num_str = m.group(1)  # e.g., "2.1", "2.3"
        line = ref.get('line', 0)
        section = ref.get('in_section', '')

        # 收集位置
        key = num_str
        if key not in fig_locations:
            fig_locations[key] = []
        fig_locations[key].append((line, section))

        # 按章节前缀分组（取最后一个点之前的部分作为前缀）
        parts = num_str.split('.')
        if len(parts) >= 2:
            prefix = '.'.join(parts[:-1])  # e.g., "2" for "2.1"
            if prefix not in fig_numbers_by_prefix:
                fig_numbers_by_prefix[prefix] = set()
            fig_numbers_by_prefix[prefix].add(int(parts[-1]))

    # 检测1：重复图编号（仅跨章节重复才算异常，同章节内多次引用是正常行为）
    for num_str, locations in fig_locations.items():
        unique_sections = set(loc[1] for loc in locations if loc[1])
        if len(unique_sections) > 1:
            lines = sorted(set(loc[0] for loc in locations))
            sections = sorted(unique_sections)
            issues.append({
                'code': 'MC-013',
                'severity': MAJOR,
                'message': f"图编号跨章节重复: 图{num_str} 在 {len(sections)} 个不同章节出现",
                'line': lines[0],
                'detail': f"涉及章节: {', '.join(sections[:5])}",
            })

    # 检测2：图编号不连续（同一前缀下缺失编号）
    for prefix, numbers in fig_numbers_by_prefix.items():
        if len(numbers) < 2:
            continue
        min_n, max_n = min(numbers), max(numbers)
        expected = set(range(min_n, max_n + 1))
        missing = sorted(expected - numbers)
        if missing:
            missing_ids = [f"图{prefix}.{n}" for n in missing[:10]]
            severity = CRITICAL if len(missing) >= 3 else WARNING
            issues.append({
                'code': 'MC-013',
                'severity': severity,
                'message': f"图编号不连续: 图{prefix}.x 系列缺少 {len(missing)} 个编号（{', '.join(missing_ids[:5])}{'...' if len(missing) > 5 else ''}）",
                'line': 0,
                'detail': f"已有编号: {sorted(numbers)}",
            })

    return issues


def run_all_checks(structure_path: Path, project_dir: Path) -> dict:
    """执行所有机械检查，返回结构化结果"""

    # 加载预解析 JSON
    structure = json.loads(structure_path.read_text(encoding='utf-8'))

    # 加载报告原文（用于全文搜索型检查）
    report_text_path = structure_path.parent / 'report_text.txt'
    if report_text_path.exists():
        report_lines = report_text_path.read_text(encoding='utf-8').splitlines()
    else:
        # 尝试从 structure metadata 中推断
        src = structure.get('metadata', {}).get('source', '')
        if src and Path(src).exists():
            report_lines = Path(src).read_text(encoding='utf-8').splitlines()
        else:
            report_lines = []

    # 尝试加载项目结构 JSON（由 parse_project_structure.py 生成）
    proj_struct_path = structure_path.parent / 'project_structure.json'
    proj_struct = None
    if proj_struct_path.exists():
        try:
            proj_struct = json.loads(proj_struct_path.read_text(encoding='utf-8'))
        except Exception:
            pass

    # 执行所有检查
    all_issues = []
    all_issues.extend(check_figure_mismatches(structure))
    all_issues.extend(check_chinese_anomalies(structure))
    all_issues.extend(check_section_gaps(structure))
    all_issues.extend(check_modules_vs_directories(structure, project_dir))
    all_issues.extend(check_flowchart_vs_delivery(structure, project_dir, report_lines))
    all_issues.extend(check_copypaste_forensics(structure, project_dir, report_lines))
    all_issues.extend(check_numeric_sums(structure, report_lines))
    if proj_struct:
        all_issues.extend(check_code_forensics(proj_struct, project_dir, report_lines))
        all_issues.extend(check_parameter_consistency(structure, proj_struct))
        all_issues.extend(check_method_package_consistency(report_lines, proj_struct))
        all_issues.extend(check_hardcoded_paths(proj_struct))
        all_issues.extend(check_delivery_completeness(proj_struct, structure))
        all_issues.extend(check_deg_table_type(report_lines, proj_struct))
        all_issues.extend(check_high_risk_module_consistency(report_lines, structure, proj_struct, project_dir))
    else:
        all_issues.extend(check_high_risk_module_consistency(report_lines, structure, proj_struct, project_dir))
    all_issues.extend(check_report_file_references(report_lines, project_dir))
    all_issues.extend(check_figure_numbering_continuity(structure))
    all_issues.extend(check_docking_md_target_consistency(report_lines))
    all_issues.extend(check_figure_range_claims(report_lines, structure))

    # 按严重度排序
    severity_order = {CRITICAL: 0, FATAL: -1, MAJOR: 1, WARNING: 2, INFO: 3}
    all_issues.sort(key=lambda x: (severity_order.get(x['severity'], 9), x.get('line', 0)))

    # 统计
    counts = {}
    for issue in all_issues:
        s = issue['severity']
        counts[s] = counts.get(s, 0) + 1

    return {
        'total_issues': len(all_issues),
        'counts': counts,
        'issues': all_issues,
        'checks_run': [
            'MC-001: 图编号-章节不匹配',
            'MC-002: 中文术语异常',
            'MC-003: 章节编号跳号',
            'MC-004: 报告模块 vs 交付目录',
            'MC-005: 流程图方法 vs 交付物',
            'MC-006: 复制粘贴残留',
            'MC-007: 数字求和校验',
            'MC-008: 代码级交叉校验',
            'MC-009: 报告参数vs代码参数',
            'MC-010: 方法-包名一致性',
            'MC-011: 硬编码绝对路径',
            'MC-012: 报告引用文件存在性',
            'MC-013: 图编号连续性',
            'MC-014: 交付完整性',
            'MC-015: DEG table type detection',
            'MC-016: high-risk text-file-image consistency',
            'MC-017: docking to MD target consistency',
            'MC-018: figure range continuity claims',
        ],
    }


def format_report(result: dict) -> str:
    """格式化为可读报告"""
    lines = []
    lines.append("# 机械检查报告")
    lines.append("")
    lines.append(f"共发现 **{result['total_issues']}** 个问题：")
    for sev in [CRITICAL, MAJOR, WARNING, INFO]:
        cnt = result['counts'].get(sev, 0)
        if cnt > 0:
            icon = {'CRITICAL': '🔴', 'MAJOR': '🟠', 'WARNING': '🟡', 'INFO': '🔵'}[sev]
            lines.append(f"- {icon} {sev}: {cnt}")
    lines.append("")

    current_code = ''
    for issue in result['issues']:
        if issue['code'] != current_code:
            current_code = issue['code']
            lines.append(f"\n## {current_code}")
            lines.append("")

        sev_icon = {'CRITICAL': '🔴', 'MAJOR': '🟠', 'WARNING': '🟡', 'INFO': '🔵'}.get(issue['severity'], '⚪')
        loc = f"L{issue['line']}" if issue.get('line') else ''
        lines.append(f"- {sev_icon} [{loc}] {issue['message']}")
        if issue.get('detail'):
            lines.append(f"  - {issue['detail']}")
        if issue.get('context'):
            ctx = issue['context'][:80]
            lines.append(f"  - 上下文: `{ctx}`")

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    structure_path = Path(sys.argv[1])
    project_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else structure_path.with_name('mechanical_check_result.json')

    if not structure_path.exists():
        print(f"ERROR: {structure_path} 不存在")
        sys.exit(1)
    if not project_dir.exists():
        print(f"ERROR: {project_dir} 不存在")
        sys.exit(1)

    result = run_all_checks(structure_path, project_dir)

    # 保存 JSON
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"结果: {out_path}")

    # 打印可读报告
    print("\n" + format_report(result))


if __name__ == '__main__':
    main()
