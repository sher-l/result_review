# v6 变更日志

> 记录 v5.0 → v6.x 的所有架构变更。

---

## v6.5 变更（2026-04-17）

### 新增：三路收敛 Prompt 自动构造

- `scripts/launch_convergence_audit.py`：基于预检查结果自动构造 3 个 Sub-Agent 的完整 prompt（~86KB/个）
  - 内嵌框架核心规则、预检查结果摘要、报告文本概览、Agent 差异化强化维度、结构化 JSON 输出格式
  - 解决核心问题：子代理不读文档就开始审核
  - 必要文件校验：缺少 report_text.txt / report_structure.json / project_structure.json 时拒绝启动

### 新增：收敛比对脚本

- `scripts/convergence_compare.py`：比对 3 份 Sub-Agent 审核结果 JSON
  - 基于位置+维度+规则+描述关键词的加权相似度匹配
  - 分类：共识（3/3）、多数（2/3）、单方（1/3）、分歧（矛盾）
  - 收敛指标：共识率 ≥ 95% 且分歧率 < 5% 为收敛
  - JSON schema 校验：自动修正字符串数值、裁剪越界分数、报告格式异常

### 改进：执行路径约束强化

- **文件校验**：launch_convergence_audit.py 启动前验证必要文件存在性
- **格式约束**：_OUTPUT_FORMAT 增加严格类型要求（数值字段必须是数字、severity/verdict 枚举约束）
- **Round 0 联动**：Sub-Agent prompt 增加"与预检查结果的关系"指引，防止简单复制
- **相似度算法改进**：章节号精确匹配替代子串包含，减少误匹配
- **Null safety**：normalize_location() 处理 None / 非字符串输入

### 改进：MC-001~MC-014 优化（v6.4.1 → v6.5）

- MC-001：系统命名检测（fig_prefix→section 一对一映射）
- MC-004：中文关键词直接子串匹配（甲基化、代谢物、PCA、SHAP 等）
- MC-006：三层过滤（参考文献排除 + KEGG/GO 上下文 + 章节标题排除）+ E-MTAB/PRJNA/SRP 数据集支持
- MC-008：报告文本交叉核对（代码有 + 报告无 → MAJOR）
- MC-014 新增：交付完整性检测（零代码 + N 模块 → CRITICAL）

### 改进：Layer 2 visual_audit.py

- 32+ 种图片类型（含 IHC、CNV/突变、细胞通讯、轨迹分析）
- 封面/装饰图自动跳过
- 100% 映射率（图片 → 报告章节）

### 基础设施

- `requirements.txt`：补齐 python-docx, lxml, pandas, pytest
- `AI_INDEX.md`：注册 Layer 2 + 三路收敛工具

### 变更文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | scripts/launch_convergence_audit.py | 三路收敛 Prompt 自动构造器 |
| 新增 | scripts/convergence_compare.py | 收敛比对脚本 |
| 新增 | scripts/visual_audit.py | Layer 2 视觉审核准备 |
| 修改 | scripts/mechanical_checks.py | MC-001/004/006/008 优化 + MC-014 新增 |
| 修改 | scripts/auto_audit_pipeline.py | 集成 Layer 2 visual_audit |
| 修改 | requirements.txt | 补齐依赖 |
| 修改 | AI_INDEX.md | 注册新脚本 |
| 修改 | 所有文档 | 版本号 v6.4 → v6.5 |

---

## v6.4 变更（2026-04-07）

### 新增：Layer 2 全量视觉审核

**动机**：Sub-Agent 是纯文本模型，无法查看图片内容。之前框架仅检查图片文件存在与大小，图片内容错误（阈值线位置、基因标注、copy-paste 残留的他项目标题）完全无法被发现。

**核心变更**：将视觉审核**前置**到 Sub-Agent 之前（Round 1），使 Sub-Agent 在审核时拥有真实的图片描述（`figure_audit.md`），从根源减少图片相关假阳性。

| 层 | 名称 | 执行者 | 输入 | 输出 |
|----|------|--------|------|------|
| Layer 0 | 代码化预解析 | Python 脚本 | docx + 项目目录 | 4 个 JSON + report_text.txt |
| Layer 1 | 自动预检查 | 21 个检查器 | 项目目录 + Layer 0 JSON | 风险分层报告 |
| **Layer 2** | **全量视觉审核** | **Lead Auditor** | **images/ + report_text.txt** | **figure_audit.md** |
| Layer 3 | AI 深度审核 | 3 个 Sub-Agent | Layer 0-2 产物 | 最终审核报告 |
| Layer 4 | 最终复核 | Lead Auditor | Layer 2+3 产物 + report_text.txt | 修正后的最终报告 |

**Layer 2 核心规则**：
- **全量强制**：项目中每张 Figure/Table 图片都必须查看，不允许抽样
- 每张图必查：可渲染、标题匹配、轴标签/图例、阈值线、标注数值、基因/细胞名称
- 9 大图件类型专项检查（Volcano/Heatmap/UMAP/Forest/ROC/KM/CellChat/Nomogram/箱线图）
- 产物 `figure_audit.md` 作为 Layer 3 Sub-Agent 的必要输入

### 变更：Layer 编号重映射

| 旧编号 (v6.3) | 新编号 (v6.4) | 说明 |
|--------------|--------------|------|
| Layer 0 | Layer 0 | 不变 |
| Layer 1 | Layer 1 | 不变 |
| — | Layer 2 | **新增**：全量视觉审核 |
| Layer 2 (Sub-Agent) | Layer 3 | 重编号，输入增加 figure_audit.md |
| Layer 3 (源文本复核) | Layer 4 | 重编号，扩展为源文本+视觉最终复核 |

### 变更：Round 执行流程

```
Round 0  → Layer 0 + Layer 1
Round 1  → Layer 2 (全量视觉审核) → figure_audit.md        [v6.4 新增]
Round 2  → Layer 3 Sub-Agent (输入含 figure_audit.md)
Round 3  → 交叉比对 + 迭代收敛
Round 4  → Lead Auditor 汇总报告初稿
Round 5  → Layer 4 源文本+视觉最终复核 → 最终 HTML
```

### 变更：强制输出文件新增 figure_audit.md

审核必须产出 6 个文件（原 5 个 + figure_audit.md）。

### 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | WORKFLOW.md | +Layer 2 章节 + Layer 重编号 + Round 重编号 + 版本号 v6.4 |
| 修改 | CORE_RULES.md | +§7.5 Layer 2 + §7.6 Layer 4 + figure_audit.md 输出 + 版本号 v6.4 |
| 修改 | CONVERGENCE_REVIEW_PROTOCOL.md | +figure_audit.md 输入 + 流程图更新 + Layer 重编号 + 版本号 v6.4 |
| 修改 | v6_CHANGELOG.md | +v6.4 章节 |

---

## v6.3 变更（2026-04-07）

### 新增：Layer 3 源文本复核验证

**动机**：26YHB087F 审核中，Sub-Agent C 产生了 2 个假阳性 CRITICAL（DEG 阈值和 CytoHubba 算法数），均在 Lead Auditor 直接阅读报告原文后被推翻。交叉收敛（Layer 2）无法消除此类 AI 幻觉。

| 层 | 名称 | 执行者 | 输入 | 输出 |
|----|------|--------|------|------|
| Layer 0 | 代码化预解析 | Python 脚本 | docx + 项目目录 | 4 个 JSON + report_text.txt |
| Layer 1 | 自动预检查 | 19 个检查器 | 项目目录 + Layer 0 JSON | 风险分层报告 |
| Layer 2 | AI 深度审核 | 3 个 Sub-Agent | Layer 0 产物 + Layer 1 报告 | 最终审核报告 |
| **Layer 3** | **源文本复核** | **Lead Auditor** | **Layer 2 产物 + report_text.txt** | **修正后的最终报告** |

**Layer 3 核心规则**：
- 所有 CRITICAL 级 Sub-Agent 发现必须由 Lead Auditor 直接回溯原文验证
- 高风险类型（参数不一致、参考文献、统计方向、Figure 编号、数字求和）强制回溯
- Layer 3 不发现新问题，只验证/排除 Layer 2 的发现
- 最终报告必须包含"复核阶段自纠正"表

### 新增：Round 4 执行阶段

执行摘要从 4 步升级为 5 步：
```
Round 0 → Round 1+2 → Round 3 → Round 4 (Layer 3 复核) → 最终 HTML
```

### 新增：审核报告 HTML 标准

基于 26YHB087F 经验，HTML 报告必须包含：
- 原文引用（带行号和 `<mark>` 高亮）
- 复核自纠正表格
- SOP 风格布局（参考标准化分析流程SOP.html）

### 新增：经验教训文件

`lessons/LESSONS_LEARNED_26YHB087F.md` — 记录 Sub-Agent 假阳性模式、Layer 0 误判模式、流程改进。

### 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | WORKFLOW.md | +Layer 3 章节 + Round 4 + 版本号 v6.3 |
| 修改 | CORE_RULES.md | +§7.5 Layer 3 规则 + 版本号 v6.3 |
| 修改 | CONVERGENCE_REVIEW_PROTOCOL.md | +阶段四 + 流程图 + 版本号 v6.3 |
| 修改 | v6_CHANGELOG.md | +v6.3 章节 |
| 新增 | lessons/LESSONS_LEARNED_26YHB087F.md | 26YHB087F 审核经验教训 |

### 触发案例

| 假阳性 | Sub-Agent | 原文实际 | 层 |
|--------|-----------|---------|-----|
| DEG 阈值 \|log2FC\|>1 vs 0.5 | Agent C | 报告写 >0.5，与代码一致 | Layer 3 发现 |
| CytoHubba 5 种 vs 4 种 | Agent C | 报告写"四种"，与代码一致 | Layer 3 发现 |

---

## v6.0 变更（2026-04-02）

## 架构级变更

### 新增：三层执行引擎

v6.0 引入"三层执行引擎"，将审核流程从原来的"自动检查+AI审核"升级为结构化的三层管线：

| 层 | 名称 | 执行者 | 输入 | 输出 |
|----|------|--------|------|------|
| Layer 0 | 代码化预解析 | Python 脚本 | docx + 项目目录 | 4 个 JSON + report_text.txt |
| Layer 1 | 自动预检查 | 19 个检查器 | 项目目录 + Layer 0 JSON | 风险分层报告 |
| Layer 2 | AI 深度审核 | 3 个 Sub-Agent | Layer 0 产物 + Layer 1 报告 | 最终审核报告 |

### 新增：Layer 0 预解析管线

| 组件 | 用途 |
|------|------|
| `scripts/parse_report_structure.py` | 报告文本 → report_structure.json（章节树、图表引用、基因清单、数字上下文、中文异常） |
| `scripts/parse_project_structure.py` | 项目目录 → project_structure.json（模块、代码、包名、参数索引、GEO 引用） |
| `scripts/mechanical_checks.py` | 12 项确定性机械检查 (MC-001~MC-012) → mechanical_check_result.json |

### 新增：12 项机械检查（MC-001~MC-012）

| 编号 | 检查项 | 严重度范围 |
|------|--------|-----------|
| MC-001 | 图编号-章节不匹配 | MAJOR |
| MC-002 | 中文缺字异常 | CRITICAL/WARNING |
| MC-003 | 章节编号跳号 | WARNING |
| MC-004 | 报告模块 vs 交付目录 | MAJOR |
| MC-005 | 流程图 vs 交付物 | MAJOR |
| MC-006 | 复制粘贴残留（报告级） | CRITICAL/INFO |
| MC-007 | 数字求和验证 | MAJOR |
| MC-008 | 代码级复制粘贴检测 | CRITICAL/INFO |
| MC-009 | 报告参数 vs 代码参数 | MAJOR |
| MC-010 | 方法-包名一致性 | MAJOR |
| MC-011 | 硬编码绝对路径 | WARNING |
| MC-012 | 结果文件存在性验证 | WARNING |

### 新增：CORE_RULES.md

从 MASTER_PROMPT.md + WORKFLOW.md + WORKFLOW_MODULE_CHECKS.md 中压缩提炼的 AI 精简规则（~160 行），包含：
- 六维审核框架 (D1-D6)
- 20 条 AI 深度检查清单 (R01-R20)
- 10 大高频漏审模式
- Sub-Agent 差异化审核指南 (A/B/C)

### 变更：Sub-Agent 差异化强化

v5.0 的三路独立审核升级为差异化强化模式：
- Sub-Agent A: 强化 D1（覆盖完整性）+ D5（证据充分性）
- Sub-Agent B: 强化 D2（事实正确性）+ D3（三方一致性）
- Sub-Agent C: 强化 D6（方法-代码一致）+ 统计判断

每个 Agent 仍做完整审核，但在强化维度上要求更深入的检查。

### 变更：严重度分级统一

- SeverityLevel 从 4 级（FATAL/CRITICAL/WARNING/INFO）扩展为 5 级（+MAJOR）
- 统一 mechanical_checks.py 与 quality_gate.py 的分级系统

### 变更：MASTER_PROMPT.md v5.0 → v6.0

- 从 207 行压缩至 ~100 行
- 删除与 CORE_RULES.md 重复的"六大优先级"详细内容
- 新增 Layer 0 产物说明和文档路由表

### 变更：Layer 0 → Layer 1 桥接

- `BaseProjectChecker` 新增 `layer0_data` 参数
- `CheckOrchestrator` 新增 `review_dir` 参数，自动加载 Layer 0 JSON
- 检查器可通过 `self.report_structure` / `self.project_structure` 访问预解析数据

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | scripts/parse_report_structure.py | Layer 0 报告预解析 |
| 新增 | scripts/parse_project_structure.py | Layer 0 项目目录解析 |
| 新增 | scripts/mechanical_checks.py | 12 项机械检查 |
| 新增 | CORE_RULES.md | AI 精简核心规则 |
| 新增 | v6_CHANGELOG.md | 本文件 |
| 新增 | KNOWN_LIMITATIONS.md | 已知限制文档 |
| 修改 | MASTER_PROMPT.md | v5.0 → v6.0 精简重构 |
| 修改 | CONVERGENCE_REVIEW_PROTOCOL.md | Sub-Agent 差异化 + 终止条件消歧 |
| 修改 | scripts/auto_audit_pipeline.py | 集成 Layer 0（Step 0.5） |
| 修改 | script_utils/quality_gate.py | SeverityLevel +MAJOR |
| 修改 | script_utils/base_project_checker.py | +layer0_data 属性 |
| 修改 | script_utils/check_orchestrator.py | +review_dir + Layer 0 加载 |
| 归档 | script_utils/ 7 个孤儿文件 | → archive/orphan_v6/ |
| 备份 | MASTER_PROMPT.md v5.0 | → archive/MASTER_PROMPT_v5.0_backup.md |

## 向后兼容性

- Layer 0 JSON 为可选输入，不影响 Layer 1 已有检查器（`layer0_data` 默认为 `None`）
- 旧版调用 `CheckOrchestrator(project_path, project_type)` 仍然有效
- 旧版检查器不引用 `self.report_structure` 则不受影响

---

## v6.2 变更日志（2026-04-03）

> 8 项检查器增强 + 架构改进。核心目标：降低 SKIP 率、增强检查覆盖面、统一输出格式。

### 改进 1：`find_report_text()` 递归 docx 搜索

- **文件**: `script_utils/utils.py`
- **问题**: 原逻辑只搜索 `project_path/*.docx`（根目录），而许多项目的 docx 在 `result/` 子目录中
- **修复**: Priority 3 搜索现扩展到 `result/`、`Result/`、`结果文件/`、`结果/` 子目录，按文件大小降序选择，过滤包含 "审核" 的文件
- **效果**: 25YYH171F 的报告文本加载从失败变为成功

### 改进 2：5 个 Checker 降级模式

当无报告文本可用时，以下 5 个 checker 不再直接 SKIP，而是进入降级模式输出部分有用信息：

| Checker | 降级模式行为 | 文件 |
|---------|-------------|------|
| ThresholdConsistencyChecker | 跨脚本阈值一致性比对 | `check_threshold_consistency.py` |
| NumberCrossrefChecker | CSV 行数汇总 | `check_number_crossref.py` |
| ReportCoverageChecker | 已识别模块列表 | `check_report_coverage.py` |
| ScRNAQCChecker | R 脚本 QC 参数扫描 | `check_scrna_qc.py` |
| ReportDataMatchChecker | 可匹配数据文件列表 | `check_report_data_match.py` |

- 降级模式输出 `degraded: True` 标记（非 `skipped: True`）
- **效果**: 25YYH171F SKIP 从 6 降到 1

### 改进 3：ML Visual-Only 检测

- **文件**: `script_utils/check_ml_anomaly.py`
- **新增方法**: `_check_ml_visuals_without_metrics()`
- **行为**: 检测含 ROC/Boxplot 图片但无 metrics CSV 的 ML 目录，输出 WARNING

### 改进 4：跨 Checker 融合信号检测

- **文件**: `script_utils/check_orchestrator.py`
- **新增方法**: `_detect_convergence_signals()`, `_extract_targets_from_issue()`
- **行为**: 所有 P0+P1 checker 完成后，扫描 issues 中的模块名/文件名引用：
  - 同一目标被 ≥2 个独立 checker 标记 → `MEDIUM` 置信度
  - 被 ≥3 个 checker 标记 → `HIGH` 置信度
- **输出**: `convergence_signals` 列表写入 summary

### 改进 5：中文术语校对 Checker（新建）

- **文件**: `script_utils/check_chinese_proofreading.py`（新建）
- **注册**: `check_orchestrator.py` P1_CHECKERS 列表
- **两类检查**:
  - 缺字检测: 25 条规则（如"疫细胞浸润"→"免疫细胞浸润"）
  - 同音错字: 12 条规则（如"局势细胞"→"巨噬细胞"）
- **排除机制**: 避免"箱线图"被误判为"列线图"缺字等常见误报
- **来源**: 26YHB147F 审核经验

### 改进 6：证据完整性模块扩展

- **文件**: `script_utils/check_evidence_completeness.py`
- **新增方法**: `_check_image_only_modules()`
- **检测**: SHAP、Correlation、ssGSEA、scQuantify 模块仅有图片而无 CSV 数据的情况

### 改进 7：Checker 输出标准化

- **文件**: `script_utils/check_orchestrator.py`
- **新增方法**: `_normalize_result()`
- **行为**: 每个 checker 返回值统一为 6 个必接字段：
  - `issues`: list（必须）
  - `warnings`: list（必须，默认 `[]`）
  - `total_checks`: int（必须，默认 `1`）
  - `failed_checks`: int（必须，默认 `len(issues)`）
  - `skipped`: bool（必须，默认 `False`）
  - `degraded`: bool（必须，默认 `False`）
- 原始输出保留在 `_raw` 字段
- 基因集质量检查（特殊路径）也已标准化
- **效果**: 20/20 checker 通过标准化验证

### 改进 8：MODULE_KEYWORDS 扩展

- **文件**: `script_utils/check_report_coverage.py`
- **扩展**: 从 19 类增至 29 类，新增：Combat、Target、Toxicity、Correlation、SHAP、Annotation、Quantify、Expression、MolecularDynamics、GSVA

### 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `script_utils/utils.py` | docx 搜索增加子目录 |
| 修改 | `script_utils/check_threshold_consistency.py` | +降级模式 |
| 修改 | `script_utils/check_number_crossref.py` | +降级模式 |
| 修改 | `script_utils/check_report_coverage.py` | +降级模式 + MODULE_KEYWORDS 扩展 |
| 修改 | `script_utils/check_scrna_qc.py` | +降级模式 |
| 修改 | `script_utils/check_report_data_match.py` | +降级模式 |
| 修改 | `script_utils/check_ml_anomaly.py` | +visual-only 检测 |
| 修改 | `script_utils/check_evidence_completeness.py` | +image-only 模块检测 |
| 修改 | `script_utils/check_orchestrator.py` | +标准化 + 融合检测 + 注册新 checker |
| 新增 | `script_utils/check_chinese_proofreading.py` | 中文术语校对 P1 checker |

### 验证结果

- **25YYH171F**: SKIP 6→1, 20/20 标准化 OK, 融合信号 0（正常：issues 分散）
- **26YHB147F**: 20/20 标准化 OK, 融合信号 0（正常：issues 分别指向不同模块）

### 向后兼容性

- 标准化为后处理，不修改任何 checker 内部逻辑
- 降级模式保留原有 SKIP 路径作为兜底
- 融合检测为附加输出，不影响现有 severity 分级
- 中文校对 checker 标记 `silent_if_empty: True`，无报告文本时自动跳过

---

## v6.3 变更日志（2026-04-03）

> 框架审视修复：generate_report() 全面重写 + 测试覆盖补全。共修复 8 项问题。

### P0: generate_report() 重写（#1 #2 #3）

**问题**：原 `generate_report()` 硬编码 4 个 checker 名称做特殊渲染，其余 16 个 P1 checker 的 issues/warnings 完全不展示；融合信号不在 markdown 报告中；degraded/skipped 状态不可见。

**修复**：
- **#1 融合信号章节**：当 `convergence_signals` 非空时，报告末尾自动渲染 `## 🔗 跨检查器融合信号` 表格（目标、类型、关联检查器数、置信度）
- **#2 通用渲染**：移除 4 个硬编码 checker 分支，改用标准化字段（`issues`/`warnings`/`total_checks`/`failed_checks`）通用渲染所有 checker。issues 最多展示 10 条，warnings 最多 5 条，超出部分显示计数。兼容旧格式 `errors`/`mismatches`/`species_mismatches` 键
- **#3 degraded/skipped 标记**：每个 checker 结果块增加 `⚡ 降级运行（无报告文本）` 和 `⊘ SKIP` 可视标记

**影响文件**：`check_orchestrator.py` generate_report() 方法

### P1: 测试覆盖补全（#4 #5 #6）

- **#4 新增 `test_check_chinese_proofreading.py`**：23 个测试用例覆盖缺字检测、同音错字、排除上下文（箱线图/折线图/乳腺癌等）、降级模式、返回结构
- **#5 GeneSetQualityChecker 记录**：在 `KNOWN_LIMITATIONS.md` 记录其不继承 BaseProjectChecker 的架构一致性说明
- **#6 orchestrator 测试扩展**：新增 `TestNormalizeResult`（6 用例）、`TestConvergenceSignals`（5 用例）、`TestGenerateReport`（4 用例），P1 数量断言从 `>= 11` 更新为 `>= 15`

### P2: 文档与注释（#7 #8）

- **#7 QualityGateBuilder 注释**：`add_from_check_result()` 添加 v6.2 标准化兼容性说明文档
- **#8 convergence 扫描范围**：`_detect_convergence_signals()` docstring 明确注明仅扫描 P0+P1，P2/P3 启用后需同步更新

### 修改文件清单

| 文件 | 变更 |
|------|------|
| `script_utils/check_orchestrator.py` | generate_report() 重写 + convergence docstring |
| `script_utils/quality_gate.py` | QualityGateBuilder 注释更新 |
| `tests/test_check_chinese_proofreading.py` | 新增 23 测试用例 |
| `tests/test_check_orchestrator.py` | 新增 15 测试用例 + P1 断言更新 |
| `KNOWN_LIMITATIONS.md` | GeneSetQualityChecker 架构说明 |
| `v6_CHANGELOG.md` | 本条目 |

### 验证结果

- **单元测试**: 46/46 passed（orchestrator 23 + chinese_proofreading 23）
- **端到端**: 25YYH171F — 降级标记 ✅、检查项统计 ✅、问题详情渲染 ✅
- **语法**: 4 个修改文件全部 py_compile 通过
