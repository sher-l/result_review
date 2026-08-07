<!-- Mirrored durable lessons from result_review_report/26YBB036F/wrong_question_set.md on 2026-06-25. -->

# 26YBB036F 错题集

## 项目级典型错误

| 编号 | 典型错误 | 触发场景 | 证据 basis | 正确标准 | 下次提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|---|
| WQ-01 | 把未交付的空间数据写入正式数据来源 | 报告列出 GSE298286，但 rawdata 无目录 | `report_text.txt` L14/L28；`project_structure.json` rawdata 清单 | 每个报告数据集必须在 rawdata 或下载清单中闭环 | 先核对数据集编号双向覆盖，再看方法和结果 | CRITICAL | 若报告出现 GSE 编号而 rawdata、代码和下载清单均未命中，直接生成 CRITICAL 候选 |
| WQ-02 | 核心空间模块只有方法声明，没有结果图表和代码 | 题名含空转结合，结果 2.3、2.8-2.11 无实质输出 | `report_text.txt` L35-L63、L125-L189；图号跳断 | 题名核心模块必须同时具备数据、代码、结果和图表 | 空间、单细胞映射、空间轨迹、共定位要逐项查目录 | CRITICAL | 为空间模块建立“方法词汇→结果章节→目录→图号”四联检查 |
| WQ-03 | 高风险 docking→MD 目标链条断裂 | 对接最优组与 MD 模拟对象不同 | `report_text.txt` L247-L255、L268；docking 输出 | docking 分数、相互作用图、MD 复合物必须同一受体-配体 | 先比对 Table、原始口袋、PDB 文件名和 MD 图注 | CRITICAL | 对 docking/MD 加入受体、配体、score、pose、MD target 的一致性断言 |
| WQ-04 | 方法阈值与实际筛选表口径不一致 | DEG 方法写 `|log2FC|>1`，候选表按 padj 保留 | `report_text.txt` L65/L192；`script/r.13_bulk.DEGs.R` | 方法、代码、结果表必须使用同一阈值，或明确分层口径 | 看到候选基因数量时必须复算筛选条件 | MAJOR | 对 DEG 表自动统计满足方法阈值的行数并与正文数量比较 |
| WQ-05 | 多算法评分公式写法与代码实现不一致 | 报告称五种得分归一化后求和，代码只处理一列 | `script/r.04.scRNA.irGSEA.R` L50-L58 | 评分公式、列名、归一化范围和求和对象必须一致 | 关键细胞来源于 score 时必须查公式和代码 | MAJOR | 子代理提示中加入“综合评分公式逐列核对”检查 |
| WQ-06 | 生存验证把验证集内最优切点当外部验证 | 每个数据集单独 `surv_cutpoint` | `script/r.14_DEGs.KM.R`；`P_data.csv` 字段 | 外部验证应固定训练切点，并报告 HR/CI/样本量 | 生存筛选不能只看 P 值交集 | MAJOR | 预后模块检查必须要求 cutpoint 来源、HR/CI、事件数和校正统计 |
| WQ-07 | 单细胞统计把细胞当独立重复 | Wilcoxon/相关性直接按细胞执行 | `script/r.04.scRNA.irGSEA.R`、`script/r.05_scRNA.KeyCell.subcell.R` | 组间推断应考虑患者/样本层级 | 看到大量细胞显著性时先问单位是细胞还是样本 | MAJOR | 单细胞统计检查加入 pseudobulk/混合模型/样本层级字段要求 |
| WQ-08 | 交付代码保留外项目示例数据 | `plot1cell/utils.R` 含 GSE139107 / MouseIRI | `script/plot1cell/utils.R` L428-L469 | 正式交付代码不得混入未声明数据集的下载和读取流程 | 工具函数也要扫 GEO 编号和疾病/物种标签 | MAJOR | 代码级 GEO 扫描命中未声明编号时，区分主流程与示例，但必须记录清理要求 |
| WQ-09 | 药物预测只导出候选名，缺筛选统计 | pRRophetic 候选 CSV 无 r/P/校正 P | `result/18_pRRophetic`；`script/r.18_pRRophetic.R` | 高通量药物筛选必须导出完整统计和多重校正 | 药物结论不能只看候选名称 | MAJOR | 药物模块检查必须要求每个候选的 Wilcoxon、相关性、校正 P 和模型性能 |
| WQ-10 | 模拟敲除按名义 P 值写强结论 | scTenifold top 基因校正后 P 不支持同等强度 | `result/17_scTenifoldKnk/附件/*.csv` | 多重检验场景必须报告校正口径 | 虚拟敲除属于探索性证据，表述要降级 | WARNING | scTenifold 检查加入 nominal P 与 adjusted P 双阈值摘要 |

## 本项目审核提醒

1. 修订版首先关闭 F-01、F-02、F-03；否则不进入通过判定。
2. 所有 F 编号必须回填到逐分析点表，避免主问题与分析点断链。
3. 后续相似项目遇到空间、docking/MD、药物预测、单细胞统计时，应优先套用本错题集的触发规则并重新核验证据。
