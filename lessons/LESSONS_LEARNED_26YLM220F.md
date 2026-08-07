# 26YLM220F 错题集

## 错题 1：无正式报告仍尝试把代码/图件当作报告审核通过依据
- 错误类型：交付范围与证据链误判。
- 具体表现：项目包只有 rawdata、Cox PDF 和 R 脚本，未交付 .docx/.doc 正式报告。
- 触发场景：生信项目只交结果文件或中间产物，报告正文遗漏。
- 证据依据：report_text.txt L1-L2；report_structure.json total_sections=0；原始目录无 .docx/.doc。
- 正确标准：正式审核必须能把报告章节、图号、图注、结论映射到结果和代码；缺正式报告应至少 CRITICAL，不得判通过。
- 下次审核提醒：先查 zip/docx 清单，再运行报告结构解析；无报告时仍可审数据包，但结论必须标注报告级阻断。
- 严重程度：CRITICAL。
- 规则建议：auto_audit_pipeline 未发现 docx 时也应创建 review_dir/case_manifest，并把“正式报告缺失”作为默认高优先级候选问题。

## 错题 2：机械检查把 GSE53625 误判为 rawdata 未提及
- 错误类型：自动检查假阳性/证据口径不完整。
- 具体表现：MC-008 称代码引用 GSE53625 但 rawdata 未提及；实际 rawdata 存在 02.*GSE53625.csv。
- 触发场景：GEO 数据以处理后 CSV 命名交付，机械检查只看部分索引或报告文本。
- 证据依据：00_rawdata/02.exprlog2_GSE53625.csv、02.group_GSE53625.csv、02.survival_GSE53625.csv；r.00_rawdata.r getGEO('GSE53625')。
- 正确标准：区分“数据实际存在”“报告未声明”“跨项目污染”三类结论，不得把前两者混为外项目污染。
- 下次审核提醒：GSE 类问题必须三方核对：代码引用、rawdata实物、报告声明。
- 严重程度：MAJOR（本项目最终为报告声明缺口）。
- 规则建议：MC-008 输出应列出 rawdata 命中的 GSE 文件，若存在则降为“报告声明待核”。


# 26YLM220F 框架优化记录

## 应强化项
1. `auto_audit_pipeline.py` 在未发现 .docx 时仍应创建 `result_review_report/<project_id>`、`case_manifest.json`、`project_structure.json` 和默认 `report_text.txt`，避免后续 guardrails 断档。
2. `check_report_data_match` / MC-008 应把 rawdata 文件名中的 GSE 命中纳入判断；若 rawdata 存在但报告缺失，应输出“报告声明缺失”，不要直接写“rawdata 未提及/跨项目污染”。
3. 小切片 prompt 对视觉审核应默认允许读取 `visual_prefilter.json`、`visual_audit_checklist.json`、`figure_audit.md`；若这些文件不存在，切片应记录“不适用/未生成”，不应阻断。

## 本次不需要新增政策口径
- 代码未交付/复现风险仍按既有 WARNING 口径；本项目有代码，但正式报告缺失与 Cox 结构化结果缺失是独立问题。
- 高风险模块（docking/MD/虚拟敲除）未发现实质交付或报告声称，不新增问题。
