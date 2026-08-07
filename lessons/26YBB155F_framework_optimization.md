# 26YBB155F 框架优化记录

## 1. 本次命中的框架短板

- 系统性文本搜索入口缺失：框架文档要求 script_utils/systematic_text_search.py，但当前工作区未找到该脚本，导致只能用项目内检索和子代理切片替代。
- visual_audit_checklist.json 与 figure_audit.md 可生成候选项，但 figure_audit.md 仍可保留未闭环字段；需要在 finalize 前由 linter 检查该状态。
- convergence_compare.py 对部分语义相近但主题不同的问题存在误配，需要在最终报告要求 Lead AI裁定表记录“采纳/拆分/降级”。
- 对 MR 结果计数、DGIdb 字段、对接结构 ID、hub_final 硬编码等高频错误，可进一步形成轻量脚本检查。

## 2. 建议加固项

| 位置 | 建议 | 本次证据 | 优先级 |
|---|---|---|---|
| scripts/systematic_text_search.py 或 script_utils/systematic_text_search.py | 补齐官方入口，检查项目编号、GSE/GSM、疾病词、单细胞术语、外项目编号、参考文献尾部残留 | 本次运行两个候选路径均失败 | 高 |
| final_report_linter.py | 增加 figure_audit.md 未闭环字段和 visual_audit_checklist 元数据错配提示 | B02 发现清单与正文图号不一致 | 中 |
| convergence_compare.py | 输出低置信匹配并要求 Lead 拆分，避免 PPI 与 MR 等主题误配 | convergence_report.md 中 M001/M004/M005 存在误配 | 中 |
| patterns/method_code_mismatch.md | 加入 MR clump 参数、五种 MR 算法声明、hub_final 硬编码、ceRNA 多库支持未实现规则 | F-02/F-03/F-05 | 高 |
| patterns/figure_visual_errors.md | 加入图号跳号和视觉清单非结果页元数据错配规则 | F-13 | 中 |

## 3. 无需立即修改政策的项

- 本次不建议把单纯目录名称顺序不一致升级为硬门禁；它应作为 WARNING 或与证据链不足合并判断。
- 本次不建议把对接缺脚本单独定为 FATAL；当受体 ID 错配或结构化结果缺失同时出现时再升级为 MAJOR/CRITICAL。
