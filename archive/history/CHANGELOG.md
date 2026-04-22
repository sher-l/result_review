# 框架更新日志

> 记录框架的所有改进和修复

---

## 版本历史总览

| 版本 | 日期 | 核心改进 | 关键新增 | 基于项目 |
|-----|------|---------|---------|----------|
| **v6.2** | 2026-04-04 | 路径健壮性 + 报告缓存 + 检查器假阳性优化 + HTML模板全面重新设计 | Path.resolve()、报告文本单次加载、数字交叉验证5级匹配、中文校对精修、证据完整性分级优化、5级严重性独立展示、Verdict横幅、打印样式 | 25YYH171F 实审 |
| **v6.1** | 2026-04-02/03 | 结构健壮性 + 假阳性优化 | 虚继承消除、返回值统一、并发锁、缓存保护、gene_naming假阳性-99%、并行输出排序 | 3轮怀疑性审查 |
| **v4.7** | 2026-03-31 | 深度审查：4 CRITICAL + 6 HIGH 修复 | PDF页数算法重写、多行基因提取、词边界防误匹配、P0不可用检测、中文细胞类型映射、参考文献范围解析、HTML安全过滤 | 5-subagent深度审查 |
| **v4.6.1** | 2026-03-31 | 误判优化 | 证据完整性单细胞上下文感知 + 可视化模块白名单 | 26YTY025F |
| **v4.6** | 2026-03-31 | 深度证据交叉验证自动化 | report_data_match、ml_anomaly、code_existence、figure_data_match 4个新检查器 + scrna_qc下游覆盖增强 | 26YYS019F |
| **v4.5** | 2026-03-30 | Agent视觉核查 + 检查器扩展 | figure_integrity、gene_set_quality、scrna_qc、report_coverage、visualization_thresholds、gene_naming 6个检查器 + 视觉截图核查 | 25YYF085F / 26YYS083F |
| **v4.4** | 2026-03-11 | 覆盖完整性 + 事实核对 + 入口收敛 | 覆盖矩阵、事实核对清单、标题/TopN检查、阴性结果完整性 | 25SYH053F / 26YHB205F / 26YYH033F |
| **v4.1** | 2026-02-25 | 样本范围描述精确性检查 | "所有样本"描述歧义检测、多数据集样本范围验证 | 26YYH033F |
| **v3.2** | 2026-02-13 | 细胞类型/基因名称检查 + 三方交集验证 | 细胞类型命名一致性、基因名称大小写检查、三方交集逻辑验证、参考基因集使用验证、代码路径一致性 | 25YLC105F |
| **v3.1** | 2026-02-11 | 强制Agent Team + 经验总结机制 | 强制使用Agent Team、Figure标题检查、经验总结 | 26YHB161F |
| **v3.0** | 2026-02-10 | Agent Team专业分组审核 | 按代码/内容分组，三轮检查机制 | 26YZF001F |
| **v2.3** | 2026-02-04 | 物种验证前置 + 系统性文本检查 | Step 0物种验证、系统性grep搜索 | 25YYS110F |
| **v2.2** | 2026-02-03 | 专业逻辑和判断标准检查 | STATISTICS_REFERENCE.md | 用户反馈 |
| **v2.0** | 2026-02-03 | 统一工作流程 | WORKFLOW.md标准化 | - |

---

## [v6.2] - 2026-04-04

### 🛤️ 路径健壮性（CWD 无关化）

- `check_orchestrator.py`、`base_project_checker.py`、`project_metadata.py`、`utils.py`：全部 `Path(project_path)` → `Path(project_path).resolve()`
- 消除工作目录依赖，25YYH171F 首次运行 6 SKIP 全部修复为 0 SKIP

### ⚡ 报告文本缓存

- `check_orchestrator.py`：新增 `_load_report_text()` + `_report_text` 缓存
- 在 `_run_checker()` 中注入 `checker._cached_report_text`，8 个需要报告文本的 checker 共享一次 docx 解析
- `base_project_checker.py`：`load_report_text()` 优先使用 `_cached_report_text`

### 🔎 数字交叉验证优化（check_number_crossref.py）

**正则跨度限制**：GO/KEGG/DEG 模式的 `.*?` 改为 `{0,20}` 或 `{0,40}`，防止跨章节错提数字（如 GO 的 250 被 KEGG 正则捕获）。ML/基因模式保留原宽松跨度（需长跨度捕获结果数字）。

**5级交叉比对逻辑**：
1. 总行数 ±1 → OK
2. 显著行数(p<0.05) ±1 → OK
3. 报告数字全部 < 总行数 → WARNING（子集/子分类）
4. 最接近数字在 ±max(5, 10%)内 → WARNING（近似不一致）
5. 以上均不满足 → CRITICAL

**新增**：`_count_significant_rows()` 方法，自动检测 p 值列候选名（`p.adjust`、`padj`、`FDR` 等 9 种），统计 p<0.05 行数。

**效果**：
- 25YYH171F: 3 CRITICAL → 0 CRITICAL + 3 WARNING
- 147F: 1 CRITICAL → 1 WARNING

### 📝 中文术语校对精修（check_chinese_proofreading.py）

- 移除错误规则 `('血细胞', '血小板')` — 血细胞(blood cells)≠血小板(platelets)
- 排除上下文添加 `点线图`（点线图是合法图表类型，不是"列线图"缺字）
- **效果**：147F 从 3 假阳性 → 0 issue

### 📂 结果根目录扫描增强（utils.py）

- `find_result_root()` 新增扫描 `result/`、`Result/`、`结果/` 子目录中的编号模块
- 修复 25YYH171F 等项目数字交叉验证 SKIP 问题

### 🧪 证据完整性分级优化（check_evidence_completeness.py）

**scExpression 排除**：模块目录名同时含 `sc` 和 `expression` 时跳过检查（单细胞可视化模块无 AUC 表是正常的）。

**分子对接证据识别**：新增 PDB/MOL2 复合物文件检测（`complex`/`out`/`pose`/`docked` 关键词），存在对接产物时严重度从 CRITICAL 降为 WARNING 并正确归入 `self.warnings`（不再导致整体 FAIL）。

**参考文献缺失降级**：数据库被提及但无引用编号的严重度从 CRITICAL → MAJOR。缺少参考文献编号是报告质量问题而非数据正确性错误。编号越界和编号错配仍保持 CRITICAL。

**效果**：
- 25YYH171F: evidence 3 CRITICAL → 1 CRITICAL(MD无原始数据) + 1 WARNING(对接)
- 147F: evidence 3 CRITICAL → 3 MAJOR(参考文献) + 1 WARNING(对接)

### 回归测试

- 263 项测试全部通过 + 1 项跳过
- 25YYH171F: SKIP=0, FATAL=1(setwd编号), CRITICAL=1(MD无原始数据), MAJOR=0, WARNING=6(数字交叉3+对接+SHAP+Correlation+scQuantify)
- 147F: 数字交叉 1 CRITICAL→1 WARNING, 中文校对 3→0, 证据 3 CRITICAL→3 MAJOR+1 WARNING

### 🎨 HTML 审核报告模板全面重新设计

**`render_final_review_html.py`**：
- 新增 `determine_verdict()` 函数：FATAL→不建议提交、CRITICAL→有条件通过、无高优先级→建议通过
- 新增模板变量：`MAJOR_COUNT`、`WARNING_COUNT`（独立拆分）、`VERDICT_CLASS`、`VERDICT_TEXT`

**`final_review_report_template.html`** 全面重写：
- **修复 FATAL 卡片颜色 bug**：旧版 FATAL 使用了 `.info` 蓝色类 → 现为独立深红 #dc2626
- **5 级严重性独立展示**：Hero 区域 + 正文均使用 🔴FATAL / 🟠CRITICAL / 🟤MAJOR / 🟡WARNING / 🔵INFO 独立卡片
- **审核结论 Verdict 横幅**：🚫不建议提交（红）/ ⚠️有条件通过（橙）/ ✅建议通过（绿）
- **严重性块样式修复**：旧版 FATAL 和 INFO 共享灰色 → 每级独立颜色和渐变
- **版本标识更新**：v4.4 → v6.2
- **渲染说明精简**：移除过时的临床统计检查描述
- **新增功能**：回到顶部按钮、打印样式（@media print）、smooth scrolling
- **视觉风格现代化**：暖黄纸质风格 → 现代 Slate 灰蓝色调
- 20 个项目 HTML 已批量重新生成

---

## [v6.1] - 2026-04-02/03

### 🏗️ 结构健壮性修复（3轮怀疑性审查）

基于 3 轮 Explore 子代理怀疑性审查，修复 8 项结构性问题 + 1 项假阳性优化 + 1 项输出排序修复。

#### P0: 虚继承消除（6 个检查器）

- `check_data_flow.py`、`check_figure_integrity.py`、`check_ml_anomaly.py`、`check_model_consistency.py`、`check_species_match.py`、`check_gene_naming.py`：消除重复定义基类已有的方法
- 确保所有 18 个注册检查器统一使用 `BaseProjectChecker` 的 `find_modules()`、`find_code_directory()`、`load_report_text()` 等基类方法

#### P1a: 返回值统一

- `check_project_id_consistency.py`（errors→issues）、`check_term_consistency.py`（mismatches→issues）、`check_visualization_thresholds.py`（mismatches→issues）、`check_species_match.py`（species_mismatches mapped to issues）
- Orchestrator registry 同步更新所有 `fail_key`/`count_key` 为 `'issues'`

#### P1b: 边界条件测试

- 新增 `tests/test_boundary_conditions.py`：33 项测试
- 覆盖空项目、编码兼容（GBK/BOM）、大项目、Layer 0 路径、返回值统一

#### 第2轮修复

1. **`count_value` 防御性修复**（`check_orchestrator.py`）
   - `result.get(...) or fail_value` → `if count_value is None: count_value = fail_value`
   - 防止空列表被 `or` 判定为 falsy 而使用 fail_value

2. **`ProjectMetadata.find_numbered_modules()` 缺失方法**（`project_metadata.py`）
   - 新增 `find_numbered_modules()` 返回匹配 `r'\d{2}[_\-]'` 的编号模块目录
   - 修复 `gene_naming` 检查器因 AttributeError 静默失败的问题

#### 第3轮修复

3. **并发安全**（`check_orchestrator.py`）
   - 新增 `self._result_lock = threading.Lock()` + `_append_result()` 方法
   - 替换 6 处 `self.results[priority].append()` 为线程安全的 `_append_result()`

4. **缓存保护**（`project_metadata.py`）
   - `rglob()` 和 `glob()` 返回 `list()` 副本而非缓存直接引用
   - 防止调用方 `.append()`/`.extend()` 污染缓存

### 🎯 gene_naming 假阳性优化

- `check_gene_naming.py`：`has_symbols` 分支不再匹配空格字符
  - 含空格的多词短语（如 "Activated B cell"、"CD56bright natural killer cell"）直接跳过
  - 仅检测 `-` 和 `_` 符号
- 新增 `_detect_gene_column()` 自动检测基因列
  - 优先匹配 `GENE_COLUMN_CANDIDATES` 已知列名列表
  - 回退启发式：第一列 ≥50% 匹配 `^[A-Z][A-Za-z0-9][-A-Za-z0-9.]*$` 时使用
  - 无法识别时返回 `skipped` 而非盲取第一列
- **效果**：147F 项目 INFO 从 3787 → 49（降低 98.7%）

### 🖨️ 并行输出排序修复

- `check_orchestrator.py`：`_run_checker` 新增 `_print_buffer` 参数
  - 并行模式下每个 checker 输出到独立缓冲列表
  - 执行完毕后按注册顺序逐条打印
  - 修复之前 P1 并行执行时控制台输出交叉的可读性问题

#### 回归测试

- 225 项测试全部通过 + 1 项跳过
- 147F 管线：CRITICAL:7, INFO:49（gene_naming 优化后新基线）
- 233F 管线：CRITICAL:6, INFO:241（gene_naming 优化后新基线）

---

## [v4.7] - 2026-03-31

### 🔬 深度审查修复（5-subagent 全框架审计）

基于 5 个子代理对全部 16 个检查器 + 流水线脚本的全面代码审查，修复 4 个 CRITICAL + 6 个 HIGH 问题。

#### CRITICAL 修复

1. **C1: 蛋白复合物 + lncRNA 正则统一**
   - `check_gene_naming.py` + `check_gene_set_quality.py`：蛋白复合物正则统一为双向匹配 `r'.*-.*_.*|.*_.*-.*'`
   - lncRNA 正则统一为 `r'^(LINC\d|MIR\d|RP11-)'`，需数字/连字符后缀避免误匹配（LINCARE、ACTB）

2. **C2: PDF 页数算法重写**
   - `check_figure_integrity.py`：从 max(/Count) 改为在 `/Type /Pages` 所在 PDF 对象内（obj…endobj 边界）搜索 /Count
   - 避免字体表 /Count 256、颜色空间 /Count 等干扰导致页数膨胀
   - 回退策略：逐页计数 `/Type /Page(?!s)`

3. **C3: 多行基因提取**
   - `check_data_flow.py`：`_extract_monocle_genes` 重写，使用 `re.DOTALL` 支持跨行 `c()` 向量
   - 搜索 `features|gene_list|hub_genes|target_genes|genes|selected_genes` 变量名
   - 从引号字符串中提取基因名

4. **C4: 术语一致性词边界**
   - `check_term_consistency.py`：错误术语模式添加 `\b` 词边界
   - 防止 "Normal" 匹配 "normalized"，"Tumor" 匹配 "Tumor_suppressor" 等误判

#### HIGH 修复

5. **H1: P0 检查器不可用检测**
   - `check_orchestrator.py`：P0 循环后增加 `p0_unavailable` 追踪
   - 任何 `cls is None` 的 P0 检查器触发 FATAL 级别错误消息

6. **H2: 去重有图无CSV检查**
   - `check_code_existence.py`：从 `check_all()` 移除 `_check_image_only_modules` 调用
   - 该功能现由 `check_figure_data_match.py` 独占处理

7. **H3: 去重ML指标 + CSV行计数修复**
   - `check_report_data_match.py`：从 `check_all()` 移除 `_check_ml_metrics` 调用（由 `check_ml_anomaly.py` 独占）
   - `_count_csv_data_rows` 改用 `csv.reader(io.StringIO(text))` 替代 `split('\n')`，正确处理引号内换行

8. **H4: 中文细胞类型映射**
   - `check_scrna_qc.py`：新增 `_CN_TO_EN` 字典，21 组常见中文→英文细胞类型映射
   - 覆盖：巨噬细胞、NK细胞、T/B细胞、成纤维/内皮/上皮细胞、单核、树突状、浆细胞等

9. **H5: 参考文献范围解析**
   - `check_evidence_completeness.py`：引用正则扩展为 `\[(?P<ref>[\d,\-\s]+)\]`
   - 新增 `_expand_ref_range` 静态方法：`[1-5]` → `[1,2,3,4,5]`，`[1,3,5]` → `[1,3,5]`

10. **H6: HTML 链接安全过滤**
    - `render_final_review_html.py`：`apply_inline_formatting` 新增 `_safe_link` 内部函数
    - 过滤 `javascript:`, `data:`, `vbscript:` 协议链接，仅保留文本

#### 回归测试

- `tests/test_v47_regression.py`：32 项测试全部通过
- 覆盖所有 10 项修复的核心行为验证

---

## [v4.6.1] - 2026-03-31

### 🔧 误判优化

**基于项目**：26YTY025F（CA13+低级别胶质瘤单细胞）

#### 证据完整性单细胞上下文感知

- `check_evidence_completeness.py`：新增 `_SC_STAT_TOKENS` 元组（chisq/chi_sq/chiseq/fisher/kruskal）
- 单细胞项目的表达模块含卡方/Fisher检验 CSV 时，不再误报“缺 AUC/差异统计表”
- 修复场景：26YTY025F 的 03_expression 被误标为 CRITICAL

#### 可视化模块白名单

- `check_code_existence.py`：新增 `_VIS_ONLY_KEYWORDS` 白名单（qc/umap/pca/tsne/subtypes/dimplot）
- QC、UMAP 等纯可视化模块不再被标记“有图无CSV”
- 回归测试：26YYS019F 无新增误报，合成测试 4/4 通过

---

## [v4.6] - 2026-03-31

### 🎯 重大更新：深度证据交叉验证自动化

**问题背景**：
- 26YYS019F 审核中发现 Mantel 检验报告文字与 CSV 数据存在基因标签互换（SIRT1↔MAP1LC3A），此类错误在 v4.5 时需要人工逐行对比才能发现。

#### 新增 4 个 P1 检查器

1. **`check_report_data_match.py`** — CSV↔报告文字交叉验证
   - Mantel 检验基因标签互换检测（CRITICAL 级）
   - 基因集计数验证（DEG/交集/LASSO/关键基因）
   - GSEA 通路计数验证
   - Cibersort 差异细胞验证

2. **`check_ml_anomaly.py`** — ML 模型异常检测
   - AUC=1.0 过拟合风险
   - AUC-Accuracy 矛盾（高 AUC 低 Accuracy→类别不平衡）
   - 均匀 AUC 检测
   - 仅训练集验证检测

3. **`check_code_existence.py`** — 代码存在性 + 有图无CSV
   - 检测代码文件（.R/.py/.Rmd/.ipynb）存在性
   - 每模块图件与CSV数据比例分析

4. **`check_figure_data_match.py`** — 图件-数据匹配
   - LASSO 特征基因 CSV 缺失
   - 图件密集但数据文件缺失的模块

#### 增强 1 个现有检查器

- **`check_scrna_qc.py`** — 新增 `_check_downstream_coverage()` 方法
  - 检测 scTenifoldKnk 细胞类型覆盖缺口
  - 对比注释细胞类型总数与实际分析数

#### HTML 导出修复

- `render_final_review_html.py`、`ensure_review_html.py`、`auto_audit_pipeline.py` 现在同时支持 `final_review_report.md` 和 `REVIEW_REPORT.md` 两种审核报告文件名

#### 检查器规模

```
总计: 16 检查器 (4 P0 + 12 P1)
```

#### 验证

- 26YYS019F: 2 CRITICAL（Mantel 互换精确命中）+ 合理 warnings
- 25YYF085F: 回归通过，无误报
- 26YYS083F: 回归通过，无误报

---

## [v4.5] - 2026-03-30

### 🎯 Agent 视觉核查 + 检查器扩展

- Agent 可自主使用浏览器截图核查图件（open_browser_page + screenshot_page）
- 新增 6 个 P1 检查器：figure_integrity / gene_set_quality / scrna_qc / report_coverage / visualization_thresholds / gene_naming
- check_term_consistency 增强：CANCER_ABBREVIATIONS(40项) + CANCER_SYNONYMS 数据库
- WORKFLOW.md 拆分：核心流程 + 模块检查详册
- 基于项目：25YYF085F / 26YYS083F

---

## [v4.4] - 2026-03-11

### 🎯 重大更新（基于近期漏审问题汇总）

#### 核心改进：覆盖完整性检查 + 事实核对前置 ⭐⭐⭐

**问题背景**：
- 25SYH053F：原审核没有发现报告遗漏86%的MR暴露，说明“只核对部分数字”并不能保证报告完整。
- 26YHB205F：原审核漏掉 STRING URL、UniProt/PDB 功能映射、euchromatin 翻译、CC TOP4/TOP5 等事实错误。
- 26YYH033F：原审核暴露出“所有样本”这类措辞不精确，会扩大样本范围。

#### 新增功能

**1. 覆盖矩阵（P0/P1）**

新增强制产物 `coverage_matrix.md`，逐项列出：
- 数据集 / 队列
- 模块 / 子分析
- 暴露 / 分组 / 亚组
- Figure / Table
- 阴性结果 / 失败分析

**2. 事实核对清单（P0/P1）**

新增强制产物 `fact_check_list.md`，至少核对：
- 数据库名称与URL是否匹配
- 数据库功能描述是否匹配
- 英文术语翻译是否准确
- 样本范围用语是否准确
- TopN / Top5 / Top10 是否与实际条目数一致

**3. Figure/Table 标题专项检查（P1）**

要求核对：
- 疾病名称
- 数据集编号
- 细胞类型
- 分组名称

**4. 阴性结果与失败分析完整性（P1）**

新增要求：
- 失败分析不能省略
- 无显著结果不能选择性隐藏
- 核心模块覆盖率必须达到100%

#### 文档收敛

- `README.md`：改为明确主线入口
- `INDEX.md`：删除对不存在或过期文档的导航
- `WORKFLOW.md`：加入“报告覆盖与事实快检”
- `CHECKLIST_TEMPLATE_v4.0.md`：加入覆盖矩阵、事实核对、标题/TopN检查（当前主线文件名为 `CHECKLIST_TEMPLATE.md`）
- `AGENT_TEAM_PLAN_v4.0.md`：加入3份强制中间产物（当前主线文件名为 `agent_plans/AGENT_TEAM_PLAN.md`）

---

## [v4.1] - 2026-02-25

### 🎯 重大更新（基于项目26YYH033F审核发现）

#### 核心改进：样本范围描述精确性检查 ⭐⭐⭐

**问题背景**：
项目26YYH033F报告中出现"计算线粒体自噬相关基因在**所有样本**的评分"的描述，但实际只使用了训练集GSE43292的64个样本（共197个样本）。

**真实案例**：
| 数据集 | 用途 | 样本数 | 是否参与ssGSEA |
|--------|------|--------|---------------|
| GSE43292 | 训练集 | 64 | ✅ 是 |
| GSE100927 | 验证集1 | 104 | ❌ 否 |
| GSE28829 | 验证集2 | 29 | ❌ 否 |

**暴露问题**：
- 报告中"所有样本"表述产生歧义
- 容易让读者误解为使用了全部197个样本
- 实际只有64个训练集样本参与评分计算

#### 新增功能

**1. 样本范围描述精确性检查** ⭐⭐⭐ P1级新增

**检测方法**：
```python
# 搜索报告中可能产生歧义的表述
ambiguous_patterns = ['所有样本', '全部样本', '全部数据', 'all samples', 'all data']
for pattern in ambiguous_patterns:
    matches = grep_search(report_text, pattern)
    # 对照代码验证实际使用的样本范围
```

**检查清单**（新增到CHECKLIST_TEMPLATE.md）：
- [ ] 搜索报告中"所有样本"、"全部样本"等表述
- [ ] 对照代码确认实际使用的数据集
- [ ] 验证样本数量是否匹配

**常见问题模式**：
| 报告描述 | 实际情况 | 问题级别 |
|---------|---------|---------|
| "所有样本" | 只有训练集样本 | 🟡 中等 |
| "全部数据" | 部分数据集 | 🟡 中等 |
| "验证集" | 训练集+验证集 | 🔴 严重 |

**建议修改**：
> ❌ "计算线粒体自噬相关基因在所有样本的评分"
> ✅ "计算线粒体自噬相关基因在**训练集GSE43292的所有样本**的评分"

#### 审核统计（26YYH033F项目）

| 检查项 | 结果 |
|--------|------|
| 数字验证通过率 | 100% (15/15) |
| 参数一致性 | 100% (6/6) |
| 严重问题 | 0 |
| 中等问题 | 1（样本范围描述不精确） |
| 轻微问题 | 1（代码硬编码路径） |
| 总体评价 | 优秀 |

#### 文件更新

| 文件 | 更新内容 |
|------|---------|
| `CHECKLIST_TEMPLATE.md` | 新增"样本范围描述精确性检查"章节 |
| `lessons/LESSONS_LEARNED_26YYH033F.md` | 新建经验总结文件 |

---


---

## v3.2 及以下版本

> 历史版本 (v3.2 / v3.1 / v3.0 / v2.3 / v2.2 / v2.1 / v2.0) 的详细更新日志已省略。
> 核心改进摘要见上方版本历史总览表格。

---

**最后更新**: 2026-03-29
**当前版本**: v4.4
