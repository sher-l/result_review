# 经验教训索引

> 按项目编号索引。详细错误案例和成功案例见 `archive/old_docs/LESSONS_LEARNED_full.md`。

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
| 临床统计 | "逐步回归"声称但代码无实现 → CRITICAL | 26YSH015F |
| 临床统计 | 基线变量 OR 方向与均值方向矛盾 → CRITICAL | 26YSH015F |
| 临床统计 | 分类变量方向描述需按高水平占比判定，不能只看显著性 | 26YSH015F |
| 临床统计 | Logistic 报告需全文排除生存分析模板残留 | 26YSH015F |
| 报告文本 | Figure 标题错误 → FATAL | 26YHB161F |
| Copy-paste | 报告引用的"结果文件见文件夹XX"路径必须在项目中实存，否则 → FATAL | 25YYF085F |
| 覆盖矩阵 | 反向扫描：正文/结果所有 GSE 编号必须在 Table 1 声明 | 25YYF085F |
| 术语 | 癌种缩写(HCC/PAAD/BRCA等)全文排查，防止跨项目残留 → FATAL | 26YYS083F |
| 单细胞 | scRNA QC 数字单调性：过滤后细胞数 ≤ 过滤前，否则 → CRITICAL | 26YYS083F |
| 基因名 | 正文基因名与上游分析 CSV 输出交叉验证，防止笔误 → CRITICAL | 26YYS083F |
| 结构 | 章节编号连续性 + Figure 引用不越界 → MAJOR | 26YYS083F |
| 翻译 | Platelets=血小板（非"血细胞"），细胞类型翻译需逐一核对 | 25YYF085F |

---

> 完整历史经验（含案例叙述）：`archive/old_docs/LESSONS_LEARNED_full.md`
> 框架优化历史：`archive/old_docs/FRAMEWORK_OPTIMIZATION_SUMMARY.md`
