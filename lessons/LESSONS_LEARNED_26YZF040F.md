# Lessons Learned: 26YZF040F

生成时间：2026-05-21T14:34:54

## 新增模式

1. **抗体药物不应默认进入小分子 SMILES/SuperPred 靶点预测链。** 当报告把 ICI 抗体写成“免疫抑制剂”并使用 SMILES 预测靶点时，应要求说明适用性、来源列和去重规则。
2. **原始 p 值阳性与 FDR 不显著会污染整条下游生信链。** 若下游靶点、候选基因和预后模型均以该药物为起点，应将入口统计口径列为 CRITICAL。
3. **训练集高 C-index 不得抵消外部验证不足。** 生存模型如果验证集 C-index 约 0.6，即便均值因训练集拉高，也不能写“良好预测性能”。
4. **“项目终止/已删除”说明不能与详细方法共存。** 未执行的 ML、SHAP、单细胞、scTenifoldKnk/Geneformer 方法残留应作为正式稿结构诚信问题处理。

## 后续框架建议

- 规则建议：对 OR/CI 列出现负值增加机械检查规则，提示 log(OR)/系数误标。
- 规则建议：对抗体药物 + SMILES/SuperPred 组合增加高风险提示。
- 规则建议：对验证集 C-index/AUC 低于阈值而正文写“良好”增加语义检查。
- 规则建议：单纯未交付代码 / 未发现代码文件 / 代码不可复现风险只按 WARNING；不得仅因无代码升级为 CRITICAL 或作为唯一不通过原因。若伴随统计错误、数据链断裂、错误项目来源或结论无证据，应按这些实质问题独立定级。

## 已同步到框架规则

- `policy/audit_policy.json`：新增 `code_delivery_policy`，并要求错题集记录“规则建议”。
- `CORE_RULES.md` / `MASTER_PROMPT.md` / `CHECKLIST_TEMPLATE.md` / `WORKFLOW.md`：同步“无代码仅 WARNING，实质问题独立升级”的严重度口径。
- `lessons/LESSONS_LEARNED.md`：新增 26YZF040F 索引和框架级速查项。
