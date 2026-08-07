# 图像审核路线图

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v7.1`
> Policy updated at: `2026-08-04`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 当前已实现

- `visual_prefilter.json`：视觉预筛结构化产物。
- `visual_audit_result.json`：资产守恒、跳过/不支持理由和高风险派生证据的最终闭环。
- 完全重复图检测：基于文件 SHA1。
- OCR 项目编号失配检测：可选依赖 `pytesseract`。
- 明显错图检测：用轻量视觉家族分类拦截“图表位被文字页替代”类错误。
- 字体风格不一致检测：基于 OCR 文本块和字形统计做启发式预警。
- `review_lane`：`standard` / `strict` 双车道，当前默认 `strict`。

## 后续增强建议

1. 感知哈希或向量相似度，覆盖裁剪后重复图。
2. 图注 OCR 与正文自动对齐，提升跨项目污染检出率。
3. 图表类型识别从规则法升级为轻量模型。
4. 把 `visual_prefilter` 风险标签回灌到 mechanical checks 和最终报告模板。

## 使用原则

- 机器预筛只负责排序和标红，不直接替代最终裁定。
- `strict` 项目仍保留全量 AI看图。
- 图件格式不要求 PDF+PNG 双格式；PDF-only 可接受，PNG/JPG-only 需说明或补 PDF。
