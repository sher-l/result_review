"""报告结构预解析器：从 report_text.txt 提取结构化索引

将报告文本转化为机器可读的结构化数据，供后续机械检查和 AI 审查使用。

用法:
    python parse_report_structure.py <report_text.txt路径> [输出JSON路径]

输出 JSON 包含:
    - sections: 章节树（编号、标题、起止行）
    - figure_refs: 图引用（编号、所在章节、是否匹配）
    - table_refs: 表引用
    - numbers_in_context: 关键数字（基因数、样本数、p值等）
    - gene_names: 基因名清单
    - database_refs: 数据库引用
    - image_markers: 内联图片标记位置
    - section_numbering_gaps: 章节编号跳号
"""
import json
import re
import sys
from pathlib import Path


def parse_sections(lines: list[str]) -> list[dict]:
    """提取章节结构：支持 1.2.16、2.1、第一章 等格式"""
    sections = []
    # 匹配 "X.Y.Z 标题" 或 "X.Y 标题" 或 "X 标题"
    sec_pattern = re.compile(r'^(\d+(?:\.\d+)*)\s+(.+?)$')
    for i, line in enumerate(lines):
        m = sec_pattern.match(line.strip())
        if m:
            sections.append({
                'id': m.group(1),
                'title': m.group(2).strip(),
                'line': i + 1,  # 1-based
            })
    # 计算每个 section 的结束行
    for j in range(len(sections)):
        if j + 1 < len(sections):
            sections[j]['line_end'] = sections[j + 1]['line'] - 1
        else:
            sections[j]['line_end'] = len(lines)
    return sections


def _get_section_for_line(sections: list[dict], line_num: int) -> str | None:
    """根据行号找到所在章节编号"""
    for sec in reversed(sections):
        if line_num >= sec['line']:
            return sec['id']
    return None


def parse_figure_refs(lines: list[str], sections: list[dict]) -> list[dict]:
    """提取所有图引用并检查章节匹配"""
    refs = []
    # 匹配 "图X.Y.Z"、"图X.Y"、"Figure X"、"Fig. X"
    fig_pattern = re.compile(r'(?:图|Figure|Fig\.?)\s*(\d+(?:\.\d+)*)', re.IGNORECASE)
    for i, line in enumerate(lines):
        for m in fig_pattern.finditer(line):
            fig_id = m.group(1)
            line_num = i + 1
            in_section = _get_section_for_line(sections, line_num)

            # 检查匹配：图2.6.1 应在 2.6 或 2.6.x 的 section 中 
            mismatch = False
            if in_section and '.' in fig_id:
                # 图编号的前缀（去掉最后一级）应和 section 的主编号匹配
                fig_parts = fig_id.split('.')
                sec_parts = in_section.split('.')
                if len(fig_parts) >= 2 and len(sec_parts) >= 2:
                    # 图2.6.1 的前缀 "2.6" 应该和 section "2.6" 匹配
                    fig_prefix = '.'.join(fig_parts[:2])
                    sec_prefix = '.'.join(sec_parts[:2])
                    if fig_prefix != sec_prefix:
                        mismatch = True

            refs.append({
                'fig_id': f'图{fig_id}',
                'raw_match': m.group(0),
                'line': line_num,
                'in_section': in_section,
                'mismatch': mismatch,
                'context': line.strip()[:100],
            })
    return refs


def parse_table_refs(lines: list[str], sections: list[dict]) -> list[dict]:
    """提取所有表引用"""
    refs = []
    tbl_pattern = re.compile(r'(?:表|Table)\s*(\d+(?:\.\d+)*)', re.IGNORECASE)
    for i, line in enumerate(lines):
        for m in tbl_pattern.finditer(line):
            line_num = i + 1
            refs.append({
                'table_id': f'表{m.group(1)}',
                'raw_match': m.group(0),
                'line': line_num,
                'in_section': _get_section_for_line(sections, line_num),
                'context': line.strip()[:100],
            })
    return refs


def parse_numbers(lines: list[str]) -> list[dict]:
    """提取关键数字上下文（基因数、样本数、p值、AUC等）"""
    results = []
    # 匹配"共X个"、"X个基因"、"X个样本"、"N例"、"AUC=X"、"p<X"
    patterns = [
        (re.compile(r'(\d+)\s*个(?:基因|DEGs?|差异|上调|下调|显著|靶点|交集|候选|核心)'), 'gene_count'),
        (re.compile(r'(?:共|总计|合计|包括|其中)\s*(\d+)\s*(?:个|例|条|项|种|对)'), 'total_count'),
        (re.compile(r'(\d+)\s*例'), 'sample_count'),
        (re.compile(r'(?:上调|上升|高表达).*?(\d+)'), 'upregulated'),
        (re.compile(r'(?:下调|下降|低表达).*?(\d+)'), 'downregulated'),
        (re.compile(r'AUC\s*[=≈]\s*([\d.]+)', re.IGNORECASE), 'auc_value'),
        (re.compile(r'(?:p|P)\s*[<>=]\s*([\d.eE-]+)'), 'p_value'),
        (re.compile(r'(?:adj\.?P\.?Val|FDR|q\.?value)\s*[<>=]\s*([\d.eE-]+)', re.IGNORECASE), 'fdr_value'),
        (re.compile(r'\|?\s*log2\s*(?:FC|FoldChange|Fold Change)\s*\|?\s*[><=]\s*([\d.]+)', re.IGNORECASE), 'log2fc_threshold'),
    ]
    for i, line in enumerate(lines):
        for pattern, num_type in patterns:
            for m in pattern.finditer(line):
                results.append({
                    'value': m.group(1),
                    'type': num_type,
                    'line': i + 1,
                    'context': line.strip()[:120],
                })
    return results


def parse_gene_names(lines: list[str]) -> list[dict]:
    """提取基因名（大写字母+数字，长度2-15）"""
    genes = {}
    # 标准基因名模式：METTL3, TP53, IGFBP1, HLA-A, MT-ND1
    gene_pattern = re.compile(r'\b([A-Z][A-Z0-9]{1,14}(?:-[A-Z0-9]+)?)\b')
    # 排除常见非基因词
    exclude = {
        'THE', 'AND', 'FOR', 'NOT', 'ALL', 'ARE', 'BUT', 'CAN', 'DID', 'GET',
        'HAS', 'HAD', 'HER', 'HIM', 'HIS', 'HOW', 'ITS', 'LET', 'MAY', 'NEW',
        'NOW', 'OLD', 'OUR', 'OUT', 'OWN', 'SAY', 'SHE', 'TOO', 'USE', 'WAY',
        'WHO', 'BOY', 'DAY', 'EYE', 'FAR', 'FEW', 'GOT', 'HAS', 'CAR', 'DEG',
        'UC', 'VS', 'RNA', 'DNA', 'PCA', 'UMAP', 'CSV', 'PDF', 'PNG', 'RDS',
        'KEGG', 'GO', 'GSEA', 'WGCNA', 'LASSO', 'ROC', 'AUC', 'SVM', 'RF',
        'PPI', 'DEGs', 'DEG', 'ML', 'DCA', 'VIF', 'HR', 'OR', 'CI', 'SD',
        'FC', 'FDR', 'QC', 'GEO', 'GSE', 'TCGA', 'GWAS', 'MR', 'MD', 'RMSD',
        'STRING', 'OMIM', 'CTD', 'IMAGE', 'VERSION', 'FATAL', 'CRITICAL',
        'MAJOR', 'WARNING', 'INFO', 'PASS', 'FAIL', 'TRUE', 'FALSE', 'NULL',
        'TOP', 'ADJ', 'LOG', 'RCTD', 'SCT', 'SEURAT',
    }
    for i, line in enumerate(lines):
        for m in gene_pattern.finditer(line):
            name = m.group(1)
            if name in exclude or len(name) < 3:
                continue
            if name not in genes:
                genes[name] = {'name': name, 'first_line': i + 1, 'count': 0}
            genes[name]['count'] += 1
    return sorted(genes.values(), key=lambda x: x['first_line'])


def parse_database_refs(lines: list[str]) -> list[dict]:
    """提取数据库引用"""
    refs = []
    db_names = [
        'STRING', 'GeneCards', 'OMIM', 'UniProt', 'PDB', 'PubChem',
        'SwissTargetPrediction', 'CTD', 'TCMSP', 'DGIdb', 'DrugBank',
        'PharmGKB', 'BindingDB', 'CB-DOCK2', 'AutoDock', 'COREMINE',
        'FerrDb', 'MSigDB', 'HADb', 'GEO', 'TCGA', 'CMap', 'CMAP',
        'DisGeNET', 'TTD', 'STITCH', 'SuperPred', 'SEA',
    ]
    db_pattern = re.compile(
        r'\b(' + '|'.join(re.escape(d) for d in db_names) + r')\b\s*(?:\[(\d+)\])?',
        re.IGNORECASE
    )
    for i, line in enumerate(lines):
        for m in db_pattern.finditer(line):
            refs.append({
                'database': m.group(1),
                'ref_num': m.group(2),
                'line': i + 1,
                'context': line.strip()[:100],
            })
    return refs


def parse_image_markers(lines: list[str]) -> list[dict]:
    """提取内联图片标记及其上下文"""
    markers = []
    img_pattern = re.compile(r'\[IMAGE:\s*(image_\d+\.\w+)\]')
    for i, line in enumerate(lines):
        for m in img_pattern.finditer(line):
            context_before = lines[i-1].strip() if i > 0 else ''
            context_after = lines[i+1].strip() if i + 1 < len(lines) else ''
            markers.append({
                'file': m.group(1),
                'line': i + 1,
                'context_before': context_before[:100],
                'context_after': context_after[:100],
                'inline_text': line.replace(m.group(0), '').strip()[:50],
            })
    return markers


def detect_chinese_anomalies(lines: list[str]) -> list[dict]:
    """检测中文关键术语异常（缺字、错字、截断）"""
    anomalies = []

    # 关键术语及其可能的缺字/错字变体
    term_checks = [
        # (错误模式, 正确术语, 描述)
        (r'(?<!免)疫细胞', '免疫细胞', '缺"免"字'),
        (r'(?<!死)亡相关', '死亡相关', '缺"死"字'),
        (r'(?<!转)录组', '转录组', '缺"转"字'),
        (r'(?<!磷)酸化', '磷酸化', '缺"磷"字'),
        (r'(?<!巨)噬细胞', '巨噬细胞', '缺"巨"字'),
        (r'(?<!炎)症性', '炎症性', '缺"炎"字'),
        (r'(?<!表)达基因', '表达基因', '缺"表"字'),
        (r'局势细胞', '巨噬细胞', '输入法错误'),
        (r'异常色质', '异染色质', '错字'),
        (r'(?<!染)色质(?!体)', '染色质', '可能缺"染"字'),
        (r'(?<!蛋)白互作', '蛋白互作', '缺"蛋"字'),
        (r'(?<!细)胞凋亡', '细胞凋亡', '缺"细"字'),
        (r'(?<!基)因表达', '基因表达', '缺"基"字'),
        (r'(?<!细)胞增殖', '细胞增殖', '缺"细"字'),
        (r'(?<!细)胞分化', '细胞分化', '缺"细"字'),
        (r'(?<!细)胞迁移', '细胞迁移', '缺"细"字'),
    ]

    for i, line in enumerate(lines):
        for wrong_pat, correct, desc in term_checks:
            for m in re.finditer(wrong_pat, line):
                # 排除正确用法
                start = max(0, m.start() - 2)
                end = min(len(line), m.end() + 2)
                context = line[start:end]
                if correct in line[max(0, m.start()-5):m.end()+5]:
                    continue  # 完整术语存在，跳过
                anomalies.append({
                    'text': m.group(),
                    'correct': correct,
                    'description': desc,
                    'line': i + 1,
                    'context': line.strip()[:100],
                })

    # 检查段首截断（段落第一个字符是否为中间字符）
    truncation_chars = set('疫录酸噬症达调')  # 常见被截断后的首字
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and stripped[0] in truncation_chars:
            anomalies.append({
                'text': stripped[:6],
                'correct': '?',
                'description': '段首可能截断（首字为常见截断残留字符）',
                'line': i + 1,
                'context': stripped[:80],
            })

    return anomalies


def detect_section_gaps(sections: list[dict]) -> list[dict]:
    """检测章节编号跳号"""
    gaps = []
    for i in range(1, len(sections)):
        prev_id = sections[i-1]['id']
        curr_id = sections[i]['id']
        prev_parts = prev_id.split('.')
        curr_parts = curr_id.split('.')
        # 同级检查：如果位数相同且前缀相同
        if len(prev_parts) == len(curr_parts) and prev_parts[:-1] == curr_parts[:-1]:
            try:
                prev_num = int(prev_parts[-1])
                curr_num = int(curr_parts[-1])
                if curr_num - prev_num > 1:
                    missing = [f"{'.'.join(prev_parts[:-1])}.{n}" if len(prev_parts) > 1
                              else str(n)
                              for n in range(prev_num + 1, curr_num)]
                    gaps.append({
                        'prev': prev_id,
                        'curr': curr_id,
                        'missing': missing,
                        'line': sections[i]['line'],
                    })
            except ValueError:
                pass
    return gaps


def parse_report(text_path: Path) -> dict:
    """主解析入口"""
    lines = text_path.read_text(encoding='utf-8').splitlines()

    sections = parse_sections(lines)
    figure_refs = parse_figure_refs(lines, sections)
    table_refs = parse_table_refs(lines, sections)
    numbers = parse_numbers(lines)
    gene_names = parse_gene_names(lines)
    database_refs = parse_database_refs(lines)
    image_markers = parse_image_markers(lines)
    chinese_anomalies = detect_chinese_anomalies(lines)
    section_gaps = detect_section_gaps(sections)

    # 统计摘要
    fig_mismatches = [f for f in figure_refs if f['mismatch']]

    return {
        'metadata': {
            'source': str(text_path),
            'total_lines': len(lines),
            'total_sections': len(sections),
            'total_figures': len(figure_refs),
            'total_tables': len(table_refs),
            'total_images': len(image_markers),
            'total_genes': len(gene_names),
        },
        'sections': sections,
        'figure_refs': figure_refs,
        'figure_mismatches': fig_mismatches,
        'table_refs': table_refs,
        'numbers_in_context': numbers,
        'gene_names': gene_names,
        'database_refs': database_refs,
        'image_markers': image_markers,
        'chinese_anomalies': chinese_anomalies,
        'section_numbering_gaps': section_gaps,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    text_path = Path(sys.argv[1])
    if not text_path.exists():
        print(f"ERROR: {text_path} 不存在")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else text_path.with_suffix('.structure.json')

    result = parse_report(text_path)

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"结构化索引: {out_path}")
    print(f"  章节: {result['metadata']['total_sections']}")
    print(f"  图引用: {result['metadata']['total_figures']} (不匹配: {len(result['figure_mismatches'])})")
    print(f"  表引用: {len(result['table_refs'])}")
    print(f"  图片: {result['metadata']['total_images']}")
    print(f"  基因: {result['metadata']['total_genes']}")
    print(f"  数据库引用: {len(result['database_refs'])}")
    print(f"  中文异常: {len(result['chinese_anomalies'])}")
    print(f"  章节跳号: {len(result['section_numbering_gaps'])}")


if __name__ == '__main__':
    main()
