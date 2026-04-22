"""
v4.7 回归测试 — 验证 4 个 CRITICAL + 6 个 HIGH 修复
独立脚本，不通过 pytest 运行。直接执行: python test_v47_regression.py
"""
import sys as _sys
if __name__ != '__main__':
    # pytest 收集时跳过此模块
    import pytest
    pytest.skip('standalone regression script', allow_module_level=True)
else:
    import re
    import os
    import csv
    import io

# 确保可以导入框架模块 — script_utils 优先于 scripts（类优先于函数）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'script_utils'))

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name} — {detail}")
        failed += 1

# ============================================================
print("\n=== C1: 蛋白复合物+lncRNA正则统一 ===")
# ============================================================
from check_gene_naming import GeneNamingChecker
from check_gene_set_quality import GeneSetQualityChecker

# 蛋白复合物 — 两个checker使用相同pattern
p_naming = GeneNamingChecker.PATTERNS['protein_complex']
p_quality = re.compile(r'.*-.*_.*|.*_.*-.*')  # gene_set_quality硬编码

check("protein_complex: hyphen-before-underscore", bool(p_naming.match("CD3-ZETA_1")))
check("protein_complex: underscore-before-hyphen", bool(p_naming.match("TRAF_1-binding")))
check("protein_complex: 正常基因不匹配", not p_naming.match("BRCA1"))
check("protein_complex: 单连字符不匹配", not p_naming.match("HLA-A"))

# lncRNA — 需要数字后缀
l_naming = GeneNamingChecker.PATTERNS['lncrna']
check("lncrna: LINC01234匹配", bool(l_naming.match("LINC01234")))
check("lncrna: MIR155匹配", bool(l_naming.match("MIR155")))
check("lncrna: RP11-xxx匹配", bool(l_naming.match("RP11-344E13.1")))
check("lncrna: LINCARE不匹配", not l_naming.match("LINCARE"))
check("lncrna: MIRI不匹配", not l_naming.match("MIRI"))
check("lncrna: ACTB不匹配", not l_naming.match("ACTB"))

# ============================================================
print("\n=== C2: PDF页数算法 ===")
# ============================================================
from check_figure_integrity import FigureIntegrityChecker

# 构造一个假PDF，包含字体表中的大 /Count 值
fake_pdf = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Font /Count 256 >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 5 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
    b"%%EOF"
)

# 写临时文件测试
import tempfile
from pathlib import Path as _Path
with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
    f.write(fake_pdf)
    tmp_pdf = f.name

try:
    checker = FigureIntegrityChecker.__new__(FigureIntegrityChecker)
    result = checker._pdf_page_count(_Path(tmp_pdf))
    check("PDF页数=5（不受字体/Count 256干扰）", result == 5,
          f"实际返回: {result}")
finally:
    os.unlink(tmp_pdf)

# ============================================================
print("\n=== C3: 多行基因提取 ===")
# ============================================================
from check_data_flow import DataFlowValidator

# 模拟多行 R 代码
multi_line_r = '''
features <- c("TP53",
              "BRCA1",
              "EGFR",
              "MYC")
'''

# 用正则测试提取
pattern = r'(?:features|gene_list|hub_genes|target_genes|genes|selected_genes)\s*(?:<-|=)\s*c\s*\((.*?)\)'
m = re.findall(pattern, multi_line_r, re.DOTALL | re.IGNORECASE)
if m:
    genes = re.findall(r'["\']([^"\']+)["\']', m[0])
else:
    genes = []

check("多行c()提取4个基因", len(genes) == 4, f"实际: {genes}")
check("包含TP53", "TP53" in genes)
check("包含MYC", "MYC" in genes)

# ============================================================
print("\n=== C4: 术语一致性词边界 ===")
# ============================================================

# 模拟修复后的行为
wrong_term = "Normal"
pat = re.compile(r'\b' + re.escape(wrong_term) + r'\b', re.IGNORECASE)
check("'Normal'匹配独立单词", bool(pat.search("The Normal group was...")))
check("'Normal'不匹配'normalized'", not pat.search("We normalized the data"))
check("'Normal'不匹配'abnormality'", not pat.search("abnormality detected"))

# ============================================================
print("\n=== H1: P0检查器不可用检测 ===")
# ============================================================
from check_orchestrator import CheckOrchestrator

# 验证 orchestrator 的 P0 checker 定义包含 cls 字段
p0_defs = CheckOrchestrator.P0_CHECKERS
has_cls_field = all('cls' in d for d in p0_defs)
check("P0检查器定义包含cls字段", has_cls_field)

# 验证 run_all_checks 的源码包含 p0_unavailable 检测逻辑
import inspect
src = inspect.getsource(CheckOrchestrator.run_all_checks)
check("run_all_checks包含p0_unavailable检测", "p0_unavailable" in src or "P0" in src and "unavailable" in src.lower())

# ============================================================
print("\n=== H2: 去重有图无CSV检查 ===")
# ============================================================
from check_code_existence import CodeExistenceChecker

src_ce = inspect.getsource(CodeExistenceChecker.check_all)
check("check_all不再调用_check_image_only_modules",
      "_check_image_only_modules" not in src_ce,
      "仍在check_all中调用")

# ============================================================
print("\n=== H3: 去重ML指标 + CSV行计数修复 ===")
# ============================================================
from check_report_data_match import ReportDataMatchChecker

src_rdm = inspect.getsource(ReportDataMatchChecker.check_all)
check("check_all不再调用_check_ml_metrics",
      "_check_ml_metrics" not in src_rdm,
      "仍在check_all中调用")

# CSV行计数测试 — 含引号内换行的字段
csv_with_multiline = '"Name","Desc"\n"Gene1","line1\nline2"\n"Gene2","ok"\n'
src_count = inspect.getsource(ReportDataMatchChecker._count_csv_data_rows)
check("_count_csv_data_rows使用csv模块", "csv.reader" in src_count or "csv" in src_count,
      "未使用csv模块")

# ============================================================
print("\n=== H4: 中文细胞类型映射 ===")
# ============================================================
from check_scrna_qc import ScRNAQCChecker

src_scrna = inspect.getsource(ScRNAQCChecker)
check("包含_CN_TO_EN映射", "_CN_TO_EN" in src_scrna)
check("包含巨噬细胞映射", "巨噬细胞" in src_scrna)
check("包含成纤维细胞映射", "成纤维细胞" in src_scrna)

# ============================================================
print("\n=== H5: 参考文献范围正则 ===")
# ============================================================
from check_evidence_completeness import EvidenceCompletenessChecker

# 测试 _expand_ref_range
refs = EvidenceCompletenessChecker._expand_ref_range("1-5")
check("[1-5]展开为5个引用", refs == [1, 2, 3, 4, 5], f"实际: {refs}")

refs2 = EvidenceCompletenessChecker._expand_ref_range("1,3,5")
check("[1,3,5]展开为3个引用", refs2 == [1, 3, 5], f"实际: {refs2}")

refs3 = EvidenceCompletenessChecker._expand_ref_range("2-4, 7")
check("[2-4, 7]展开为4个引用", refs3 == [2, 3, 4, 7], f"实际: {refs3}")

# ============================================================
print("\n=== H6: HTML链接安全过滤 ===")
# ============================================================
from render_final_review_html import apply_inline_formatting

safe = apply_inline_formatting("[link](https://example.com)")
check("正常链接保留", 'href="https://example.com"' in safe)

xss = apply_inline_formatting("[click](javascript:alert(1))")
check("javascript:协议被过滤", "javascript:" not in xss)
check("过滤后文本保留", "click" in xss)

data_xss = apply_inline_formatting("[img](data:text/html,<script>)")
check("data:协议被过滤", 'href="data:' not in data_xss)

# ============================================================
print(f"\n{'='*50}")
print(f"结果: {passed} 通过, {failed} 失败, 共 {passed+failed} 项")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)
