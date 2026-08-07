# 标准检查工作流程

> 说明：本文件是展开版流程参考，不再是第一入口。  
> 当前正式审核先以 `policy/audit_policy.json`、`README.md`、`MASTER_PROMPT.md` 为准；本文件用于补充细节，不用于覆盖主线口径。

> **版本**: v7.1
> **更新日期**: 2026-07-30
> **状态**: ✅ 已升级（五层执行引擎：Layer 0 预解析 + Layer 1 检查器 + Layer 2 全量视觉审核 + Layer 3 Sub-Agent + Layer 4 最终复核）
> **收敛协议**: [CONVERGENCE_REVIEW_PROTOCOL.md](CONVERGENCE_REVIEW_PROTOCOL.md)

├── 由final_review_report.md导出audit_report.html
---

## 🎯 统一工作流程

## 核心补强原则（2026-03-17）

后续所有审核都必须按“逐分析点闭环”执行，而不是按整份报告给总评。

每个分析点至少要回答 4 个问题：

1. 方法在报告中有没有写清。
2. 结果描述在报告中有没有写到。
3. 对应结果文件是否真实存在。
4. 证据是否足够支撑该结论。

如果一个分析点只有图片、PDF 或一句结果描述，但没有结构化结果表、原始数值文件或中间证据链，不得直接判定为“通过”，应标记为“证据不足”或“部分通过”。

自动预检查是辅助工具。自动检查结论若与明细矛盾，或检查器本身报错，必须转入 Agent 逐项复核，并在最终报告中写明。Agent 可通过浏览器工具（open_browser_page + screenshot_page）直接查看图片/PDF内容进行视觉核查。

### 准备阶段

#### 0. 确认项目身份
```
□ 项目编号确认
□ 项目路径确认
□ 报告文件位置确认
```

---

## 🔴 Round 0: Auto-Precheck阶段（5-10分钟）

> **为什么这是第一步？**
> - 自动化预检查可快速发现高优先级问题
> - 先把容易漏掉的代码问题集中揪出来，再进入逐项证据复核
> - 自动检查负责“全量发现问题”，不是“发现问题就停”
>
> **执行方式**：
> ```bash
> python scripts/auto_audit_pipeline.py <项目路径> --project-type <疾病类型>
> ```

### 自动检查内容

#### 0.1 项目编号一致性检查（P0 - FATAL级）

**基于项目**: 25YLC105F（所有14个代码文件使用错误项目编号25YLC135F）

```bash
# 自动检查
python script_utils/check_project_id_consistency.py <项目路径>
```

**检查项**：
- [ ] 从文件夹名提取项目编号
- [ ] 搜索代码中所有项目编号
- [ ] 检查 `setwd()` / 路径中是否出现错误项目编号或明显跨项目残留
- [ ] 记录硬编码路径信息；仅因运行环境不同而出现的本地路径不单独判错

**FATAL级标准**：
- 发现任何错误项目编号 → 🔴 **FATAL**，在最终审核中列为最高优先级，但不中断后续检查

#### 0.2 术语主题匹配检查（P0 - FATAL级）

**基于项目**: 25YLC105F（肾结石项目使用癌症术语Tumor/Normal）

```bash
# 自动检查
python script_utils/check_term_consistency.py <项目路径> --project-type <疾病类型>
```

**术语主题匹配表**：

| 项目类型 | 正确术语 | 不应使用的术语 | 冲突来源 |
|----------|----------|---------------|----------|
| 肾结石 | Disease/Control | Tumor/Normal ❌ | 癌症项目 |
| 心血管 | Cardiac/Heart | Tumor ❌ | 癌症项目 |
| 代谢 | Diabetes/Glucose | Cardiac ❌ | 心血管项目 |
| 神经 | Brain/Neuron | Cardiac ❌ | 心血管项目 |
| **IBD/UC** | UC/Control, 溃疡性结肠炎 | NAFLD ❌, LSCC ❌ | 肝病/癌症项目 |

**FATAL级标准**：
- 发现其他疾病类型的特征术语 → 🔴 **FATAL**，在最终审核中列为最高优先级，但不中断后续检查

> **⚠️ 26YHB147F教训**：还需搜索 **其他项目的GEO数据集编号** 作为跨项目Copy-paste的佐证。
> 该项目3处 NAFLD + 1处 LSCC + 1处错误数据集编号(GSE89632→GSE87466) 均来自同一Copy-paste源头。
> 建议：全文搜索所有 `GSE\d+` 编号，逐一确认属于本项目。

#### 0.3 跨模块数据流验证（P0 - FATAL级）

**基于项目**: 25YLC105F（monocle只用3个基因，但上游交集有19个）

```bash
# 自动检查
python script_utils/check_data_flow.py <项目路径>
```

**检查项**：
- [ ] monocle输入基因 = 交集输出基因
- [ ] GSEA输入基因 = ML交集
- [ ] DEG分析 → 富集分析：基因集匹配
- [ ] 单细胞 → 空间转录组：细胞类型匹配

**FATAL级标准**：
- 下游分析使用的基因数 ≠ 上游输出 → 🔴 **FATAL**，在最终审核中列为最高优先级，但不中断后续检查

#### 0.4 标准基因集数量验证（P1 - CRITICAL级）

**基于项目**: 25YLC105F（M6A基因集应25个，实际只有24个）

**标准基因集库**：

| 基因集 | 标准数量 | 说明 |
|-------|----------|------|
| **M6A** | **25个** | 6 Writers + 2 Erasers + 13 Readers + 4 IGFBP |
| 铁死亡 | FerrDb V3≈3481；KEGG hsa04216=41 | 按数据源分别核对 |
| 铜死亡 | Science 2022核心13个 | FDX1/LIAS/LIPT1 等 |
| 凋亡 | KEGG hsa04210=136 | 富集核对常用口径 |
| 自噬 | HADb+MSigDB并集604；HADb=371 | 量化/交集常用口径 |
| 焦亡 | 审核基线76；Reactome≈26 | 按来源分别核对 |

**检查清单**：
- [ ] 检查M6A基因集文件位置
- [ ] 统计实际基因数量
- [ ] 验证数量是否为25个
- [ ] 如数量不符，记录缺失基因

#### 0.5 报告覆盖与事实快检（P0/P1 - CRITICAL级）

> **为什么这一步必须前置？**
> - 25SYH053F 证明“只核对部分数字”并不能保证报告完整，核心暴露可能被批量遗漏。
> - 26YHB205F 证明数据库名称、URL、功能描述、术语翻译会出现事实性错误。
> - 26YYH033F 证明“所有样本”这类措辞会扩大样本范围，造成结论误读。

**必须输出 1 份覆盖矩阵**：

| 检查对象 | 实际存在 | 报告覆盖 | 状态 |
|----------|----------|----------|------|
| 数据集 / 队列 | ___个 | ___个 | ✅ / ❌ |
| 模块 / 子分析 | ___个 | ___个 | ✅ / ❌ |
| 暴露 / 分组 / 亚组 | ___个 | ___个 | ✅ / ❌ |
| Figure / Table | ___个 | ___个 | ✅ / ❌ |
| 失败分析 / 阴性结果 | ___项 | ___项 | ✅ / ❌ |

**快检清单**：
- [ ] 报告是否覆盖全部数据集、暴露、核心模块
- [ ] 是否遗漏失败分析、阴性结果、无显著结果
- [ ] Figure / Table 标题是否对应正确疾病、数据集、细胞类型
- [ ] 结果表格、正文描述、图注是否三方一致
- [ ] TopN / TOP5 / TOP10 描述是否与实际条目数一致
- [ ] 方法段是否写清关键阈值、TopN规则、模型选择规则、软件版本
- [ ] 数据库名称、URL、功能描述是否正确对应
- [ ] 正文提到数据库但未加参考文献编号的情况是否已单列
- [ ] 数据库引用编号是否存在串号，而不是只检查“有编号”
- [ ] 术语翻译是否正确（如 euchromatin = 常染色质，Macrophages = 巨噬细胞）
- [ ] 细胞类型中文翻译是否逐一正确（防止输入法联想错误如“局势细胞”）
- [ ] R 包名称拼写是否正确（如 IOBR 而非 IBOR）
- [ ] “所有样本 / 全部数据 / 验证集” 是否与真实样本范围一致
- [ ] 正文给出“共N例，其中A组x例、B组y例”时，x+y 是否等于 N
- [ ] 自定义分组缩写是否全文统一（如 HMS/LMS 不能与 HLS 混用）
- [ ] 方法段列出的具体分析项是否与结果段描述和实际结果文件三方一致
- [ ] 图注标注字母是否连续且无重复（不跳号、不重号）
- [ ] 方法段和结果段的章节编号体系是否一致（不混编）
- [ ] 每个核心分析点是否都能形成“方法-结果描述-结果文件-证据充分性”闭环
- [ ] 关键结论是否有结构化结果文件支持，而不是只有图片或 PDF
- [ ] 只交付筛选后结果的模块，是否缺少原始总表或中间总表
- [ ] 图件是否存在明显导出异常、错图、损坏或可视化异常
- [ ] 若项目未交付代码，是否已提前标记 WARNING 级“代码不可复现风险”，且未单独升级为 CRITICAL

**严重性标准**：
- 漏报核心模块、暴露、数据集，或选择性隐藏阴性结果 → 🔴 **CRITICAL**
- 错误数据库-功能映射、错误URL、错误术语翻译 → 🔴 **CRITICAL**
- Figure / Table 标题与实际内容不符 → 🔴 **CRITICAL**
- 样本总数与分组数加和不一致 → 🔴 **CRITICAL**
- 方法段列出的分析项与实际结果文件不匹配（如声称做了 EMT 实际做了 TGF-beta） → 🔴 **CRITICAL**
- 自定义分组缩写全文不统一（如 LMS/HLS 混用） → 🔴 **CRITICAL**
- 细胞类型中文翻译事实性错误 → 🔴 **CRITICAL**
- 临床统计项目把“差异显著”误写成错误方向（如把双胎率更低写成胎数更高） → 🔴 **CRITICAL**
- 临床统计项目声称使用逐步回归/LASSO/Bootstrap，但代码无对应函数调用 → 🔴 **CRITICAL**
- 单纯未交付代码 / 未发现代码文件 / 代码不可复现风险 → 🟡 **WARNING**；不得仅因无代码升级为 CRITICAL，也不得作为唯一不通过原因
- TopN 数量与实际不符 → 🟠 **MAJOR**
- R 包名称拼写错误 → 🟠 **MAJOR**
- 图注标注字母重复或跳号 → 🟠 **MAJOR**
- 章节编号体系混乱（方法/结果编号混编） → 🟠 **MAJOR**

#### 0.5.1 临床统计项目附加快检（适用于基线统计 / Logistic / 列线图 / ML）

若项目目录存在 `01_baseline`、`02_Logistic`、`03_Nomogram`、`04_ML_Modeling` 等模块，应把它视为临床统计项目并额外完成以下检查：

- [ ] 基线统计方向性逐条核对：连续变量比较方向、分类变量高水平占比方向、显著性与描述一致
- [ ] Logistic 流程完整：单因素 → VIF → 多因素 结果链齐全
- [ ] 方法-代码一致性：声称逐步回归需找到 `step()` / `stepAIC()` / `stepwise()`；声称 LASSO 需找到 `glmnet` / `cv.glmnet`
- [ ] 列线图模块完整：Nomogram / calibration / DCA / ROC 是否真实存在
- [ ] ML 指标完整：训练集、测试集、AUC/Accuracy/Sensitivity/Specificity 是否成套
- [ ] SHAP 不只看图件，优先核对是否交付数值导出表
- [ ] 全文搜索生存分析模板残留：`死亡|生存|时间尺度|不同时间|hazard|survival|Kaplan-Meier|Cox`

如自动预检查已启用 `临床统计项目检查`，仍不得跳过 Agent 方向性复核；该检查器主要负责快速发现缺项、模板残留和方法-代码不一致，不能代替逐句判读。

#### 0.6 风险分层判断

**分层规则**：
- 🔴 **FATAL**: 最高优先级问题，必须记录并在逐项证据复核中优先展开
- 🟠 **CRITICAL**: 严重问题，必须进入最终问题列表
- 🟡 **WARNING**: 警告问题，建议补充复核记录

**输出结果**：
```
风险分层状态: ✅ 低风险 / ⚠️ 需重点复核
可以继续审核: 是（自动检查应始终输出完整问题清单）

下一步:
    输出自动检查报告 → 启动当前主线Agent Team协作方案进行逐项证据复核
    如需回归比对 → 修正后重新运行auto_audit_pipeline.py
```

### 预检查报告

**报告位置**: `check_reports/auto_audit/auto_audit_report_*.md`

**报告内容**：
- 项目编号一致性结果
- 术语主题匹配结果
- 跨模块数据流验证结果
- 风险分层状态
- 逐项证据复核优先级建议

### 错题集闭环（⚠️ 必做）

审核启动前，Lead Auditor 必须读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把与当前项目相同或相近的历史错误模式列入重点复核项。

要求：
- 命中错题集的内容必须在当前项目中加严核验，必要时写入 `fact_check_list.md` 或高风险模块核对项。
- 错题集只提供风险提示，不能直接套用历史项目结论；必须回到当前报告、代码、结果文件和图表证据独立判断。
- Round 4 最终报告完成后、运行 `finalize_audit.py` 前，必须把本次典型错误点沉淀到 `lessons/`。
- 单条错题至少记录：错误类型、具体表现、触发场景、证据依据、正确标准、下次审核提醒、严重程度。
- 若本次无新增可复用错误模式，应在 `final_review_report.md` 的经验总结/复盘处明确写明“无新增错题集沉淀项”。

### 最终收口（⚠️ 必做，优先走 `finalize_audit.py`）

当 `final_review_report.md` 和错题集复盘完成后，**必须立即**运行以下命令完成最终收口与交付：

```bash
python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>
```

要求：
- `final_review_report.md` 为唯一真源
- `audit_report.html` 必须由脚本派生生成
- 默认通过 `finalize_audit.py` 统一触发 lint / autofix / backfill / state sync / HTML 发布 / 自动归档
- 不允许只发布不移动；HTML 发布成功后必须移动到 `raw/已AI审核一次`，归档失败则本次收口失败
- 若只是单独调试 HTML 派生步骤，才直接运行 `ensure_review_html.py`
- **此步骤为必做步骤，不完成最终收口不算审核交付完成**
- **持续恢复规则**：`finalize_audit.py` 的本地可恢复失败（缺交付物、schema/contract/lint 不一致、清单映射错误、HTML 发布或归档预检失败）不得作为审核结束点。Lead 必须记录失败阶段，按最小范围修复或重新分派，复跑对应本地门与同一官方 finalize 路径；只有取得正式通知 `sent` 回执并验证归档，或遇到需要新增用户授权/外部状态变化的不可恢复失败，才能结束或向用户请求处理。

> **教训**: 25YHB656F 审核中遗漏了最终 HTML 交付步骤，现统一纳入 `finalize_audit.py` 收口。

### 三路审核触发规则（强制，小切片执行）

- 只要进入“正式审核”而不是“咨询/框架讨论”状态，Lead Auditor 就必须在 Layer 2 之后启动小切片 Sub-Agent，并最终汇总为三路结果。
- Lead Auditor 的默认职责是监工、分工、整合、仲裁和最终门禁；不得把主线程当作全文审核执行者。
- Lead 不应在主线程直接展开长报告、长日志、完整清单、完整 JSON、完整通知 metadata 或大证据；正式审核证据必须由 Sub-Agent 落盘，Lead 只读取短状态、证据路径、计数和最终必要片段，避免 leader 触发 remote compact。
- 禁止把完整项目一次性交给 1 个 Sub-Agent 或 3 个“大而全” Sub-Agent 审核；三路是收敛口径，不是大任务分发口径。
- 必须先读取 `agent_prompts/agent_slice_manifest.json`，再按 `agent_prompts/slices/*.md` 分批执行；每批最多 4 个切片。
- 每个切片必须写入 `agent_results/slices/*.json`；聊天最多返回 5 行，只返回状态、输出路径、发现数量、最高严重度和阻断项。
- 正式判断型 Sub-Agent 必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high。`fast/mini/explore` 只能用于定位、清单、schema、grep，不能裁定严重度、统计适用性、高风险模块或最终仲裁。若子代理触发 remote compact/context loss，必须先继续拆分切片再重试，禁止原范围重跑。
- 每批切片完成后必须把进度写入 `review_event_log.jsonl`，并更新项目内 `subagent_supervision_summary.json`；不得依赖外部运行时目录保存唯一 checkpoint。
- 用户说“开始审核某项目 / 审核下一个 / 现在重审某项目”时，默认视为已经授权完整执行主线，不再额外追问是否启用三路。
- 只有当用户明确要求“单人初筛”“暂不走三路”“只看某一块”时，才允许降级。

### 最终报告：错误机制优先，而非问题堆叠

- 正文开头必须是“提交阻断问题”，最多 5 项；它们只包括会改变提交结论、关键主张可信度或独立复现能力的问题。
- 每项按**错误点 → 证据 → 修订要求**写。错误点必须说出“当前材料实际写/做了什么”和“具体错在哪里”；修订要求必须说明应如何计算、表述或补交。证据必须给出报告行号、结果/代码/图表的精确路径或可核验数值；没有具体证据的怀疑不能进入核心正文。
- 不把“影响”设为固定字段。只有在不说明就无法理解提交结论时，才用一句说明结论边界；不得用“可能影响可信度”等泛泛表述掩盖错误机制。
- 其余已裁定问题在“其他已裁定问题”中以 `S-` 编号简明呈现；每项同样保留**错误点、证据、修订要求**，不写成只含 finding 编号的概览表。
- 逐分析点表只保留已裁定问题，作为问题编号的索引，不得替代对错误机制和修订要求的直接说明；不得默认再写“问题证据展开”。
- 收敛记录、机械检查、完整仲裁、文件盘点、监督记录以及未成立候选项的排除理由属于审核底稿，不写入正式报告正文或 HTML 卡片；只有用户明确要求争议复核时，才另附对应摘录。

### 系统性文本搜索（⚠️ 必做，不可跳过）

在 Round 0 阶段或 Round 1 之前，**必须**执行系统性文本搜索，发现批量复制粘贴错误、术语混用等问题：

```bash
python script_utils/systematic_text_search.py <项目路径>
```

**检查重点**：
- 细胞类型中英翻译（如 Macrophages→巨噬细胞 而非"局势细胞"）
- 自定义分组缩写一致性（如 HMS/LMS 不与 HLS 混用）
- R 包名称拼写（如 IOBR 而非 IBOR）
- 全文项目编号统一
- 临床统计项目中的生存分析模板残留（如 死亡风险、不同时间结局、Cox 回归、Kaplan-Meier）

> **教训**: 25YYS110F 审核中抽样检查仅发现 1-2 处复制粘贴错误，系统搜索后发现 5 处；25YHB656F 发现 6 处缩写混用。

### 可选专项检查：术语 / 数据库 / URL

当项目存在较高的术语混用、数据库名称错误、URL/功能描述不可靠风险时，可在 Round 0 后或 Round 1 前补做术语专项检查：

```bash
python result_review_framework/scripts/terminology_audit.py --project-dir <项目路径> --project-id <项目编号> --diseases <疾病中文名> <疾病英文名>
```

使用说明见 `guides/TERMINOLOGY_AUDIT_GUIDE.md`。

### 复审触发与执行

> **注意**: 复审包括 Layer 2 全量视觉审核（Round 1）和 Layer 4 最终复核（Round 5）。

满足以下任一条件时，应进入复审，而不是停留在初审结论：

- 补交了结构化结果文件、原始数值文件或中间检索表
- 修正了正文中的数据库、URL、图注、表格或参考文献问题
- 原审核中仍有 `有问题`、`证据不足`、`未覆盖` 的分析点

复审执行规则：

1. 默认先做定向复审，只检查新增材料、未决事项、高风险分析点和可能改变结论的段落。
2. 复审必须输出“原结论是否变化”的明确判断。
3. 复审必须单独记录新增发现、已关闭事项和仍未关闭事项。
4. 若第 1 次复审后仍有关键未决事项，可进入第 2 次复审；第 2 次后仍不闭环，则维持不放行结论，不再无限循环。

---

## 三路独立审核与交叉收敛
> **完整协议**: [CONVERGENCE_REVIEW_PROTOCOL.md](CONVERGENCE_REVIEW_PROTOCOL.md)
> **Agent 执行方案**: [agent_plans/AGENT_TEAM_PLAN.md](agent_plans/AGENT_TEAM_PLAN.md)

Round 1（专业组检查）和 Round 2（交叉验证）已升级为**小切片 Sub-Agent + 三路汇总 + 迭代收敛**模式：

### 执行摘要

1. **Round 0**: Auto-Precheck → Layer 0 (预解析) + Layer 1 (21 检查器)
2. **Round 1**: Layer 2 全量视觉审核 — Lead Auditor 逐图查看全部 Figure，产出 `figure_audit.md`
3. **Round 2**: 分批启动小切片 Sub-Agent (Layer 3)，每个切片只处理一个窄范围并落盘到 `agent_results/slices/`
4. **Round 3**: Lead Auditor 将切片汇总成 3 方结果并进行交叉比对 → 迭代收敛（最多 3 轮）
5. **Round 4**: Lead Auditor 汇总一致结论 → 生成最终报告初稿
6. **Round 5**: Layer 4 源文本+视觉 最终复核 → 排除假阳性 → 生成最终 HTML

### 关键规则

- 每个小切片 Sub-Agent 只承担明确窄范围，不是全栈完整审核员
- 如果任一 Sub-Agent 触发 remote compact/context loss，Lead 必须把该切片按章节、模块、图号范围、文件组或问题簇继续拆小后重试，禁止按原范围重复启动。
- 小切片 Sub-Agent 之间**不得共享**审核中间结果（独立性原则）；同一路汇总器只读取本路 slice JSON
- 不得复制 Lead 全量上下文给子代理；不得在聊天中粘贴长日志、完整 JSON、完整 Markdown 报告、大表、完整通知 metadata 或内部归档路径
- Lead 只做监工/整合/仲裁，不直接吞入长报告、长日志、完整文件清单或大证据；完整证据必须写入文件，聊天只回短状态、路径、计数和 blocker
- Lead 最终回复最多 8 行；正式审核完成通知只保留状态、时间、项目、报告文件、审核结果和问题统计，不贴摘要、workspace、内部路径或监督 JSON 元数据
- 正式判断型 Sub-Agent 必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high。`fast/mini/explore` 仅可作为检索/定位辅助。若子代理触发 remote compact/context loss，必须先继续拆分切片再重试，禁止原范围重跑
- 交叉比对分四级：共识(3/3) / 多数(2/3) / 单方(1/3) / 分歧(冲突)
- 迭代收敛时构建**问题并集**，只针对分歧点启动小切片复核，不重新启动大范围审核
- 终止条件：3 方结论完全一致 + 无新增 + 无分歧，或达到 3 轮硬限制
- 不允许用"投票多数"替代证据验证
- 审核底稿必须保留“自动机械检查处置表”，逐条写明保留/撤销/降级/升级；正式报告只写经裁定且需要读者处理的问题
- 对分子对接、MD、虚拟敲除等高风险模块，底稿必须分别记录：模块是否真实存在、证据是否充分、是否可复现、结论强度是否被过度外推；正式报告仅在存在已裁定问题时写入对应条目

### Sub-Agent 报告保存规则（强制）

- **每个 Sub-Agent 返回结果后，必须立即保存为 `agent_X_report.md` 文件**（X = a/b/c）
- 保存时机：Sub-Agent 返回 → 立即写文件，不得延迟到收敛阶段
- 交叉收敛完成后，必须生成 `convergence_report.md`，包含完整投票表
- **自检门禁**：在写 `final_review_report.md` 之前，执行检查：
  ```
  agent_a_report.md  ✅ 存在
  agent_b_report.md  ✅ 存在
  agent_c_report.md  ✅ 存在
  convergence_report.md  ✅ 存在
  ```
  4 个文件必须全部存在，否则禁止生成最终报告

### 与下述各阶段的关系

- "第一阶段前的强制产物"中的覆盖矩阵、事实核对、未解决项 → 每个 Sub-Agent 独立产出
- "第一阶段：理解项目"→ 每个 Sub-Agent 独立执行
- "第二阶段：逐模块详细检查"→ 每个 Sub-Agent 独立执行
- "第三阶段：问题分析和报告"→ 由 Lead Auditor 在交叉收敛后统一执行

---

## Layer 2：全量视觉审核
> **设计动机**：Sub-Agent 是纯文本模型，无法查看图片内容。之前框架仅检查图片文件存在与大小，图片内容错误（如阈值线位置错误、基因标注不匹配、copy-paste 残留的他项目标题）完全无法被发现。将视觉审核**前置**于 Sub-Agent 之前（Round 1），使 Sub-Agent 在审核时拥有真实的图片描述，从根源减少图片相关假阳性。

### 执行时机与执行者

- **时机**：Round 0 (Auto-Precheck) 完成后，Round 2 (Sub-Agent 启动) 之前
- **执行者**：Lead Auditor（唯一拥有 `view_image` 工具的角色）
- **范围**：全量——项目中每一张 Figure/Table 图片都必须查看，**不允许抽样**

### 执行步骤

1. **收集图片清单**：从 `report_structure.json` 和 images/ 目录获取完整图片列表
2. **逐图查看**：使用 `view_image` 工具逐张打开每个图片文件
3. **对照报告**：将图片实际内容与 `report_text.txt` 中对应图注/正文描述对比
4. **对照数据**：将图中标注的关键数值与结果 CSV/表格文件对比
5. **记录发现**：每张图产出一条审核记录

### ⛔ 全量执行约束

- 审核报告中必须列出**每张图片的审核结论**（通过/问题/跳过+原因）
- 仅以下图片允许跳过：文件 < 2KB 的装饰图标、封面 logo/二维码
- 最终报告必须包含覆盖率统计：`已审图片数 / 总图片数 (百分比)`
- 若覆盖率 < 100%（排除合理跳过项），报告必须说明未审图片及原因
- **禁止以"时间不足"或"上下文限制"为由做抽样**——宁可分批执行也要全量覆盖
- **自检门禁**：在进入 Layer 3 之前，必须确认 `figure_audit.md` 覆盖率 ≥ 95%（排除装饰图后）。未通过则禁止启动 Sub-Agent

### 逐图核查清单（⚠️ 每张图必查）

- [ ] **文件可渲染**：图片正常显示，无空白/截断/损坏
- [ ] **标题/副标题**：疾病名/数据集名与本项目一致（捕获 copy-paste 残留）
- [ ] **Panel 标注**：A/B/C… 标注清晰，与图注描述的 panel 顺序一致
- [ ] **轴标签**：X/Y 轴标注存在且可读，单位正确（log2FC, -log10(p), Expression level）
- [ ] **图例(Legend)**：存在且类别标签与正文分组名一致
- [ ] **阈值线**（Volcano/Manhattan 等）：虚线位置与报告声明的阈值视觉吻合
- [ ] **标注数值**：图中标注的数值（Up/Down 数量、AUC 值、p 值）与数据文件/报告一致
- [ ] **基因/细胞标注**：图中标注的基因名/细胞类型与报告正文匹配

### 高频图件类型专项检查

| 图件类型 | 核查要点 | 对照数据源 |
|----------|---------|------------|
| Volcano 图 | 标题疾病名、阈值竖线 ±logFC、Up/Down 数量、标注基因名 | DEG 结果表 CSV |
| Heatmap | 色彩梯度方向、基因/样本标签可读、聚类树、行列数 | 输入基因列表 CSV |
| UMAP/tSNE | cluster 标注、细胞类型名称、cluster 数量 | 细胞注释表 CSV |
| Forest 图 | HR/OR 方向（左=保护/右=风险）、参考线=1、变量名 | Cox/Logistic 结果表 |
| ROC 曲线 | 对角线参考线、AUC 标注值 | AUC 数值表 |
| KM 生存曲线 | 分组标签、p 值标注、风险表 | 生存分析结果表 |
| CellChat | 发送/接收方向、数量 vs 强度、细胞类型标签 | CellChat 输出表 |
| 箱线图/小提琴图 | 分组标签、显著性标注 */**、组间差异方向 | 差异分析表 |
| Nomogram | 变量名可读、评分刻度存在 | 模型系数表 |

### 严重性判断

| 发现 | 等级 |
|------|------|
| 图件损坏/空白/截断 | 🔴 CRITICAL |
| 图件标题出现非本项目的疾病名/数据集名 | 🔴 FATAL (copy-paste 残留) |
| 图件显示的数值与数据文件不一致 | 🔴 CRITICAL |
| Panel 标注与图注描述不匹配 | 🟠 MAJOR |
| 轴标签/图例缺失 | 🟡 WARNING |
| 颜色不一致但不影响结论 | 🟡 WARNING |

### Layer 2 产物

产出 `figure_audit.md`，格式：

```markdown
# 全量视觉审核报告

## 审核统计
- 总 Figure 数: N
- 通过: N (✅)
- 有问题: N (❌/⚠️)

## 逐图审核记录

### Figure 1: <文件名>
- 图件类型: Volcano / Heatmap / UMAP / ...
- 标题匹配: ✅/❌
- 数值匹配: ✅/❌ (<具体描述>)
- 标注匹配: ✅/❌
- 发现: <问题描述，无问题则写 "无">
- 等级: ✅ / WARNING / MAJOR / CRITICAL / FATAL

### Figure 2: ...
```

### 与后续 Layer 的关系

- `figure_audit.md` 作为 Layer 3 (Sub-Agent) 的**必要输入**，Sub-Agent 可引用视觉审核结论
- Layer 4 (最终复核) 会回溯验证 Layer 2 发现的高等级图片问题
- Layer 2 **可以发现新问题**（与 Layer 4 不同）

---

## Layer 4：源文本+视觉 最终复核
> **设计动机**：26YHB087F 审核中，Sub-Agent C 报告了 2 个 CRITICAL 级参数不一致问题（DEG 阈值 |log2FC|>1 vs 0.5、CytoHubba 5 种 vs 4 种），经 Lead Auditor 直接阅读报告原文方法段后确认为**假阳性**——报告原文实际与代码一致，是 Sub-Agent C 读错了报告数字。这类 AI 幻觉仅靠交叉收敛无法消除（因为其他 Agent 可能没有检查相同的具体数字），必须由 Lead Auditor 对原文做最终回溯验证。

### 为什么 Layer 3 交叉收敛不够？

| 问题类型 | 交叉收敛能解决？ | 原因 |
|----------|:---:|------|
| 遗漏（漏审模块） | ✅ | 并集策略覆盖 |
| 分歧（同一问题不同判断） | ✅ | 多数+证据原则 |
| 一致错误（3 个 Agent 都犯同样的错） | ❌ | 同质化偏差 |
| AI 幻觉（读错数字/编造引用） | ❌ | 需回溯原始文本 |
| 假阳性（报告实际没问题但被标记） | ❌ | 需逐条验证 |

### Layer 4 执行协议

**触发时机**：Round 4（最终报告汇总）完成后，生成 HTML 之前。

**执行者**：Lead Auditor（不得委托 Sub-Agent）。

**执行步骤**：

1. **提取关键发现清单**：从 `unresolved_items.md` 中收集所有 CRITICAL 和 1/3 单方发现的 MAJOR 项
2. **逐条原文回溯**：对每个关键发现，直接读取 `report_text.txt` 中相关段落的**原始文本**
   - 不得依赖 Sub-Agent 的摘要或引述
   - 必须定位到具体行号，读取完整句子
   - 与代码/结果文件直接对比，形成独立判断
   - 行号仅用于审核底稿；写入正式报告时必须转换为“原 DOCX 文件名 + 章节/图表标题 + 原文短句”，页码仅在固定渲染版本已核验时辅助使用
3. **假阳性标记**：如果原文与 Sub-Agent 描述不符，标记为假阳性(FP)，记录：
   - Sub-Agent 原始报告内容
   - 原文实际内容（含行号）
   - 判定：✅ 一致/假阳性
4. **更新审核产物**：修正四份审核文件（coverage_matrix / fact_check_list / unresolved_items / final_review_report）；最终报告按顶层问题主题组织，但每个独立修订动作必须成为一个“具体错误”，不得合并压缩
5. **记录自纠正**：在 `final_review_report.md` 和 `audit_report.html` 中设立"复核阶段自纠正"专区

### Layer 4 必须回溯的高风险项（⚠️ 强制）

以下类型的 Sub-Agent 发现**必须**进行原文/原图回溯，无论共识级别：

| 高风险类型 | 原因 | 回溯方法 |
|-----------|------|---------|
| 参数不一致（报告 vs 代码） | Sub-Agent 最容易读错数字 | 定位方法段行号，读原文 |
| 参考文献错配 | Agent 可能误判引用编号 | 读参考文献列表原文 |
| 统计方向判断 | p 值方向、HR 方向易翻转 | 读原文具体表述 |
| Figure 编号冲突 | 需确认报告实际使用的编号 | 读原文图注 |
| 数字求和验证 | 千位分隔符、小数点解析易出错 | 读原文数字上下文 |
| 图片内容异常（Layer 2 发现） | 验证视觉发现非误判 | 重新 view_image + 对照数据文件 |

### Layer 4 产物

在最终报告中新增：

```markdown
## 复核阶段自纠正

| # | Sub-Agent 原始报告 | 原文实际 | 结论 |
|---|-------------------|---------|------|
| 1 | <Agent 声称的内容> | <原文行号+内容> | ✅/❌ |
```

### 与其他 Layer 的关系

- Layer 2 (视觉审核) 负责"发现图片问题"→ 产物喂给 Layer 3
- Layer 3 (Sub-Agent) 负责"发现文本/代码/数据问题"（最大化召回率）
- Layer 4 负责"验证所有发现"（最大化精确率）
- Layer 4 **不会发现新问题**，只验证/排除 Layer 2 + Layer 3 的发现
- Layer 4 完成后才能生成最终 HTML

---

## 第一阶段前的强制产物

### A. 覆盖矩阵（必做）

在进入逐模块审核前，必须先建立覆盖矩阵，防止“做了审核但没审全”。

**矩阵最少包含 7 列**：
- 模块 / 数据集 / 暴露 / 图表编号 / 实际文件证据
- 报告是否提及
- 报告是否解释结果
- 是否存在阴性或失败结果
- 证据充分性（充分 / 部分充分 / 不足）
- 是否交付结构化结果文件
- 审核状态

**证据充分性判定要点**：
- 只有图片 / PDF，没有原始数值表或结构化结果表 → 不能判为“充分”
- 表达验证 / ROC 缺检验结果表或 AUC 表 → 证据不足
- 正文声称存在差异比较，但未交付差异统计表 → 证据不足
- 药物预测缺数据库筛选中间表 → 证据不足
- 仅交付筛选后结果，缺少筛选前原始总表或可追溯中间总表 → 证据不足
- 网络分析缺节点表 / 边表 → 证据不足
- 分子对接缺 docking score 表，或缺少盒子大小 / 空腔中心等关键参数记录 → 证据不足
- 分子对接 result 目录中选定的位姿不是 CurPockets_info 中结合能最优的位姿，且无书面理由 → 🔴 CRITICAL（基于 26YHB147F）
- 分子对接结合能汇总表数值与选定 PDB 文件名中的分数不一致 → 🔴 CRITICAL
- MD 缺轨迹原始文件或数值导出（如 xvg / csv） → 证据不足
- 图件存在明显导出异常或内容损坏 → 不能按“文件已交付”计入充分证据

**适用示例**：
- MR 项目：逐个暴露检查是否全部写入报告
- 多数据集项目：逐个 GSE / 队列检查是否全部覆盖
- 富集分析：TopN 条目数、上调/下调结果是否都被描述
- 单细胞项目：每个细胞亚群、轨迹、通讯、空间映射是否都有结果说明
- 分子对接项目：逐个基因-药物对核查位姿选择 ↔ 原始分数 ↔ 汇总表三方一致性

### B. 事实核对清单（必做）

必须至少核对以下 4 类事实：
- 数据库名称与 URL 是否对应：STRING / DrugBank / UniProt / PDB / GeneCards / OMIM
- 数据库功能是否对应：UniProt 不提供 3D 结构，PDB 才提供结构文件
- 英文术语翻译是否对应：euchromatin / heterochromatin 等
- 样本范围用语是否对应：所有样本 / 训练集 / 验证集 / 外部验证集
- 正文中的数据库引用编号是否与参考文献列表一一对应
- 正文提到数据库但未给参考文献编号，视为事实链不闭环
- 数据库编号若指向了别的文献条目，视为参考文献错配

---

## 第零阶段：物种和质量预检（保留原有）

### 步骤0：基因集物种和质量验证

**为什么这是第一步？**
- 基因集物种错误会导致整个分析结果不可用
- 质量问题（如蛋白复合物、非标准命名）会影响结果可靠性
- 这类问题在分析前必须发现，否则浪费大量检查时间

**真实案例教训**：
- 项目25YYS110F使用小鼠基因集(mmc3.gmt)分析人类数据 → 整个免疫浸润模块不可用
- 项目25YYS110F基因集包含4个蛋白复合物基因 → 影响ERGs分析可靠性

#### 0.1 基因集物种验证 ⭐⭐⭐

**检查范围**：
- [ ] 所有原始数据文件（01_Rawdata/）
- [ ] 所有功能分析使用的.gmt文件
- [ ] 所有参考基因集
- [ ] 所有注释数据库

**检查方法**：

**方法1：文件名检查（快速筛选）**
```powershell
# 搜索所有.gmt文件
Get-ChildItem -Path "项目路径" -Filter "*.gmt" -Recurse

# 常见小鼠基因集标识
mmc3.gmt          # Mouse Microarray Cell Compendium 3
mouse*.gmt        # 任何带mouse的gmt文件
mm10_*.gmt        # 小鼠基因组版本mm10
```

**方法2：代码检查（定位使用位置）**
```powershell
# 搜索.gmt文件引用
Select-String -Path "CODE/*.R" -Pattern "\.gmt"

# 检查是否有可疑的小鼠基因集
Select-String -Path "CODE/*.R" -Pattern "mmc3|mouse|mm10"
```

**方法3：基因集文件检查（验证物种标签）**
```powershell
# 检查.gmt文件前几行
Get-Content "结果文件/path/to/file.gmt" -First 5

# 人类基因集示例：
# h.all.v2023.2.Hs.gmt    # Hs = Homo sapiens
# c2.cp.kegg.v2023.2.Hs.gmt
# xCell sigs are human

# 小鼠基因集示例：
# mmc3.gmt               # Mouse
# c2.cp.kegg.v2023.2.Mm.gmt  # Mm = Mus musculus
```

**物种匹配检查表**：

| 分析数据物种 | 基因集物种 | 结果 | 操作 |
|------------|-----------|------|------|
| 人类 (GSE*, H*) | 人类 (Hs, h.all) | ✅ 通过 | 无需操作 |
| 人类 (GSE*, H*) | 小鼠 (Mm, mmc3) | ❌ FATAL | 必须替换 |
| 小鼠 (GSE*M) | 小鼠 (Mm) | ✅ 通过 | 无需操作 |
| 小鼠 (GSE*M) | 人类 (Hs) | ❌ FATAL | 必须替换 |

**常见人类基因集**：
- MSigDB: `*.Hs.gmt` (Hs = Homo sapiens)
- xCell: `xCell_sig.txt` (人类)
- CIBERSORT: `LM22.txt` (人类)
- EPIC: `EPIC_sig.txt` (人类)

**常见小鼠基因集**：
- MSigDB: `*.Mm.gmt` (Mm = Mus musculus)
- mmc3.gmt (Mouse Microarray Cell Compendium)

#### 0.2 基因集质量检查

**检查项目**：

**1) 基因命名格式验证**
```python
# 检查基因名格式
# 人类标准基因名：大写字母，无符号，无数字前缀
# 例如：TP53, ABCB1, RORA

# 错误格式示例：
scf-fbxl5_human        # ❌ 蛋白复合物，包含下划线和连字符
bola3-glrx5_human      # ❌ 蛋白复合物
MT-ND1                 # ⚠️ 线粒体基因（需确认是否保留）
HLA-A                 # ⚠️ HLA基因（需确认是否保留）
IGKV1D-43             # ⚠️ 免疫球蛋白（需确认是否保留）
LINC00152             # ⚠️ lncRNA（需确认是否应该分析）
```

**2) 蛋白复合物基因检测**
```python
# 使用Python检查
import pandas as pd

df = pd.read_csv('final_ERGs.csv')

# 检测蛋白复合物（包含连字符和下划线）
protein_complexes = df[df['gene_name'].str.contains('-', regex=True) & 
                        df['gene_name'].str.contains('_', regex=True)]

print(f"发现 {len(protein_complexes)} 个蛋白复合物基因")
print(protein_complexes)
```

**3) 非标准基因名分类统计**
```python
# 分类统计
categories = {
    'protein_complex': df['gene_name'].str.contains('-', regex=True) & df['gene_name'].str.contains('_', regex=True),
    'mitochondrial': df['gene_name'].str.startswith('MT-'),
    'hla': df['gene_name'].str.startswith('HLA-'),
    'immunoglobulin': df['gene_name'].str.startswith('IG'),
    'lncrna': df['gene_name'].str.startswith('LINC') | df['gene_name'].str.startswith('MIR')
}

for category, mask in categories.items():
    count = mask.sum()
    if count > 0:
        print(f"{category}: {count} 个")
        print(df[mask]['gene_name'].tolist()[:10])  # 显示前10个
```

**质量检查记录表**：

| 检查项 | 结果 | 数量 | 处理建议 |
|-------|------|------|---------|
| 总基因数 | ______ | - | 基准数量 |
| 标准基因名 | ✅/❌ | ______ | 应占绝大多数 |
| 蛋白复合物 | ❌ | ______ | **必须删除** |
| 线粒体基因 | ⚠️ | ______ | 确认是否保留 |
| HLA基因 | ⚠️ | ______ | 确认是否保留 |
| 免疫球蛋白 | ⚠️ | ______ | 确认是否保留 |
| lncRNA | ⚠️ | ______ | 确认是否应该分析 |

#### 0.3 参考数据库物种验证

**检查项目**：
- [ ] 基因组注释文件（如GTEx, Ensembl）
- [ ] 通路数据库（KEGG, Reactome）
- [ ] 蛋白互作数据库（STRING, BioGRID）
- [ ] 转录因子数据库（TRRUST, DoRothEA）

**检查命令**：
```powershell
# 搜索数据库引用
Select-String -Path "CODE/*.R" -Pattern "GTEx|Ensembl|KEGG|Reactome|STRING"

# 检查数据集编号（GSE开头通常是人类）
Select-String -Path "CODE/*.R" -Pattern "GSE[0-9]"
```

**数据集物种判断**：
- GSE* (无M后缀) → 通常是人类数据
- GSE*M (有M后缀) → 可能是小鼠数据
- 需要结合GEO数据库确认

#### 0.4 记录和报告

**记录格式**：
```markdown
### Step 0: 物种和质量预检结果

#### 物种验证
- [ ] 分析数据物种: 人类/小鼠/大鼠
- [ ] 基因集物种: 人类/小鼠/大鼠
- [ ] 物种匹配: ✅/❌

#### 质量检查
- 基因集总数: ______
- 蛋白复合物: ______ (必须删除)
- 非标准基因名: ______ (需验证)

#### 发现的问题
1. 
2. 
3. 

#### 处理建议
- [ ] FATAL: 物种不匹配，必须替换基因集
- [ ] FATAL: 包含蛋白复合物，必须删除
- [ ] WARNING: 包含大量非标准基因名，需确认
```

**如果发现问题**：
- 🔴 **FATAL级别**：物种不匹配 → **停止后续检查，建议重新分析**
- 🔴 **FATAL级别**：包含蛋白复合物 → **建议修正基因集**
- ⚠️ **WARNING级别**：非标准基因名过多 → **需确认分析目的**

**检查完成标准**：
- ✅ 所有基因集物种与分析数据匹配
- ✅ 基因集无蛋白复合物错误命名
- ✅ 非标准基因名已验证并确认合理性

**时间投入**：约10-15分钟
**价值**：避免数小时的无效检查 + 发现FATAL问题

---

## 第一阶段：理解项目（10分钟）

### 步骤1：提取并阅读项目报告 ⭐ 最重要！

```powershell
# 确认报告文件
报告/25YYS110F-数据分析报告-基于scPagwas算法利用转录组联合单细胞分析必需微量元素代谢在肺动脉高压中的作用机制.docx
```

**关键操作**：
- ✅ 使用extract_from_docx提取报告文本
- ❌ 不要使用其他项目的报告！
- ✅ 确认项目编号匹配

**阅读重点**：
1. **研究背景**
   - 研究疾病/表型
   - 研究目标

2. **数据来源**
   - 数据集名称（GSE、GWAS ID等）
   - 样本数量

3. **分析方法**
   - 使用的关键算法
   - 分析流程步骤

4. **术语定义** ⚠️ 非常重要！
   - ERGs = Essential trace element metabolism-Related Genes
   - DEGs = Differentially Expressed Genes
   - 其他缩写词

5. **筛选策略** ⚠️ 关键！
   - "前10个" = top 10 selection
   - "交集" = intersection operation
   - "显著性" = p-value threshold

6. **关键数字**
   - 基因数量（各步骤）
   - 细胞数量/类型
   - 统计指标

### 步骤2：扫描项目结构

```powershell
Get-ChildItem "项目路径"
# 或在审核过程中使用递归搜索确认真实文件分布
# file_search("项目路径/**/*")
```

**自动识别**：
- 项目类型
- 分析模块
- 数据来源
- 关键文件

### 步骤2.5：报告文本质量检查 ⭐ 新增！

**目的**：在开始详细检查前，先检查报告本身的文字质量、专业准确性和逻辑正确性

#### 2.5.1 错字和语法检查
- [ ] 专业术语拼写正确（如基因名、缩写）
- [ ] 数字表达准确（如"100个"vs"100"）
- [ ] 标点符号使用正确
- [ ] 无错别字

#### 2.5.2 描述一致性检查
- [ ] 同一概念在全文中描述一致
- [ ] 术语定义前后一致
- [ ] 数字范围描述清晰（如"约100个"vs"100个"）

#### 2.5.3 专业逻辑和判断标准检查 ⭐⭐⭐ 关键！

**这是最重要的一步！需要检查报告中对方法、标准、判断逻辑的描述是否正确。**

**常见统计方法的判断标准**：

| 方法 | 正确标准 | 常见错误描述 | 严重性 |
|------|---------|-------------|--------|
| **HEIDI检验** | p > 0.05 表示通过（无多效性） | ❌ p < 0.05 通过 | 🔴 严重 |
| **差异表达(DEG)** | p < 0.05 表示显著 | ❌ p > 0.05 显著 | 🔴 严重 |
| **共表达(WGCNA)** | p < 0.05 表示模块显著 | ❌ p > 0.05 显著 | 🔴 严重 |
| **MR分析** | MR-Egger截距p > 0.05 无多效性 | ❌ p < 0.05 无多效性 | 🔴 严重 |
| **Richmond检验** | p > 0.05 无水平多效性 | ❌ p < 0.05 通过 | 🔴 严重 |
| **VIP分数** | >1 表示重要特征 | ❌ <1 重要 | 🟡 中等 |
| **logFC阈值** | |log2FC| > threshold | ❌ logFC > threshold | 🟡 中等 |
| **FDR/FDR** | < 0.05 表示显著 | ❌ > 0.05 显著 | 🔴 严重 |

**检查要点**：
- [ ] 统计方法的判断标准正确（p值方向）
- [ ] 筛选阈值的使用正确（大于vs小于）
- [ ] 方法的解释准确（如"显著性"的含义）
- [ ] 检验的结论正确（"通过"vs"失败"）
- [ ] 专业术语的使用符合领域规范

**示例：HEIDI检验检查**
```
报告描述："HEIDI检验 p < 0.05，表明工具变量可靠"

检查过程：
1. HEIDI检验用途：检测水平多效性
2. 判断标准：p > 0.05 表示无多效性（通过）
3. 报告说：p < 0.05 通过
4. 结论：❌ 完全错误！判断标准反了

建议修改：
✅ 正确："HEIDI检验 p > 0.05，表明工具变量无多效性，结果可靠"
```

**示例：DEG分析检查**
```
报告描述："筛选 adj.P.Val > 0.05 的基因为差异表达基因"

检查过程：
1. DEG判断标准：adj.P.Val < 0.05 表示显著
2. 报告说：> 0.05 显著
3. 结论：❌ 错误！筛选标准反了

建议修改：
✅ 正确："筛选 adj.P.Val < 0.05 且 |log2FC| > 0.5 的基因"
```

**示例：MR分析检查**
```
报告描述："MR-Egger截距 p < 0.05，表明无水平多效性"

检查过程：
1. MR-Egger截距：检验水平多效性
2. 判断标准：p > 0.05 表示无多效性
3. 报告说：p < 0.05 无多效性
4. 结论：❌ 错误！

建议修改：
✅ 正确："MR-Egger截距 p = X.XX (> 0.05)，表明无水平多效性"
```

#### 2.5.4 系统性文本检查 ⭐⭐⭐ 新增！

**为什么需要系统性检查？**
- 抽样检查容易遗漏批量错误
- 复制粘贴其他项目内容会导致多处错误
- 必须用系统化方法才能发现所有问题

**真实案例教训**：
- 项目25YYS110F出现"ARDS+Sepsis"、"脓毒症"等错误项目名称
- 这些错误分布在5个不同位置，抽样检查只发现1-2处
- 使用系统性grep搜索才发现全部错误

##### 2.5.4.1 项目名称系统性搜索

**检查方法**：使用grep/search搜索所有项目名称变体

```powershell
# 方法1: 搜索项目中的疾病名称
# 假设项目是"肺动脉高压(PAH)"
Select-String -Path "check_reports/project_report.txt" -Pattern "PAH|肺动脉高压|肺动脉"

# 方法2: 搜索可能错误的其他疾病名称
Select-String -Path "check_reports/project_report.txt" -Pattern "ARDS|脓毒症|Sepsis|脑卒中|糖尿病"

# 方法3: Python批量检查
import re

with open('check_reports/project_report.txt', 'r', encoding='utf-8') as f:
    content = f.read()
    
# 定义应该出现的术语
should_appear = ['PAH', '肺动脉高压', 'GSE117261', 'GSE113439', 'GSE210248']

# 定义不应该出现的术语（其他项目）
should_not_appear = ['ARDS', '脓毒症', 'Sepsis', '脑卒中', '糖尿病']

for term in should_appear:
    count = content.count(term)
    print(f"✅ 应该出现 '{term}': {count} 次")
    
for term in should_not_appear:
    if term in content:
        count = content.count(term)
        print(f"❌ 不应该出现 '{term}': {count} 次 ← FATAL错误!")
```

**检查清单**：
- [ ] 搜索正确的疾病名称（如"PAH"、"肺动脉高压"）
- [ ] 搜索错误的其他疾病名称（如"ARDS"、"脓毒症"）
- [ ] 搜索数据集编号（如GSE117261）
- [ ] 验证所有出现的位置都是正确的

**记录格式**：
```markdown
### 系统性文本搜索结果

#### 应该出现的术语
| 术语 | 出现次数 | 状态 |
|------|---------|------|
| PAH | 45次 | ✅ 正常 |
| 肺动脉高压 | 32次 | ✅ 正常 |
| GSE117261 | 18次 | ✅ 正常 |

#### 不应该出现的术语
| 术语 | 出现次数 | 位置 | 严重性 |
|------|---------|------|--------|
| ARDS+Sepsis | 2次 | 行111, 114 | 🔴 FATAL |
| 脓毒症 | 1次 | 行65 | 🔴 FATAL |
| GSE151263 | 1次 | 行140 | 🟡 严重 |
```

##### 2.5.4.2 复制粘贴检测

**检测方法**：搜索其他项目的特征词

**步骤1：识别可疑术语**
- 其他疾病的名称（ARDS、脓毒症、脑卒中、糖尿病等）
- 其他数据集编号（GSE151263等）
- 不匹配的分析方法名称

**步骤2：系统性搜索**
```powershell
# 搜索常见其他疾病
$wrong_diseases = @('ARDS', '脓毒症', 'Sepsis', '脑卒中', '糖尿病', 
                    '阿尔茨海默', '乳腺癌', '肺癌')

foreach ($disease in $wrong_diseases) {
    $matches = Select-String -Path "check_reports/project_report.txt" -Pattern $disease
    if ($matches) {
        Write-Host "发现错误术语 '$disease': $($matches.Count) 处" -ForegroundColor Red
        $matches | ForEach-Object { Write-Host "  行$($_.LineNumber): $($_.Line.Trim())" }
    }
}
```

**步骤3：判断严重性**
- 🔴 **FATAL**：出现其他项目的疾病名称（如ARDS+Sepsis出现在PAH项目中）
- 🔴 **FATAL**：出现其他项目的数据集编号
- 🟡 **严重**：出现不匹配的方法名称
- 🟡 **中等**：出现少量其他项目术语但在上下文中合理（如对比研究）

**步骤4：定位和记录**
```powershell
# 定位到具体行号
$matches = Select-String -Path "check_reports/project_report.txt" -Pattern "ARDS+Sepsis" -Context 2

foreach ($match in $matches) {
    Write-Host "=== 行 $($match.LineNumber) ===" -ForegroundColor Yellow
    Write-Host "前文: $($match.Context.PreviousContext)"
    Write-Host "错误: $($match.Line.Trim())"
    Write-Host "后文: $($match.Context.PostContext)"
    Write-Host ""
}
```

##### 2.5.4.3 数据集编号一致性检查

**检查方法**：
```powershell
# 提取所有GSE编号
$matches = Select-String -Path "check_reports/project_report.txt" -Pattern "GSE[0-9]+"

# 统计出现次数
$gse_counts = @{}
foreach ($match in $matches) {
    $gse = $match.Matches.Value
    if ($gse_counts.ContainsKey($gse)) {
        $gse_counts[$gse]++
    } else {
        $gse_counts[$gse] = 1
    }
}

# 报告
$gse_counts.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "$($_.Key): $($_.Value) 次"
}
```

**验证逻辑**：
- 报告中提到的数据集编号应该与CODE中使用的编号一致
- 不应该出现报告中未提到的数据集编号
- 不应该出现项目以外的数据集编号

**记录格式**：
```markdown
### 数据集编号一致性检查

| 数据集编号 | 报告中出现 | 代码中出现 | 状态 |
|-----------|-----------|-----------|------|
| GSE117261 | ✅ 18次 | ✅ 有 | ✅ 一致 |
| GSE113439 | ✅ 12次 | ✅ 有 | ✅ 一致 |
| GSE210248 | ✅ 15次 | ✅ 有 | ✅ 一致 |
| GSE151263 | ❌ 1次 | ❌ 无 | ❌ 错误（行140） |
```

##### 2.5.4.4 文本错误严重性分级

| 错误类型 | 示例 | 严重性 | 影响 | 处理建议 |
|---------|------|--------|------|---------|
| 错误的项目名称 | "ARDS+Sepsis"出现在PAH项目 | 🔴 FATAL | 暴露复制粘贴，质疑原创性 | 立即修正 |
| 错误的疾病名称 | "脓毒症"出现在PAH项目 | 🔴 FATAL | 暴露复制粘贴，质疑原创性 | 立即修正 |
| 错误的数据集编号 | GSE151263（应该是GSE210248） | 🟡 严重 | 引起混淆 | 修正 |
| 错误的基因名 | "ABCBA"（应该是ABCB1） | 🟡 严重 | 专业性受质疑 | 修正 |
| 基因名大小写错误 | "tp53"（应该是TP53） | 🟢 轻微 | 可读性问题 | 建议修正 |

**FATAL级文本错误判断标准**：
- 出现其他项目的疾病名称 → **FATAL**
- 出现其他项目的特征术语 → **FATAL**
- 多处(>3处)出现错误项目名称 → **FATAL**，表明系统性复制粘贴

**为什么这是FATAL？**
1. 暴露质量控制缺失
2. 质疑报告原创性
3. 可能存在其他未发现的复制粘贴内容
4. 严重影响可信度

#### 2.5.5 分析流程逻辑检查
- [ ] 分析流程描述完整
- [ ] 步骤之间逻辑连贯
- [ ] 因果关系清晰
- [ ] 无矛盾陈述

**示例**：
```
❌ 逻辑矛盾：
- 报告说："筛选出11个候选基因"
- 后面又说："经过三方交集得到9个基因"
- 但没有说明11如何变9

✅ 逻辑清晰：
- 报告说："筛选出11个候选基因"
- 明确说明："LASSO筛选9个，SVM筛选10个，RF取前10个"
- 清楚结论："三方交集得到9个基因（ABCB1, RORA, ...）"
```

#### 2.5.5 参数和阈值检查
- [ ] 参数设置符合领域规范
- [ ] 阈值选择有依据
- [ ] 参数方向正确（大于vs小于）

**记录格式**：
```markdown
### 报告文本质量检查

| 问题类型 | 位置 | 问题描述 | 严重性 |
|---------|------|---------|-------|
| 错字 | 页X | XXX应该是XXX | 🟡 |
| 不一致 | 第Y章 | 前面说A后面说B | 🔴 |
| 方法错误 | 第Z章 | HEIDI p<0.05通过（应该是>0.05）| 🔴 |
| 逻辑矛盾 | 第W章 | 流程描述不清 | 🔴 |
```

**重要提醒**：
- 🔴 **严重问题**：方法判断标准错误（如p值方向反了）会导致结论完全错误
- 这类错误比错字严重得多，必须在第一步就发现
- 需要具备专业知识才能判断，必要时查阅文献或指南

### 步骤3：创建检查目录

```powershell
python init_check.py "项目路径"
```

**生成内容**：
- ..\reports\check_[项目ID]\
  - project_scan_report.md
    - project_config.json
  - scripts/
  - reports/

---

## 第二阶段：逐模块详细检查（核心）⭐ 重要更新！

### ⭐⭐⭐ 数字验证优先级表（最重要！）

**来自26YTY013F项目的教训**: DEG数量错误442%导致审核不合格

**P0级数字（必须验证，错误即不合格）**:
| 数字项 | 报告位置 | 验证文件 | 验证方法 |
|--------|----------|----------|----------|
| DEG总数 | 差异分析章节 | `results/02_DeAnalysis/DEGs sig.csv` | `len(df)` |
| 上调基因数 | 同上 | 同上 | `sum(df['Regulated']=='up')` |
| 下调基因数 | 同上 | 同上 | `sum(df['Regulated']=='down')` |
| logFC阈值 | 方法章节 | 代码/文件名 | `abs(logFC) > threshold` |
| 基因集总数 | 数据来源 | `results/00_rawdata/` | 去重统计 |

**P1级数字（重要验证）**:
| 数字项 | 验证文件 | 验证方法 |
|--------|----------|----------|
| WGCNA模块基因数 | `results/04_WGCNA/moduleGene/*.txt` | 统计各模块 |
| ML筛选结果数 | `results/07_ML/*.txt` | 逐个文件统计 |
| 交集基因数 | `results/04_WGCNA/Module*.csv` | `len(df)` |
| 富集通路数 | `results/05_Enrichment_Analysis/` | 结果文件统计 |

**数字验证流程**:
```python
# Step 1: 从报告中提取数字
# Step 2: 定位对应文件
# Step 3: 用代码统计（不要手数！）
# Step 4: 对比差异
# Step 5: 差异>5%记录，>20%标记严重问题
```

**Python验证示例**:
```python
import pandas as pd

# DEG验证
deg = pd.read_csv('results/02_DeAnalysis/DEGs sig.csv')
print(f"DEG总数: {len(deg)}")
print(f"上调: {sum(deg['Regulated']=='up')}")
print(f"下调: {sum(deg['Regulated']=='down')}")

# 基因集验证
import glob
pyro_genes = set()
for f in glob.glob('results/00_rawdata/**/*.csv'):
    df = pd.read_csv(f)
    pyro_genes.update(df.iloc[:, 0].dropna().tolist())
print(f"细胞焦亡基因: {len(pyro_genes)}")
```

---

### ⭐ 检查策略：逐模块验证

```
对于每个分析模块（01_Rawdata → 02_DEG → 03_WGCNA ...）：

┌─────────────────────────────────────┐
│ 模块X检查流程                        │
├─────────────────────────────────────┤
│ 1. 报告描述记录                      │
│    - 记录报告中对模块X的描述         │
│    - 记录关键数字（输入/输出）       │
│    - 记录方法描述                    │
│                                      │
│ 2. 结果文件验证                      │
│    - 找到模块X的结果文件             │
│    - 统计实际数字                    │
│    - 与报告描述对比                  │
│    - 记录：一致/不一致               │
│                                      │
│ 3. 代码实现验证                      │
│    - 找到模块X的代码文件             │
│    - 理解分析逻辑                    │
│    - 检查参数设置                    │
│    - 确认：描述错了？结果错了？都对？│
│                                      │
│ 4. 问题判断                          │
│    - 如果不一致：                    │
│      ✓ 报告描述错误 → 报告问题       │
│      ✓ 结果文件错误 → 分析问题       │
│      ✓ 代码实现错误 → 代码问题       │
│      ✓ 都没错但不同 → 说明差异原因   │
│                                      │
│ 5. 记录检查结果                      │
│    - 模块状态：✅/⚠️/❌              │
│    - 发现的问题列表                  │
│    - 问题定位（报告/文件/代码）       │
└─────────────────────────────────────┘

然后进入下一个模块...
```

---

### 步骤4：逐模块详细检查

#### 🔍 模块检查示例：01_Rawdata

**第一步：记录报告描述**
```markdown
### 01_Rawdata 模块检查

报告描述：
- ERGs（必需微量元素代谢相关基因）数量：XXX个
- 数据来源：XXX数据库/文献
- 文件名：final_ERGs.csv
```

**第二步：验证结果文件**
```powershell
# 检查文件
ls 结果文件/01_Rawdata/

# 统计实际数量
$ergs = Import-Csv "结果文件/01_Rawdata/final_ERGs.csv"
Write-Host "实际ERGs数量: $($ergs.Count)"
```

```markdown
结果文件验证：
- ✅ 文件存在：final_ERGs.csv
- 实际数量：XXX个基因
- 与报告对比：✅一致 / ❌不一致
```

**第三步：验证代码实现**
```r
# 查看 CODE/01_Rawdata_GSE117261.R
# 理解：
# 1. 数据是如何加载的？
# 2. 是否有筛选？
# 3. 参数设置是什么？
```

```markdown
代码验证：
- 代码文件：01_Rawdata_GSE117261.R
- 分析逻辑：[描述]
- 参数设置：[记录关键参数]
- 与报告一致性：✅ / ⚠️ / ❌
```

**第四步：问题判断**

如果发现不一致：
```markdown
### 问题诊断

⚠️ 重要：必须包含完整的文件路径！

发现不一致：
- 报告说：XXX个基因
- 实际文件：YYY个基因
- 文件路径：[项目根目录]/结果文件/子目录/具体文件.csv

可能原因分析：
1. 报告描述错误？
   - 检查报告其他章节是否有矛盾描述
   - 检查是否有笔误

2. 结果文件错误？
   - 检查代码执行时间
   - 检查是否有中间步骤遗漏
   - 确认是否读取了正确的文件

3. 代码实现错误？
   - 检查筛选逻辑
   - 检查参数设置
   - 定位具体代码行号

4. 描述不清晰？
   - 可能"XXX个"指筛选前的数量
   - 可能YYY个是去重后的数量

文件路径格式要求：
- ✅ 正确：`26YTY013F-数据分析结果/results/02_DeAnalysis/DEGs sig.csv`
- ✅ 正确：`results/02_DeAnalysis/DEGs sig.csv` (在明确项目上下文时)
- ❌ 错误：`DEGs sig.csv` (不完整)
- ❌ 错误：只写"结果文件" (无路径)

结论：[具体判断]
```

**第五步：记录结果**
```markdown
### 01_Rawdata 检查结果

状态：✅ 通过 / ⚠️ 警告 / ❌ 错误

问题列表：
- [ ] 无问题
- [ ] 问题1：...
- [ ] 问题2：...

问题定位：
- 📄 报告问题：是/否
- 📊 结果文件问题：是/否
- 💻 代码问题：是/否

备注：[其他说明]
```

---

#### 🔍 模块检查示例：02_DEG

**第一步：记录报告描述**
```markdown
### 02_DEG 模块检查

报告描述：
- 数据集：GSE117261
- DEG总数：415个
  - 上调：222个
  - 下调：193个
- 阈值：|log2FC| > 0.5, adj.P.Val < 0.05
- 参考基因组：XXX
```

**第二步：验证结果文件**
```powershell
# 检查文件
ls 结果文件/04_DEG_GSE117261/

# 统计实际数量
$deg = Import-Csv "结果文件/04_DEG_GSE117261/DEG_logFC0.5.csv"
$up = ($deg | Where-Object { $_.logFC -gt 0 }).Count
$down = ($deg | Where-Object { $_.logFC -lt 0 }).Count
Write-Host "上调: $up, 下调: $down, 总计: $($deg.Count)"
```

```markdown
结果文件验证：
- ✅ 文件存在：DEG_logFC0.5.csv
- 实际数量：
  - 总计：415个 ✅
  - 上调：222个 ✅
  - 下调：193个 ✅
- 阈值验证：[检查logFC和P.Value列]
- 与报告对比：✅完全一致
```

**第三步：验证代码实现** ⭐⭐⭐ **关键新增：代码-报告参数一致性检查！**

```r
# 查看 CODE/02_DEG_GSE117261.R
library(limma)
# 关键参数：
logFC_cutoff <- 0.5
fdr_cutoff <- 0.05
# 分析逻辑：标准的limma流程
```

**⚠️ 关键检查：代码参数必须与报告描述一致！**

来自26YTY013F项目的教训：
- **报告声称**: logFC阈值 = 1
- **代码实际**: foldChange = 0.5
- **结果**: DEG数量差异443%（报告548个 vs 实际2977个）

**代码-报告一致性检查清单**:
| 参数类型 | 报告描述 | 代码实际 | 一致性 |
|---------|---------|---------|--------|
| logFC阈值 | 1 | 0.5 | ❌ 不一致！ |
| p-value阈值 | 0.05 | 0.05 | ✅ 一致 |
| 筛选方向 | abs(logFC) > threshold | abs(logFC) > foldChange | ✅ 一致 |

**检查方法**:
```python
# Step 1: 从报告中提取参数描述
# Step 2: 在代码中搜索对应参数
# Step 3: 逐一对比验证
# Step 4: 发现不一致立即记录

# 示例：检查logFC阈值
import re

# 从报告提取："logFC阈值设置为1"
report_threshold = 1

# 从代码提取：foldChange = 0.5
with open('scripts/r.02_DeAnalysis.R', 'r') as f:
    content = f.read()
    match = re.search(r'foldChange\s*=\s*([\d.]+)', content)
    if match:
        code_threshold = float(match.group(1))
        if abs(code_threshold - report_threshold) > 0.01:
            print(f"❌ 严重问题：代码阈值({code_threshold}) != 报告阈值({report_threshold})")
```

```markdown
代码验证：
- ✅ 代码文件：02_DEG_GSE117261.R
- ✅ 分析逻辑：标准limma差异分析
- ⚠️ 参数设置：logFC>0.5（代码） vs logFC>1（报告）→ **不一致！**
- ❌ 与报告不一致：参数不匹配
```

**第四步：问题判断**
```markdown
### 问题诊断

🔴 发现严重不一致：
- 报告说：logFC阈值=1，应得到约548个DEG
- 代码用：foldChange=0.5，实际得到2977个DEG
- 结果文件：2977个DEG（与代码一致）
- **结论**：报告描述错误，代码实际执行正确
- **影响**：报告与代码执行脱节，严重影响可信度
```

**第五步：记录结果**
```markdown
### 02_DEG 检查结果

状态：✅ 完全通过

问题列表：
- [x] 无问题

问题定位：
- 📄 报告问题：否
- 📊 结果文件问题：否
- 💻 代码问题：否

备注：分析流程标准，结果准确
```

---

#### 🔍 模块检查示例：08_Machine（机器学习）

**第一步：记录报告描述**
```markdown
### 08_Machine 模块检查

报告描述：
- 候选基因：11个（来自DEG∩WGCNA∩scPagwas∩ERGs）
- LASSO筛选：9个基因
- SVM筛选：10个基因
- RF筛选：前10个基因（按重要性）
- 三方交集：9个基因
- 验证后：2个基因（ABCB1, RORA）
```

**第二步：验证结果文件**
```powershell
# 逐个文件验证
$lasso = Import-Csv "结果文件/08_Machine/01_PAH_lasso_genes.csv"
$svm = Import-Csv "结果文件/08_Machine/04_PAH_svm_gene.csv"
$rf = Import-Csv "结果文件/08_Machine/08_PAH_RF_features_top10.csv"
$intersection = Import-Csv "结果文件/08_Machine/10_PAH_common_genes.csv"
$final = Import-Csv "结果文件/11_Nomo/01_final_key_gene.csv"

Write-Host "LASSO: $($lasso.Count)"
Write-Host "SVM: $($svm.Count)"
Write-Host "RF前10: $($rf.Count)"
Write-Host "三方交集: $($intersection.Count)"
Write-Host "最终: $($final.Count)"
```

```markdown
结果文件验证：
- ✅ LASSO：9个基因
- ✅ SVM：10个基因
- ✅ RF前10：10个基因
- ✅ 三方交集：9个基因
- ✅ 最终基因：2个基因
- 与报告对比：✅完全一致
```

**第三步：验证代码实现**
```r
# 查看 CODE/09_Machine_GSE117261.R
# LASSO
lasso_model <- cv.glmnet(x, y, alpha=1)  # alpha=1表示LASSO
# 提取非零系数基因
lasso_genes <- rownames(coef(lasso_model))[coef(lasso_model)!=0]

# SVM
svm_model <- svm(x, y, cost=best_cost)
# 提取最优准确率对应的基因

# RF
rf_model <- randomForest(x, y, importance=TRUE)
rf_importance <- importance(rf_model)
# ⚠️ 关键：取前10个
rf_top10 <- head(rf_importance, 10)
```

```markdown
代码验证：
- ✅ RF实现：top=10（与报告"前10个"一致）
- ✅ 三方交集逻辑正确
- ✅ 表达验证：训练集+验证集独立检验
```

**第四步：问题判断**
```markdown
### 问题诊断

⚠️ 初步疑问：为什么11→9→2？

代码分析：
1. 11个候选基因 → ML筛选
2. RF取前10，GZMA排第11被排除 ✅
3. 三方交集自然排除 ✅
4. 表达验证进一步筛选到2个 ✅

✅ 结论：流程完全合理，每步筛选有明确依据
```

**第五步：记录结果**
```markdown
### 08_Machine 检查结果

状态：✅ 完全通过

问题列表：
- [x] 无问题（初始误解已澄清）

问题定位：
- 📄 报告问题：否
- 📊 结果文件问题：否
- 💻 代码问题：否

备注：
- 报告描述清晰准确
- RF"前10个"策略正确
- 表达验证逻辑严谨
- 结果可追溯性强
```

---

### ⭐ 问题诊断决策树

```
发现报告描述与结果文件不一致
         │
         ▼
    ┌──────────────┐
    │ 检查代码实现 │
    └──────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 代码与     代码与
 报告一致   结果一致
    │         │
    ▼         ▼
 📄报告问题  📊结果问题
            │
            ▼
      检查代码逻辑
            │
      ┌─────┴─────┐
      │           │
      ▼           ▼
   逻辑正确    逻辑错误
      │           │
      ▼           ▼
   📊结果问题  💻代码问题
```

---

### 步骤5：所有模块检查汇总

```markdown
## 模块检查汇总表

| 模块 | 报告 | 结果 | 代码 | 状态 | 问题 |
|------|------|------|------|------|------|
| 01_Rawdata | ✅ | ✅ | ✅ | ✅ | 无 |
| 02_DEG | ✅ | ✅ | ✅ | ✅ | 无 |
| 03_WGCNA | ✅ | ⚠️ | ✅ | ⚠️ | 数量略差 |
| 08_Machine | ✅ | ✅ | ✅ | ✅ | 无 |
| ... | ... | ... | ... | ... | ... |

总体统计：
- 完全通过：X个
- 有警告：Y个
- 有错误：Z个
```

---

## 第三阶段：问题分析和报告（10-15分钟）
│      ✓ 结果文件错误 → 分析问题       │
│      ✓ 代码实现错误 → 代码问题       │
│      ✓ 都没错但不同 → 说明差异原因   │
│                                      │
│ 5. 记录检查结果                      │
│    - 模块状态：✅/⚠️/❌              │
│    - 发现的问题列表                  │
│    - 问题定位（报告/文件/代码）       │
└─────────────────────────────────────┘

然后进入下一个模块...
```

### 步骤4：验证文件和结果（对照报告）

#### 4.1 项目结构检查

```python
from templates.check_structure import StructureChecker

checker = StructureChecker(project_path, project_id)
checker.check_all()
```

**检查清单**：
- [ ] 结果文件夹结构完整
- [ ] 所有关键CSV文件存在
- [ ] 代码脚本完整
- [ ] 报告和方案文件存在

**⚠️ 注意**：目录检查必须递归！
```python
# ❌ 错误：只看顶层
list_dir("结果文件/02_scRNA_GSE210248")

# ✅ 正确：递归检查
file_search("结果文件/02_scRNA_GSE210248/**/*")
```

#### 4.2 DEG分析检查（如有）

```python
from templates.check_deg import DEGChecker

checker = DEGChecker(project_path, project_id)
checker.check_deg(
    expected_total=从报告中提取,
    expected_up=从报告中提取,
    expected_down=从报告中提取,
    logfc_threshold=从文件名或代码中提取
)
```

**关键验证**：
- DEG总数 = 报告数量？
- 上调/下调分类正确？
- logFC阈值与描述一致？

#### 4.3 机器学习检查（如有）

```python
from templates.check_ml import MLChecker

checker = MLChecker(project_path, project_id)

# 先查看报告中的筛选策略
# - LASSO: 非零系数
# - SVM: 最优准确率
# - RF: 前10个（重要！）

success, intersection = checker.check_intersection(
    lasso_file="path/to/lasso.csv",
    svm_file="path/to/svm.csv",
    rf_file="path/to/rf.csv",
    expected_count=从报告中提取
)
```

**关键验证**：
- [ ] 各算法筛选基因数正确
- [ ] 三者交集计算正确
- [ ] 理解筛选策略（如RF的"前10个"）
- [ ] 理解后续验证步骤

**⚠️ 常见误解**：
- ERGs文件在`01_Rawdata/` = 原始数据，不是ML结果！
- "前10个"是筛选标准，不是结果描述
- 验证步骤（如表达验证）会进一步减少基因数量

#### 4.4 其他模块检查

根据项目类型选择：
- 单细胞分析（check_scrna.py）
- WGCNA分析
- 富集分析
- PPI网络分析
- 分子对接
- 等

### 步骤5：验证代码实现

对照报告描述，检查代码实现：

```python
# 示例：验证RF的top参数
# 报告说："选前10个"
# 代码应该有：top=10 或类似参数

# 在CODE/09_Machine_GSE117261.R中：
rf_importance <- importance(rf_model)
rf_importance_df <- head(rf_importance, 10)  # 前10个
```

**验证重点**：
- [ ] 参数设置与报告一致
- [ ] 计算逻辑正确
- [ ] 结果文件输出路径

---

### 5.1 参数一致性检查 ⭐⭐⭐ **新增！**

**来自26YTY013F项目的教训**：
- 报告说logFC阈值=1，代码实际用foldChange=0.5
- 导致DEG数量差异443%

**检查方法**:
```python
import re

# 从报告中提取参数
report_threshold = 1  # "logFC阈值设置为1"

# 从代码中搜索对应参数
with open('scripts/r.02_DeAnalysis.R', 'r') as f:
    content = f.read()
    match = re.search(r'foldChange\s*=\s*([\d.]+)', content)
    if match:
        code_threshold = float(match.group(1))
        if abs(code_threshold - report_threshold) > 0.01:
            print(f"❌ 严重：代码({code_threshold}) != 报告({report_threshold})")
```

---

### 5.2 外部文件路径检查 ⭐⭐⭐ **新增！背景复核项**

**问题**: 代码中可能出现分析师本地环境路径，但路径本身通常不是审核重点

**26YTY013F项目发现**:
```r
# scripts/r.07_ML.R:200
source('E:/yiqishiyanwan/wangbo/R_code/msvmRFE.R')   # ❌ 外部绝对路径
```

**检查清单**:
| 检查项 | 方法 | 严重性 |
|-------|------|--------|
| Windows绝对路径 | 搜索 `C:/`, `D:/`, `E:/` | 🟡 记录 |
| Linux绝对路径 | 搜索 `/home/`, `/media/` | 🟡 记录 |
| source()引用 | 检查是否因此引用错项目/错模块/项目外关键依赖 | 视影响而定 |
| 数据读取路径 | read.csv等的路径参数 | 视是否影响结果来源判断而定 |

**严重性分级**:
- 🟢 **默认不判问题**: 仅出现 `setwd()`、盘符路径、相对路径（如 `../04-功能富集分析`），但未显示跨项目取错数据，且不影响本次审核对结果文件的 AI核对
- 🟠 **MAJOR/CRITICAL**: 路径暴露错误项目编号、错误数据来源、错误模块来源，或导致“方法-结果文件”对应关系无法判断
- 🔴 **FATAL**: 明确证实代码读取/输出的是其他项目材料，并已动摇当前项目核心结论可信度

**审核口径补充**:
- 审核环境与分析师本地运行环境通常不同，因此 `setwd()`、`E:/04-iyun`、`../04-功能富集分析` 这类路径写法本身不作为主要扣分点。
- 只有当路径信息进一步证明“拿错项目、拿错模块、拿错结果、无法判断结果来源”时，才升级为实质问题。

---

### 5.3 路径大小写一致性检查 ⭐ **新增！**

**问题**: 路径大小写不一致在Linux系统上会报错

**26YTY013F项目发现**:
```r
save.path <- "Results/04_WGCNA/"   # ❌ 大写R
save.path <- "results/00_rawdata/"  # ✅ 小写r
```

**检查清单**:
- [ ] results/ vs Results/ vs RESULTS/
- [ ] CODE/ vs code/ vs Code/
- [ ] data/ vs Data/
- [ ] 统一使用小写命名（推荐）

---

**最后更新**: 2026-07-30
**版本**: v7.1
**维护者**: GitHub Copilot
