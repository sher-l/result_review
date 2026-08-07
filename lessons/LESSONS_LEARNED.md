# 经验教训索引

> 按项目编号索引。详细错误案例和成功案例见 `archive/old_docs/LESSONS_LEARNED_full.md`。

---

## 错题集更新规则

- 每次审核结束后，必须将本次典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议沉淀到 `lessons/`；无新增模式时也应在审核复盘中说明“无新增错题集沉淀项”。
- 单条错题至少记录：错误类型、具体表现、触发场景、证据依据、正确标准、下次审核提醒、严重程度、规则建议。
- 规则建议若已明确、可执行且证据充分，直接同步更新对应 `patterns/*.md`、本索引或政策文档；只有证据不足或影响硬门禁时才标注“待复核”。
- 新项目审核前必须读取本索引和 `patterns/`；遇到相同或相近内容时列为重点复核项。
- 错题集只提示风险，不直接替代当前项目判断；后续项目必须结合当前报告、代码、结果文件和图表证据独立核验，不能机械套用历史结论。
- 写入位置：项目特有案例写 `LESSONS_LEARNED_<项目编号>.md`；可复用模式同步更新下方框架级速查表或 `patterns/*.md`。

---

## 按模式查询（推荐）

> 从 12 个项目的审核经验中提炼的 20 个通用审核模式，按问题类别归档。

| 文件 | 模式 | 严重性 | 涵盖项目数 |
|------|------|--------|----------|
| [copy_paste_residue.md](patterns/copy_paste_residue.md) | P01-P03, P12: 项目编号/疾病名/数据集/模板残留 | 🔴 FATAL | 7 |
| [numerical_direction_errors.md](patterns/numerical_direction_errors.md) | P04, P09, P18, P20: MR方向/数值/单调性/基线方向 | 🔴 CRITICAL | 6 |
| [method_code_mismatch.md](patterns/method_code_mismatch.md) | P05, P16, P19: 统计方法/ML方法/临床统计声称 | 🔴 CRITICAL | 4 |
| [data_flow_coverage.md](patterns/data_flow_coverage.md) | P06, P07, P11: 数据流断裂/基因名/覆盖缺失 | 🔴 FATAL~MAJOR | 4 |
| [figure_visual_errors.md](patterns/figure_visual_errors.md) | P08, P17: 图件编号/内容/单细胞QC图件 | 🟠 MAJOR~CRITICAL | 5 |
| [structural_special.md](patterns/structural_special.md) | P10, P13-P15: 结构格式/假阳性/对接/二级分析 | 🟠 MAJOR | 5 |

---

## 按项目查询

| 项目编号 | 文件 | 关键教训 |
|----------|------|----------|
| 25YLC105F | [LESSONS_LEARNED_25YLC105F.md](LESSONS_LEARNED_25YLC105F.md) | monocle 数据流断裂、物种基因集错误、术语不一致 |
| 25YHB687F | [LESSONS_LEARNED_25YHB687F.md](LESSONS_LEARNED_25YHB687F.md) | 结构检查递归、DEG 阈值一致性 |
| 25YZF106F | [25YZF106F_lessons.md](25YZF106F_lessons.md) | 术语专项检查流程、数据库版本验证 |
| 26YHB147F | [LESSONS_LEARNED_26YHB147F.md](LESSONS_LEARNED_26YHB147F.md) | 报告文本质量、copy-paste 残留检测 |
| 26YHB100F | [LESSONS_LEARNED_26YHB100F.md](LESSONS_LEARNED_26YHB100F.md) | MR 方向反写、机器学习方法口径错配、单细胞错图与模板残留、MD 参数冲突 |
| 26YLM076F | [LESSONS_LEARNED_26YLM076F.md](LESSONS_LEARNED_26YLM076F.md) | 覆盖矩阵双向检查、GSE 交叉验证、WGCNA MAD 方向 |
| 26YSH015F | [LESSONS_LEARNED_26YSH015F.md](LESSONS_LEARNED_26YSH015F.md) | 临床统计高频错误: 逐步回归虚假声称、基线方向性、生存分析模板残留 |
| 26YYH033F | [LESSONS_LEARNED_26YYH033F.md](LESSONS_LEARNED_26YYH033F.md) | Word 报告 Figure 标题检查 |
| 25YYF085F | [LESSONS_LEARNED_25YYF085F.md](LESSONS_LEARNED_25YYF085F.md) | 跨项目文件夹路径残留("04_exp_RNF138")、隐性数据集未在Table 1声明(GSE65682)、Platelets翻译错误、CellChat图注矛盾 |
| 26YYS083F | [LESSONS_LEARNED_26YYS083F.md](LESSONS_LEARNED_26YYS083F.md) | 项目编号错(26YYS056F)、疾病名HCC→PAAD残留、scRNA QC单调性违反、基因名笔误(CXX1→CXXC1)、章节跳号、Figure引用越界 |
| 25SLM065F | [LESSONS_LEARNED_25SLM065F.md](LESSONS_LEARNED_25SLM065F.md) | 方案编号残留、CTD药物交集错误、模型选择口径混入训练集、分子对接证据不足 |
| 26YHB132F | [LESSONS_LEARNED_26YHB132F.md](LESSONS_LEARNED_26YHB132F.md) | GSE编号错写、单细胞原始源缺失、共定位阈值未达、对接/MD不可复现、机械假阳性处置 |
| 26YHB417F | [LESSONS_LEARNED_26YHB417F.md](LESSONS_LEARNED_26YHB417F.md) | 仅Word交付导致结果不可追溯、方法-代码不可验证、宣传页高风险词误触发 |
| 26YLM158F | [LESSONS_LEARNED_26YLM158F.md](LESSONS_LEARNED_26YLM158F.md) | 0代码交付导致代码不可复现、TCGA-STAD外数据集残留、ACOT8-only验证与10基因列线图不一致 |
| 26YTY054F | [LESSONS_LEARNED_26YTY054F.md](LESSONS_LEARNED_26YTY054F.md) | 外项目编号残留、未报告GSE61739、Figure 18重复、代码未提供仅WARNING但高风险结论需独立复核 |
| 26YZF040F | [LESSONS_LEARNED_26YZF040F.md](LESSONS_LEARNED_26YZF040F.md) | ICI抗体不应默认走SMILES/SuperPred链、原始p阳性但FDR不显著污染下游、外部验证C-index偏低不得写“良好”、未执行方法残留 |

---

## 框架级教训速查

| 类别 | 教训 | 来源 |
|------|------|------|
| P0 数据流 | monocle 输入基因 ≠ 上游交集输出 → FATAL | 25YLC105F |
| P0 术语 | 肾结石项目出现 Tumor/Normal → FATAL | 25YLC105F |
| P0 物种 | 小鼠 .gmt 用于人类数据 → FATAL | 25YLC105F |
| P0 编号 | setwd 路径有他人编号 → FATAL | 通用 |
| MR | 危险因素 / 保护因素结论必须逐基因核对 OR 或 β 的方向，不能只抄图注颜色 | 26YHB100F |
| 机器学习 | 报告写 LASSO / SVM-RFE 前，必须核对 glmnet alpha、rfeControl(functions) 和实际输入特征集 | 26YHB100F |
| 单细胞 | QC 前后图必须实际比对，不能只信脚本注释；组名、降维方法、细胞类型名要全文排模板残留 | 26YHB100F |
| MD | 方法段与结果段的模拟时长/力场/温度必须统一，且必须交付轨迹原始文件或导出数值 | 26YHB100F |
| 高风险模块 | 代码/脚本未提供本身仅作为 WARNING；证据包不足、结果缺失、结论过强需拆分独立定级 | 26YTY054F |
| 临床统计 | "逐步回归"声称但代码无实现 → CRITICAL | 26YSH015F |
| 临床统计 | 基线变量 OR 方向与均值方向矛盾 → CRITICAL | 26YSH015F |
| 临床统计 | 分类变量方向描述需按高水平占比判定，不能只看显著性 | 26YSH015F |
| 临床统计 | Logistic 报告需全文排除生存分析模板残留 | 26YSH015F |
| 报告文本 | Figure 标题错误 → FATAL | 26YHB161F |
| Copy-paste | 报告引用的"结果文件见文件夹XX"路径必须在项目中实存，否则 → FATAL | 25YYF085F |
| 覆盖矩阵 | 反向扫描：正文/结果所有 GSE 编号必须在 Table 1 声明 | 25YYF085F |
| 数据流 | 报告声明的每个GSE编号必须在rawdata或可追溯下载清单中出现；下游结果存在不能替代原始源交付 | 26YHB132F |
| 术语 | 癌种缩写(HCC/PAAD/BRCA等)全文排查，防止跨项目残留 → FATAL | 26YYS083F |
| 单细胞 | scRNA QC 数字单调性：过滤后细胞数 ≤ 过滤前，否则 → CRITICAL | 26YYS083F |
| 基因名 | 正文基因名与上游分析 CSV 输出交叉验证，防止笔误 → CRITICAL | 26YYS083F |
| 结构 | 章节编号连续性 + Figure 引用不越界 → MAJOR | 26YYS083F |
| 翻译 | Platelets=血小板（非"血细胞"），细胞类型翻译需逐一核对 | 25YYF085F |
| 分子对接 | 只有展示 PDF/PDB 而无 Vina 日志、结合能表、grid 参数和脚本时，结合能结论不可复核 → CRITICAL | 25SLM065F |
| 共定位 | 报告写PPH4阈值时，必须计算结构化结果max(PP.H4.abf)；未达阈值不得暗示阳性共定位，且gene列不能被目标基因名整列替换 | 26YHB132F |
| 药物预测 | CTD 药物交集必须按唯一 Chemical ID 去重求交，并记录额外筛选规则，否则交集结论不可采信 | 25SLM065F |
| 机器学习 | 最佳模型若声称按验证集平均 AUC 选择，不得把训练集 AUC 混入排序；模型组合总数需与 AUC 矩阵行数一致 | 25SLM065F |
| Copy-paste | 正式结果报告即使同包内有方案设计参考，也必须独立核对封面单号/项目编号；正式报告残留其他单号 → FATAL | 25SLM065F |
| 仅Word交付 | 正文声明结果文件夹但项目结构为0模块/0代码/0数据 → FATAL | 26YHB417F |
| 代码交付 | 多模块生信项目若 total_code_files=0，应保留 WARNING 级代码不可复现风险；不得仅因无代码升级为 CRITICAL，统计错误/数据链断裂/错误项目来源需独立定级 | 26YLM158F、26YTY054F、26YZF040F |
| 上下文管理 | Sub-Agent/Lead 不得把完整报告、完整 JSON、长日志、完整通知 metadata、归档路径或监督 JSON 路径回传主线程；Sub-Agent 聊天最多 5 行，Lead 最终回复最多 8 行，完整内容只落盘回路径 | 框架反馈 2026-05-21 |
| 药物预测 | 抗体药物/ICI 不应默认进入小分子 SMILES/SuperPred 靶点预测链；若使用需说明适用性、来源列和去重规则 | 26YZF040F |
| 多重检验 | 原始 p 值阳性但 FDR 不显著的入口变量不得支撑强阳性下游链；若继续使用，结论需降格为探索性并说明多重检验风险 | 26YZF040F |
| 生存模型 | 训练集高 C-index/AUC 不得抵消外部验证集偏低；“良好预测性能”必须以外部验证和置信区间为主要依据 | 26YZF040F |
| 机器学习 | LASSO/SVM/Boruta筛选、表达验证和列线图入模基因集合必须逐段核对；外部数据集残留如 TCGA-STAD 会破坏数据链条 | 26YLM158F |

---

> 完整历史经验（含案例叙述）：`archive/old_docs/LESSONS_LEARNED_full.md`
> 框架优化历史：`archive/old_docs/FRAMEWORK_OPTIMIZATION_SUMMARY.md`

## 框架反馈 2026-05-21：Context compacted / 信息过载

- 错误类型：框架执行上下文管理不足。
- 具体表现：Sub-Agent 或 Lead 将完整报告、完整 JSON、长日志、完整通知 metadata、归档路径或监督 JSON 路径回传主线程，导致主上下文过大并触发 compact。
- 触发场景：正式审核完成通知、subagent 监督汇总、长证据整合、框架测试回执。
- 证据依据：用户反馈“还是进行了 Context compacted”“整个消息都发出去了”“信息有点太多”。
- 正确标准：完整内容只落盘；Sub-Agent 聊天最多 5 行；Lead 最终回复最多 8 行；正式通知只保留状态、时间、项目、报告文件、审核结果、问题统计。
- 下次审核提醒：不要为了证明完成而粘贴完整 metadata 或产物清单；必要时只报关键结果和路径。
- 严重程度：框架执行风险 WARNING。
- 规则建议：将 compact-safe 作为默认硬门禁，写入 policy、Master Prompt、Workflow、Core Rules、切片 prompt 和生成文档；若仍出现 compact/context loss，必须继续拆分切片并减少回传字段。
- 已同步到框架规则：`policy/audit_policy.json`、`MASTER_PROMPT.md`、`WORKFLOW.md`、`CORE_RULES.md`、`scripts/launch_convergence_audit.py`、`scripts/generate_policy_docs.py`。

## 26YHB052F（2026-05-20）

- 未列入Table 1且未交付rawdata/矩阵的数据集不得支撑验证结论（GSE126044/GSE135222）。
- 方法段声称GSVA但代码为Z-score/RSF时，按方法-代码不一致处理。
- 单细胞伪时间目录/文件名残留Adipocytes而正文写巨噬细胞，属于高风险图文主线冲突。
- 虚拟敲除图注BID/BAX复制粘贴残留需逐基因复核。
- 详见 `LESSONS_LEARNED_26YHB052F.md`。
