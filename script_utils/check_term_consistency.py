#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
术语主题一致性检查器（P0级 - FATAL）

基于项目25YLC105F的发现：肾结石项目使用癌症术语(Tumor/Normal)

FATAL级标准：
- 发现其他疾病类型的特征术语 → FATAL，暴露复制粘贴

作者: 审核框架 v6.5
创建日期: 2026-02-13
基于: TERM_MATCHING_LIBRARY.md
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from base_project_checker import BaseProjectChecker


# ── 癌种缩写交叉检测数据库 ──
# 来自 TERM_MATCHING_LIBRARY.md
CANCER_ABBREVIATIONS = [
    'ACC', 'BLCA', 'BRCA', 'CESC', 'CHOL', 'COAD', 'DLBC', 'ESCA',
    'GBM', 'HNSC', 'KICH', 'KIRC', 'KIRP', 'LAML', 'LGG', 'LIHC',
    'LUAD', 'LUSC', 'MESO', 'OV', 'PAAD', 'PCPG', 'PRAD', 'READ',
    'SARC', 'SKCM', 'STAD', 'TGCT', 'THCA', 'THYM', 'UCEC', 'UCS', 'UVM',
    'HCC', 'NSCLC', 'CRC', 'RCC', 'LSCC', 'PDAC', 'GC',
]

# 同义映射：检测到某缩写时，这些也算正确
CANCER_SYNONYMS = {
    'LIHC': ['HCC'], 'HCC': ['LIHC'],
    'LUSC': ['LSCC', 'NSCLC'], 'LSCC': ['LUSC'],
    'PAAD': ['PDAC'], 'PDAC': ['PAAD'],
    'STAD': ['GC'], 'GC': ['STAD'],
    'COAD': ['CRC'], 'READ': ['CRC'], 'CRC': ['COAD', 'READ'],
    'KIRC': ['RCC'], 'KIRP': ['RCC'], 'KICH': ['RCC'],
    'RCC': ['KIRC', 'KIRP', 'KICH'],
    'LUAD': ['NSCLC'], 'NSCLC': ['LUAD', 'LUSC'],
}


# 术语主题数据库（来自TERM_MATCHING_LIBRARY.md）
TERM_DATABASE = {
    '癌症': {
        'correct': ['Tumor', 'Normal', 'Cancer', 'Malignant', 'Metastasis',
                   'Carcinoma', 'Sarcoma', 'Adenocarcinoma'],
        'wrong': [],  # 癌症是通用术语
        'keywords': ['Tumor', 'Normal', 'Cancer', 'Malignant'],
        'severity_map': {}  # 无特别严重性映射
    },
    '肾结石': {
        'correct': ['Disease', 'Control', 'Randall', 'plaque', 'Kidney', 'stone',
                   'Randall\'s', 'calcification', 'Papillary', 'Ductal'],
        'wrong': ['Tumor', 'Normal', 'Cancer', 'Malignant'],  # 不应使用癌症术语
        'keywords': ['Disease', 'Control', 'Randall', 'plaque'],
        'severity_map': {
            'Tumor': 'FATAL',
            'Normal': 'FATAL',
            'Cancer': 'FATAL',
            'Malignant': 'FATAL'
        }
    },
    '心血管': {
        'correct': ['Cardiac', 'Heart', 'Case', 'Control', 'Myocardial',
                   'Cardiovascular', 'Hypertension'],
        'wrong': ['Tumor', 'Normal', 'Cancer', 'Diabetes'],
        'keywords': ['Cardiac', 'Heart', 'Myocardial', 'cardiovascular'],
        'severity_map': {
            'Tumor': 'FATAL',
            'Normal': 'FATAL',
            'Cancer': 'FATAL'
        }
    },
    '代谢': {
        'correct': ['Disease', 'Control', 'Diabetes', 'Glucose', 'Insulin',
                   'Glucagon', 'Obesity', 'Lipid', 'Cholesterol'],
        'wrong': ['Cardiac', 'Heart', 'Tumor', 'Kidney'],
        'keywords': ['Diabetes', 'Glucose', 'Insulin', 'metabolic'],
        'severity_map': {
            'Tumor': 'FATAL'
        }
    },
    '神经': {
        'correct': ['Disease', 'Control', 'Brain', 'Neuron', 'Neural',
                   'Synapse', 'Neurotransmitter'],
        'wrong': ['Cardiac', 'Heart', 'Tumor', 'Kidney'],
        'keywords': ['Brain', 'Neural', 'neuron', 'synapse'],
        'severity_map': {
            'Tumor': 'FATAL'
        }
    },
    '免疫': {
        'correct': ['Disease', 'Control', 'Inflammation', 'Immune',
                   'Inflammatory', 'Cytokine', 'Chemokine',
                   'Antibody', 'Antigen', 'Normal'],  # Normal 在免疫项目中常用作对照
        'wrong': ['Tumor'],
        'keywords': ['Inflammation', 'immune', 'cytokine', 'antibody'],
        'severity_map': {
            'Tumor': 'FATAL'
        }
    },
    'IBD': {
        'correct': ['Disease', 'Control', 'Inflamed', 'Non-inflamed',
                   'UC', 'CD', 'Healthy', 'Ulcerative', 'Crohn',
                   'Normal'],  # Normal 在 IBD 中常用作对照组标记
        'wrong': ['Tumor', 'Cancer', 'Malignant'],
        'keywords': ['IBD', 'colitis', 'Crohn', 'mucosa', 'intestinal', 'dysbiosis'],
        'severity_map': {
            'Tumor': 'FATAL',
            'Cancer': 'FATAL',
            'Malignant': 'FATAL'
        }
    }
}


class TermConsistencyChecker(BaseProjectChecker):
    """术语主题一致性检查器"""

    def __init__(self, project_path: str, project_type: str, metadata=None, layer0_data: dict = None):
        """
        初始化检查器

        参数:
            project_path: 项目根目录路径
            project_type: 项目疾病类型（如'肾结石', '癌症'）
        """
        super().__init__(project_path, metadata=metadata, layer0_data=layer0_data)
        self.project_type = project_type
        self.errors = []

        if project_type not in TERM_DATABASE:
            # 未知类型不崩溃，标记为跳过
            self._unsupported = True
            self.term_config = None
            return

        self._unsupported = False

        self.term_config = TERM_DATABASE[project_type]

    def check_all(self) -> Dict:
        """统一入口，委托给 check_code_files"""
        return self.check_code_files()

    def check_code_files(self, code_dir: str = None) -> Dict:
        """
        检查代码文件中的术语

        参数:
            code_dir: 代码目录路径（如果为None，自动查找）

        返回:
            {
                'project_type': 项目类型,
                'total_files': 检查文件数,
                'error_files': 有错误的文件数,
                'mismatches': 不匹配术语列表,
                'fatal': 是否为FATAL级
            }
        """
        # 未知类型 → 跳过，不崩溃
        if getattr(self, '_unsupported', False):
            return {
                'project_type': self.project_type,
                'total_files': 0,
                'error_files': 0,
                'issues': [],
                'fatal': False,
                'skipped': True,
                'reason': f'未知项目类型 "{self.project_type}"，术语检查跳过。支持: {list(TERM_DATABASE.keys())}',
            }

        if code_dir is None:
            code_dir = self.find_code_directory()
        else:
            code_dir = Path(code_dir)

        if not code_dir or not code_dir.exists():
            return {
                'project_type': self.project_type,
                'total_files': 0,
                'error_files': 0,
                'issues': [],
                'fatal': False
            }

        # 查找所有代码文件（去重，避免 Windows 大小写不敏感导致重复）
        seen = set()
        all_files = []
        for pattern in ('*.r', '*.R', '*.py'):
            for f in code_dir.glob(pattern):
                key = str(f).lower()
                if key not in seen:
                    seen.add(key)
                    all_files.append(f)

        for file_path in all_files:
            self._check_file(file_path)

        # 癌症项目：额外做癌种缩写交叉检测
        cancer_abbr_result = None
        if self.project_type == '癌症':
            cancer_abbr_result = self.check_cancer_abbreviations()
            if cancer_abbr_result.get('issues'):
                self.errors.extend(cancer_abbr_result['issues'])

        # 判断是否为FATAL
        fatal = any(e.get('severity') == 'FATAL' for e in self.errors)

        result = {
            'project_type': self.project_type,
            'total_files': len(all_files),
            'error_files': len(set(e['file'] for e in self.errors)),
            'issues': self.errors,
            'warnings': self.warnings,
            'fatal': fatal
        }
        if cancer_abbr_result:
            result['cancer_abbreviation_check'] = cancer_abbr_result
        return result

    def check_report_text(self, report_text: str) -> Dict:
        """
        检查报告文本中的术语

        参数:
            report_text: 报告文本内容

        返回:
            {
                'project_type': 项目类型,
                'mismatches': 不匹配术语列表,
                'fatal': 是否为FATAL级
            }
        """
        self.errors = []
        self._check_text_content(report_text, '<报告文本>')

        fatal = any(e.get('severity') == 'FATAL' for e in self.errors)

        return {
            'project_type': self.project_type,
            'issues': self.errors,
            'fatal': fatal
        }

    def _check_file(self, file_path: Path):
        """检查单个文件"""
        try:
            from utils import safe_read_file
            content = safe_read_file(file_path)[0]
            self._check_text_content(content, str(file_path.relative_to(self.project_path)))
        except Exception as e:
            self.warnings.append({
                'file': str(file_path.relative_to(self.project_path)),
                'type': 'read_error',
                'message': f'无法读取文件: {str(e)}'
            })

    def _check_text_content(self, content: str, source: str):
        """检查文本内容中的术语"""
        wrong_terms = self.term_config['wrong']
        lines = content.split('\n')

        # 预编译所有错误术语的正则模式
        patterns = [
            (re.compile(r'\b' + re.escape(wt) + r'\b', re.IGNORECASE), wt)
            for wt in wrong_terms
        ]
        citation_pattern = re.compile(r'(?:Please\s+)?Cite|doi[.:/]|pubmed|et\s+al\.', re.IGNORECASE)

        for line_num, line in enumerate(lines, 1):
            # 跳过注释行（R: #, Python: #）
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # 跳过引用/citation 行（含 Cite/DOI/pubmed/et al.）
            if citation_pattern.search(stripped):
                continue

            for pattern, wrong_term in patterns:
                for match in pattern.finditer(line):
                    # 获取严重性
                    severity = self.term_config['severity_map'].get(
                        wrong_term,
                        'SERIOUS'
                    )

                    self.errors.append({
                        'file': source,
                        'term': match.group(),
                        'position': match.start(),
                        'line': line_num,
                        'context': stripped[:100],
                        'severity': severity,
                        'message': f"发现不匹配术语'{match.group()}' (项目类型: {self.project_type}, 严重性: {severity})"
                    })

    def _find_line_number(self, content: str, position: int) -> int:
        """根据字符位置查找行号"""
        before = content[:position]
        return before.count('\n') + 1

    def _get_context(self, text: str, position: int, window: int = 50) -> str:
        """获取匹配位置的上下文"""
        start = max(0, position - window // 2)
        end = min(len(text), position + window // 2)
        return text[start:end]

    # ── 癌种缩写交叉检测 ──

    def check_cancer_abbreviations(self, expected_cancer: str = None) -> Dict:
        """
        检查项目中癌症类型缩写是否一致。

        当 expected_cancer 为 None 时，从项目路径自动推断。
        返回格式与 check_code_files 兼容。
        """
        if expected_cancer:
            expected = expected_cancer.upper()
        else:
            expected = self._infer_cancer_type()

        if not expected:
            return {'cancer_type': None, 'issues': [], 'fatal': False,
                    'note': '无法推断癌种，跳过缩写检查'}

        # 构建允许集合：expected + 其同义词
        allowed = {expected} | set(CANCER_SYNONYMS.get(expected, []))

        # 所有其他缩写视为异常，仅检查 >=3 字符的缩写（OV/GC 太短易误报）
        forbidden = [a for a in CANCER_ABBREVIATIONS if a not in allowed and len(a) >= 3]
        # 构建一个大正则，一次匹配所有禁用缩写
        if not forbidden:
            return {'cancer_type': expected, 'allowed_abbreviations': sorted(allowed),
                    'files_scanned': 0, 'issues': [], 'fatal': False}
        big_pattern = re.compile(r'\b(' + '|'.join(re.escape(a) for a in forbidden) + r')\b')

        issues = []
        scan_files = self._collect_scannable_files()

        # 1) 扫描文件内容
        for fpath in scan_files:
            try:
                from utils import safe_read_file
                content = safe_read_file(fpath)[0]
            except Exception:
                continue
            for m in big_pattern.finditer(content):
                abbr = m.group(1)
                line_text = self._get_line_at(content, m.start())
                if self._is_false_positive(abbr, line_text):
                    continue
                issues.append({
                    'file': str(fpath.relative_to(self.project_path)),
                    'term': abbr,
                    'expected': expected,
                    'line': self._find_line_number(content, m.start()),
                    'context': self._get_context(content, m.start(), 80),
                    'severity': 'FATAL',
                    'message': f"发现非本项目癌种缩写 '{abbr}'（本项目应为 {expected}，允许: {', '.join(sorted(allowed))}）"
                })

        # 2) 扫描文件名和目录名（无需读取内容，捕获复制粘贴残留）
        seen_names = set()
        item_iter = self.metadata.rglob('*') if self.metadata else self.project_path.rglob('*')
        for item in item_iter:
            name = item.name
            if name in seen_names:
                continue
            seen_names.add(name)
            for m in big_pattern.finditer(name):
                abbr = m.group(1)
                if self._is_false_positive(abbr, name):
                    continue
                issues.append({
                    'file': str(item.relative_to(self.project_path)),
                    'term': abbr,
                    'expected': expected,
                    'line': 0,
                    'context': f'文件/目录名: {name}',
                    'severity': 'FATAL',
                    'message': f"文件名含非本项目癌种缩写 '{abbr}'（本项目应为 {expected}）"
                })
            if len(seen_names) > 2000:
                break

        return {
            'cancer_type': expected,
            'allowed_abbreviations': sorted(allowed),
            'files_scanned': len(scan_files),
            'issues': issues,
            'fatal': bool(issues),
        }

    def _infer_cancer_type(self) -> str:
        """从项目路径名推断癌症缩写类型"""
        folder_name = self.project_path.name.upper()
        # 优先匹配较长的缩写（NSCLC > LUSC）
        sorted_abbrs = sorted(CANCER_ABBREVIATIONS, key=len, reverse=True)
        for abbr in sorted_abbrs:
            if re.search(r'\b' + re.escape(abbr) + r'\b', folder_name):
                return abbr
        # 中文关键词映射
        cn_map = {
            '肝癌': 'LIHC', '肺癌': 'LUAD', '胰腺癌': 'PAAD',
            '胃癌': 'STAD', '乳腺癌': 'BRCA', '结直肠癌': 'COAD',
            '前列腺癌': 'PRAD', '膀胱癌': 'BLCA', '宫颈癌': 'CESC',
            '甲状腺癌': 'THCA', '卵巢癌': 'OV', '肾癌': 'KIRC',
            '黑色素瘤': 'SKCM', '胶质瘤': 'GBM', '食管癌': 'ESCA',
            '头颈癌': 'HNSC', '子宫内膜癌': 'UCEC',
            '非小细胞肺癌': 'NSCLC', '肝细胞癌': 'HCC',
        }
        folder_text = self.project_path.name
        # 优先匹配长词
        for cn, abbr in sorted(cn_map.items(), key=lambda x: len(x[0]), reverse=True):
            if cn in folder_text:
                return abbr
        return ''

    def _collect_scannable_files(self) -> List[Path]:
        """收集所有可扫描的代码和文本文件（跳过大文件）"""
        exts = {'.r', '.R', '.py', '.Rmd', '.rmd', '.txt', '.md'}
        files = []
        max_size = 500_000  # 500KB 上限，避免扫描巨型CSV
        patterns = [f'*{ext}' for ext in exts]
        candidates = self.metadata.find_by_patterns(patterns) if self.metadata else [f for p in patterns for f in self.project_path.rglob(p)]
        for f in candidates:
            try:
                if f.stat().st_size <= max_size:
                    files.append(f)
            except OSError:
                pass
        return files[:200]

    def _get_line_at(self, content: str, pos: int) -> str:
        """返回 pos 所在的完整行"""
        start = content.rfind('\n', 0, pos) + 1
        end = content.find('\n', pos)
        if end == -1:
            end = len(content)
        return content[start:end]

    def _is_false_positive(self, abbr: str, line_text: str) -> bool:
        """过滤已知的误报模式"""
        # 纯注释行
        stripped = line_text.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            # 注释里的缩写不一定是误报，但如果是 READ 这类常用词则跳过
            if abbr in ('READ',):
                return True
        # READ 在R代码中极易误报
        if abbr == 'READ' and re.search(r'read[._]', line_text, re.IGNORECASE):
            return True
        # OV 可能出现在 "over"/"overlap" 等词中，但 \b 已排除大部分
        # ACC 可能出现在 "accuracy" 中
        if abbr == 'ACC' and re.search(r'accur', line_text, re.IGNORECASE):
            return True
        # LGG 在某些上下文中可能出现
        return False

    def generate_report(self) -> str:
        """生成检查报告"""
        result = self.check_code_files()

        report_lines = [
            "# 术语主题一致性检查报告",
            "",
            f"**项目类型**: {result['project_type']}",
            f"**检查文件数**: {result['total_files']}",
            f"**问题文件数**: {result['error_files']}",
            f"**严重性**: {'🔴 FATAL' if result['fatal'] else '✅ 通过' if len(result['issues']) == 0 else '⚠️ 有问题'}",
            ""
        ]

        # 正确术语参考
        report_lines.extend([
            "## 正确术语参考",
            "",
            f"**应使用的术语**: {', '.join(self.term_config['correct'][:5])}...",
            f"**不应使用的术语**: {', '.join(self.term_config['wrong'])}",
            ""
        ])

        if result['issues']:
            report_lines.extend([
                "## 发现的不匹配术语",
                ""
            ])

            # 按严重性分组
            fatal_issues = [e for e in result['issues'] if e['severity'] == 'FATAL']
            serious_issues = [e for e in result['issues'] if e['severity'] == 'SERIOUS']

            if fatal_issues:
                report_lines.extend([
                    "### 🔴 FATAL级问题",
                    ""
                ])
                for i, error in enumerate(fatal_issues, 1):
                    report_lines.extend([
                        f"#### 问题 {i}",
                        f"- **文件**: {error['file']}",
                        f"- **行号**: {error['line']}",
                        f"- **错误术语**: `{error['term']}`",
                        f"- **上下文**: `...{error['context']}...`",
                        ""
                    ])

            if serious_issues:
                report_lines.extend([
                    "### 🟡 严重问题",
                    ""
                ])
                for i, error in enumerate(serious_issues, 1):
                    report_lines.extend([
                        f"#### 问题 {i}",
                        f"- **文件**: {error['file']}",
                        f"- **行号**: {error['line']}",
                        f"- **错误术语**: `{error['term']}`",
                        ""
                    ])

        if result['fatal']:
            report_lines.extend([
                "",
                "## 🔴 FATAL级问题",
                "",
                "**影响**: 暴露代码直接复制自其他项目，质疑分析专业性",
                "**建议**: 立即修正术语，确保使用正确的项目主题术语",
                ""
            ])

        return "\n".join(report_lines)

    def is_fatal(self) -> bool:
        """判断是否为FATAL级问题"""
        result = self.check_code_files()
        return result['fatal']

    @staticmethod
    def detect_project_type(content: str) -> Tuple[str, float]:
        """
        自动检测项目类型

        返回: (项目类型, 置信度)
        """
        scores = {}
        total_terms = sum(len(config['keywords']) for config in TERM_DATABASE.values())

        for project_type, config in TERM_DATABASE.items():
            score = 0
            for keyword in config['keywords']:
                if re.search(r'\b' + re.escape(keyword) + r'\b', content, re.IGNORECASE):
                    score += 1
            confidence = score / len(config['keywords']) if config['keywords'] else 0
            scores[project_type] = (score, confidence)

        # 返回得分最高的
        if scores:
            best_type = max(scores, key=lambda x: scores[x][1])
            return (best_type, scores[best_type][1])
        return ('未知', 0.0)


def main():
    """命令行入口"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='术语主题一致性检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--project-type', required=True,
                      help='项目疾病类型 (支持: 肾结石, 癌症, 心血管, 代谢, 神经, 免疫, IBD)')
    parser.add_argument('--code-dir', help='代码目录路径（可选）')
    parser.add_argument('--output', help='输出报告文件路径')
    parser.add_argument('--auto-detect', action='store_true',
                      help='自动检测项目类型')

    args = parser.parse_args()

    # 自动检测项目类型
    if args.auto_detect:
        # 从报告文件中检测
        report_files = list(Path(args.project_path).glob('报告/*.docx'))
        if report_files:
            # 简化：从第一个docx文件名检测
            project_type, confidence = TermConsistencyChecker.detect_project_type(
                ' '.join(f.name for f in report_files)
            )
            print(f"自动检测项目类型: {project_type} (置信度: {confidence:.2%})")
            project_type = args.project_type or project_type
        else:
            project_type = args.project_type
    else:
        project_type = args.project_type

    try:
        checker = TermConsistencyChecker(args.project_path, project_type)
        report = checker.generate_report()

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"报告已保存到: {args.output}")
        else:
            print(report)

        sys.exit(1 if checker.is_fatal() else 0)

    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
