# 26YYH134F 可复用框架优化镜像

生成时间：2026-07-06T09:56:45

## 可执行加固项

1. **总结段外项目扫描加权**：当前 MC-006 能抓到 Cancer，但对 HNSCC、TCGA-HNSCC、DepMap、外项目四基因组合应在总结段赋予更高权重；当总结段疾病/数据集/基因与封面主线冲突时建议直接触发 FATAL 候选。
2. **声明文件夹存在性门禁**：对“结果文件见文件夹XX”“详见XX目录”建立 exact directory check；若目录不存在且模块属于虚拟敲除、MD、对接、机器学习，应进入高风险队列。
3. **MD 证据包规则**：检测到 Gromacs、AMBER、100 ns、RMSD、RMSF、Rg、H-bond 等关键词时，要求轨迹/拓扑/mdp/log/指标表或图至少一组存在。
4. **药物预测与对接结构化文件规则**：GraphBAN/ADMET/Vina 链条必须检查 CSV/TXT/log/config/PDB/PDBQT/SDF/MOL 等扩展；仅 PNG/PDF 时标记不可复核。
5. **GSE 反向追溯规则**：报告出现的每个 GSE 编号必须在 rawdata、文件名、下载清单或明确说明中可追溯；外项目总结中的 GSE 应按复制残留处理。
6. **核心基因近似拼写规则**：对 PPI/KM/免疫/GSEA/docking 共同出现的核心基因做近似拼写检查，例如 CCND1 与 CCDN1。

## 本次未直接修改框架代码的理由

- 本次任务边界是完成 26YYH134F 正式审核并发送正式通知；框架代码改造会扩大为框架维护任务。
- 已将可复用规则写入项目错题集和 `result_review_framework/lessons/26YYH134F_*`，后续框架维护可据此实施。
- 不涉及企业微信测试或通知调试；正式发送仅由 `finalize_audit.py` 执行。

## 建议更新目标

| 目标 | 建议 |
|---|---|
| `mechanical_checks.py` | 增加总结段疾病/数据集/基因一致性评分和声明文件夹 exact check |
| `visual_audit.py` | 对 MD 章节后缺少 MD 曲线、对接图无数值标注增加专门提示 |
| agent slice prompt | 要求高风险模块检查结构化文件、参数、日志和代码，不接受截图替代 |
| lessons/patterns | 将“声明文件夹不存在”和“对接仅 PNG”加入可复用模式 |
