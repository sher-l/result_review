# 脚本执行完整参考

> 本文档为所有可执行脚本提供统一的参数说明、输入输出路径和错误排查指引。  
> 快速入门参见 [QUICKSTART.md](QUICKSTART.md)。

---

## 环境准备

```powershell
cd d:\IKL\BaiduSyncdisk\报告审核
# 创建虚拟环境（仅首次）
python -m venv result_review_framework\.venv
# 激活
result_review_framework\.venv\Scripts\Activate.ps1
# 安装依赖
pip install -r result_review_framework\requirements.txt
```

**Python 版本**: ≥3.9  
**必要依赖**: python-docx, lxml, pandas（见 `requirements.txt`）

---

## 主入口脚本

### 1. auto_audit_pipeline.py — Round 0 自动预检查

**用途**: 执行 Layer 0 预解析 + Layer 1 全部检查器，产出预检查报告。

```powershell
python result_review_framework/scripts/auto_audit_pipeline.py `
  "raw/待审核/<项目目录>"
```

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| project_path | 位置参数 | ✅ | 项目根目录（相对或绝对路径） |
| --project-type | 可选 | ❌ | 疾病类型（自动推断，通常无需指定） |
| --review-dir | 可选 | ❌ | 输出目录（默认 `result_review_report/<项目编号>/`） |

**输出文件**:
- `<review_dir>/precheck_report.md` — 预检查 Markdown 报告
- `<review_dir>/precheck_report.json` — 结构化 JSON（供后续步骤使用）
- `<review_dir>/layer0/report_text.txt` — 提取的报告纯文本
- `<review_dir>/layer0/report_structure.json` — 报告结构索引
- `<review_dir>/layer0/project_structure.json` — 项目结构索引
- `<review_dir>/layer0/mechanical_check_result.json` — MC 检查结果

**常见错误**:
| 错误 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError: report` | 项目目录下无 .docx/.doc 文件 | 检查项目目录是否有报告文件 |
| `ModuleNotFoundError: docx` | 未安装 python-docx | `pip install python-docx` |
| `UnicodeDecodeError` | 文件编码问题 | 检查 .csv/.txt 文件编码（应为 UTF-8） |

---

### 2. extract_report.py — 报告文本提取

**用途**: 从 .docx 文件提取纯文本（含 `[IMAGE: xxx.png]` 标记）。

```powershell
python result_review_framework/scripts/extract_report.py `
  "<项目路径>/报告文件.docx" `
  -o "<输出目录>/report_text.txt"
```

**说明**: 通常由 auto_audit_pipeline.py 自动调用，无需手动执行。

---

### 3. parse_report_structure.py — 报告结构解析

**用途**: 从 report_text.txt 提取章节、图表、基因名、数字、中文异常等结构化信息。

```powershell
python result_review_framework/scripts/parse_report_structure.py `
  "<report_text.txt路径>" `
  -o "<输出目录>/report_structure.json"
```

---

### 4. parse_project_structure.py — 项目结构解析

**用途**: 扫描项目目录，提取模块、代码文件、包列表、参数索引、GEO 引用、项目 ID。

```powershell
python result_review_framework/scripts/parse_project_structure.py `
  "<项目路径>" `
  -o "<输出目录>/project_structure.json"
```

---

### 5. mechanical_checks.py — 机械检查

**用途**: 执行 MC-001~MC-012 确定性机械检查。

```powershell
python result_review_framework/scripts/mechanical_checks.py `
  "<项目路径>" `
  -o "<输出目录>/mechanical_check_result.json"
```

---

### 6. terminology_audit.py — 术语/数据库/URL 专项检查

**用途**: 术语一致性、数据库名称、URL 可访问性专项审查。

```powershell
python result_review_framework/scripts/terminology_audit.py `
  "<report_text.txt路径>"
```

---

### 7. ensure_review_html.py — HTML 报告生成

**用途**: 检查审核报告目录，自动补齐/更新 `audit_report.html`。

```powershell
# 单项目
python result_review_framework/scripts/ensure_review_html.py `
  "result_review_report/<项目编号>"

# 批量（扫描整个目录）
python result_review_framework/scripts/ensure_review_html.py `
  "result_review_report"
```

**触发条件**:
- `final_review_report.md` 存在但无 `audit_report.html`
- `audit_report.html` 修改时间早于 `.md` 文件

---

### 8. render_final_review_html.py — HTML 渲染器

**用途**: 将 `final_review_report.md` 渲染为格式化的 `audit_report.html`。

```powershell
python result_review_framework/scripts/render_final_review_html.py `
  "result_review_report/<项目编号>/final_review_report.md"
```

**说明**: 通常由 ensure_review_html.py 调用，一般无需手动执行。

---

### 9. check_figure_integrity.py — 图件完整性（独立入口）

**用途**: 独立检查某个目录下的图件文件完整性。

```powershell
python result_review_framework/scripts/check_figure_integrity.py `
  "<结果文件目录>"
```

---

## 内部工具

| 脚本 | 说明 | 调用方 |
|------|------|--------|
| `_extract_report.py` | 旧版报告提取（兼容入口） | — |
| `_parse_result.py` | 旧版结果解析 | — |

---

## 诊断与排查

### 日志

- auto_audit_pipeline.py 输出到 stdout，可重定向到文件：
  ```powershell
  python result_review_framework/scripts/auto_audit_pipeline.py "..." 2>&1 | Tee-Object -FilePath audit.log
  ```

### 常见问题

| 问题 | 排查 |
|------|------|
| 检查器结果全部 skipped | 检查 Layer 0 JSON 是否正常生成 |
| HTML 报告为空 | 确认 final_review_report.md 存在且非空 |
| 中文乱码 | 确认文件编码为 UTF-8（非 UTF-16 LE） |
| import 报错 | 确认 `.venv` 已激活且已安装 requirements.txt |

### 手动验证单个检查器

```python
from result_review_framework.script_utils.check_orchestrator import CheckOrchestrator
orch = CheckOrchestrator("raw/待审核/<项目目录>")
result = orch.run_single_checker("ProjectIDChecker")
print(result)
```
