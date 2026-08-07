# 生物信息学项目审核 - Agent Team方案

> 说明：本文件是 Team 执行展开方案。
> 当前正式审核主线、三路输入边界与最终收口命令，先以 `policy/audit_policy.json`、`README.md`、`MASTER_PROMPT.md` 为准。

> **当前主线版本**：v7.1
> **主文件命名规则**：文件名固定为 `AGENT_TEAM_PLAN.md`，版本号以正文声明为准。
> 完整变更记录见 [v6_CHANGELOG.md](../archive/history/v6_CHANGELOG.md)

---

## 🔴 强制要求：必须使用当前主线Agent Team方案

### ⭐⭐⭐ 核心原则
```markdown
❌ 禁止单人审核
❌ 禁止跳过Auto-Precheck阶段
❌ 禁止 Sub-Agent 之间共享中间结论（独立性原则）
✅ 必须使用“小切片 Sub-Agent → 三路汇总 → 交叉收敛”协议
✅ 必须先完成Auto-Precheck并带着问题清单进入逐项证据复核
✅ 必须先验收 `agent_results/slices/*.json`，再汇总为 3 路结果并收敛
✅ 用户只要说“开始审核/审核下一个/重审”，默认自动启动三路，不等待二次确认
```

## 2026-03-17补强原则（强制）

协作审核的最小单位不是“整章”或“整个模块”，而是“单个分析点”。

每个Agent在处理任一分析点时，必须至少回答以下 4 个问题：

1. 方法在报告中是否写清。
2. 结果描述在报告中是否出现。
3. 对应结果文件是否真实存在。
4. 证据是否足够支撑该结论。

如果一个分析点只有图片、PDF 或一句结果描述，但没有结构化结果表、原始数值文件或中间证据链，不得直接判定为“通过”，应标记为“证据不足”或“部分通过”。

如果项目未交付代码，Lead Auditor 必须在最终报告中单列“代码不可复现风险”，不得省略。

自动预检查是前置发现问题的工具，不替代逐项证据复核。若自动检查结果与明细不一致，或检查器本身报错，必须由对应Agent补做。Agent可通过浏览器工具直接查看图片/PDF进行视觉核查。

**架构优势**：
1. 自动化预检查发现FATAL问题，避免浪费逐项证据复核时间
2. 风险分层帮助逐项证据复核优先处理高风险问题
3. Lead 默认只做监工/整合/仲裁；正式审核证据由小切片 Sub-Agent 落盘，避免 leader 主线程触发 remote compact
4. 小切片 Sub-Agent 最大化覆盖面，同时降低 remote compact 和上下文丢失风险
5. 小切片不等于弱模型：正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high
6. 三路汇总 + Lead 全局一致性复核 + 交叉比对 + 迭代收敛消除遗漏与分歧，保证结论可靠
7. 每个切片只处理一个窄范围，完整结果必须落盘到 `agent_results/slices/`

**验证标准**：
- ✅ 运行auto_audit_pipeline.py并获取报告
- ✅ 自动检查已输出完整问题清单与风险分层
- ✅ 按 `agent_prompts/agent_slice_manifest.json` 分批启动小切片 Sub-Agent；如果 Sub-Agent 触发 remote compact/context loss，先继续拆分工作再重试，禁止原范围重跑
- ✅ Lead 只读取短摘要、证据路径和最终必要片段，不在主线程展开长报告/长日志/完整清单/大证据
- ✅ 正式判断型切片使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini/explore 只做定位、清单、schema、grep
- ✅ 验收每个切片已写入 `agent_results/slices/*.json`
- ✅ Lead 复核覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块
- ✅ 交叉比对达成一致或完成迭代收敛
- ✅ 最终报告包含收敛过程摘要与经验总结

---

## 📋 核心能力

| 能力 | 说明 |
|------|------|
| **小切片执行** | 多个窄范围 Sub-Agent 按 manifest 分批执行并落盘 |
| **三路汇总审核** | A/B/C 三路只汇总本路 slice JSON，形成收敛输入 |
| **交叉比对机制** | 共识/多数/单方/分歧四级分类 |
| **迭代收敛流程** | 问题并集 → 增强审查 → 再次比对，最多 3 轮 |

| **收敛日志** | 完整记录迭代过程与分歧解决 |
| **Auto-Precheck** | 5-10分钟自动 FATAL 检查 |
| **Auto-Check Coordinator** | 管理自动检查 |
| **软性风险分层** | FATAL 优先上报，不中断检查 |
| **统一检查调度器** | check_orchestrator.py 协调所有检查器 |

---

## 🏢️ 团队架构
```
┌───────────────────────────────────────────────────────────────────┐
│                    Lead Auditor (协调员)                        │
│    管理收敛流程、交叉比对、最终裁决、报告生成、经验总结          │
└────────────────────────┬──────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼────────┐ ┌────▼─────────┐ ┌────▼─────────┐
│ Auto-Check      │ │              │ │              │
│ Coordinator     │ │  三路独立    │ │  交叉收敛    │
│ (Round 0)       │ │  Sub-Agent   │ │  机制        │
├────────────────┤ ├──────────────┤ ├──────────────┤
│ 管理自动检查    │ │ Agent A      │ │ 交叉比对     │
│ 风险分层       │ │ Agent B      │ │ 问题并集     │
│ 检查调度       │ │ Agent C      │ │ 迭代收敛     │
│ 结果汇总       │ │ JSON落盘     │ │ 终止判定     │
└────────────────┘ └──────────────┘ └──────────────┘
```

### Sub-Agent 切片定义

每个 Sub-Agent 只执行 `agent_prompts/slices/*.md` 指定的一个窄范围，不得扩审到完整项目。

| 收敛路由 | 切片示例 | 目标 |
|----------|----------|------|
| A | 覆盖与证据切片 | D1 覆盖完整性、D5 证据充分性 |
| B | 数字事实与图文一致切片 | D2 事实正确性、D3 三方一致性 |
| C | 方法代码、统计与高风险模块切片 | D6 方法-代码一致、统计判断、高风险模块 |

切片输出必须写入 `agent_results/slices/*.json`。A/B/C 汇总器只读取本路 slice JSON，不能重新做全项目审核。

### 新角色：Auto-Check Coordinator（保留）

**职责**：
1. 管理 Auto-Precheck 阶段
2. 运行统一检查调度器
3. 执行风险分层评估
4. 汇总自动检查结果
5. 生成 `agent_prompts/agent_slice_manifest.json`、`agent_prompts/slices/*.md` 和三路汇总 prompt

**检查项**：
- 项目编号一致性（P0 - FATAL）
- 术语主题一致性（P0 - FATAL）
- 跨模块数据流验证（P0 - FATAL）
- 可视化阈值一致性（P1 - CRITICAL）
- 基因命名规范化（P1 - CRITICAL）

---
---

## 🔄 检查流程
> **完整收敛协议详见**: [CONVERGENCE_REVIEW_PROTOCOL.md](../CONVERGENCE_REVIEW_PROTOCOL.md)

## 强制中间产物（保留）

小切片与三路汇总必须共同覆盖以下 3 类中间产物：

1. `coverage_matrix`
  - 逐项列出数据集、模块、暴露/亚组、Figure/Table、阴性结果
  - 标记"实际存在 / 报告是否覆盖 / 证据充分性 / 是否有结构化结果文件 / 审核状态"

2. `fact_check_list`
  - 核对数据库名称、URL、功能描述、术语翻译、样本范围用语

3. `unresolved_items`
  - 记录无法确认但会影响结论的差异，禁止直接忽略

**没有以上 3 份产物，或缺少任何 required slice JSON，视为三路审核未完成。**

覆盖矩阵中的每一行都必须对应到单个分析点，而不是笼统模块总结。

### Round 0: 自动预检查（保留，5-10分钟）

```
Auto-Precheck阶段（自动执行）
├── 运行 auto_audit_pipeline.py
├── P0级检查（FATAL）
│   ├── 项目编号一致性检查
│   ├── 术语主题匹配检查
│   ├── 跨模块数据流验证
│   └── 物种一致性检查
├── P1级检查（CRITICAL）
│   ├── 证据完整性 / 基因命名 / 可视化阈值 ...
│   └── 共计 14 个 P1 检查器
├── 风险分层判断
└── 生成预检查报告 → 作为小切片 prompt 的摘要输入
```

**关键特性**：
- ✅ 完全自动化，无需额外干预
- ✅ 5-10分钟完成
- ✅ 发现 FATAL 也继续汇总全部问题
- ✅ 预检查报告是小切片 prompt 的共同事实底座

### Round 1: 小切片 Sub-Agent 执行

```
Lead Auditor 读取 agent_slice_manifest.json
├── Batch 1: 启动 2-4 个小切片 Sub-Agent
│   ├── 每个判断型切片使用强判断模型，不因切片变小而降级
│   ├── 每个切片只读自己的 prompt、重叠上下文和必要局部证据
│   ├── 不 fork/copy leader 完整上下文
│   └── 写入 agent_results/slices/*.json
├── 写 checkpoint: review_event_log.jsonl + subagent_supervision_summary.json
├── Batch 2/3: 继续执行剩余切片
└── 运行 slice 完整性验收后，再进入三路汇总
```

**每个切片 Sub-Agent 必须**：
- 只处理 prompt 指定的窄范围，不得扩审到完整项目
- 正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini/explore 只允许做定位、清单、schema、grep
- 保留必要重叠上下文：摘要/结论、Figure/Table 索引、机械检查摘要、case_manifest、相邻依赖模块
- 完整发现写入指定 `agent_results/slices/*.json`
- 聊天只返回状态、输出路径、发现数量、最高严重度、阻断项
- 完成后立即停止，不顺手审其他模块

**A/B/C 汇总器必须**：
- 只读取本路 slice JSON
- 汇总 findings、coverage_matrix、mechanical_dispositions、high_risk_modules
- 不重新打开全文做完整审核

**Lead 全局复核必须**：
- 检查覆盖缺口、slice 冲突、跨模块链条断裂
- 检查“局部通过但整体不成立”的问题
- 检查高风险模块是否被分配并以模块级上下文审过
- 严重度、统计适用性、高风险结论和最终仲裁不得由弱模型单独决定

### Round 2: 交叉比对 + 迭代收敛

```
Lead Auditor 收集 三路汇总结果

第一步: 交叉比对
├── 共识问题（3/3 一致） → 直接纳入最终列表
├── 多数一致（2/3） → 待验证
├── 单方发现（1/3） → 待验证
└── 分歧问题（结论冲突） → 高优先级

第二步: 迭代收敛（如有不一致）
├── 构建问题并集（Union Set）
├── 针对分歧点启动小切片复核
│   ├── 验证他人发现的问题
│   ├── 重新审查分歧项（附新证据）
│   └── 补做覆盖差异项
├── 再次交叉比对
└── 循环: 最多 3 轮迭代

终止条件（全部满足）:
├── ✅ 三路结论完全一致（共识率 = 100%）
├── ✅ 无新增问题
├── ✅ 无分歧项
└── ⏰ 硬限制: 3 轮迭代后仍有分歧 → Lead Auditor 裁决
```

### Round 3: 最终确认（保留，10-15分钟）

```
Lead Auditor 协调：
├── 汇总收敛后一致结论
├── 合并 三路覆盖矩阵（取并集覆盖）
├── 生成 final_review_report.md
├── 运行 finalize_audit.py 完成最终收口与 HTML 交付
├── 编写经验总结（含收敛过程摘要）
├── 更新框架文档
├── 核对 coverage_matrix 中所有项已闭环
├── 核对所有"证据不足"项已单独列示
└── 核对无代码项目已写明"代码不可复现风险"
```

---

## 🔧 使用流程
### 步骤1：运行 Auto-Precheck

```bash
# 运行自动检查流水线
python result_review_framework/scripts/auto_audit_pipeline.py <项目路径> --project-type <疾病类型>

# 查看报告
cat check_reports/auto_audit/auto_audit_report_*.md
```

### 步骤2：生成围栏并启动小切片审核

```
先运行：
python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号> --project-dir <项目路径>

按 `agent_prompts/agent_slice_manifest.json` 分批启动 2-4 个小切片 Sub-Agent，优先使用 `agent_prompts/slices/*.md` 作为执行输入。
每个切片只读必要局部证据并写入 `agent_results/slices/*.json`；不得 fork/copy Lead Auditor 完整上下文。
如需补充参考材料，只附带对应切片需要的 `WORKFLOW.md` / `CHECKLIST_TEMPLATE.md` / `MASTER_PROMPT.md` 摘要。
```

### 步骤3：交叉比对

```
收集 3 方输出 → 按 CONVERGENCE_REVIEW_PROTOCOL.md 执行：
1. 问题对齐（统一编号）
2. 一致性分类（共识/多数/单方/分歧）
3. 判断是否需要迭代
```

### 步骤4：迭代收敛（如需）

```
构建问题并集 → 针对分歧点启动小切片复核 → 再次比对
最多 3 轮，或提前收敛
```

### 步骤5：最终确认与交付

```
Lead Auditor 合并结论 → final_review_report.md → audit_report.html
Round 0 → 自动检查
Round 1 → 小切片审核（分批落盘）
Round 2 → 交叉比对 + 迭代收敛
Round 3 → 最终确认 + 报告生成
```

---

## ⚠️ 重要提醒
1. **所有数据分析项目审核必须先运行 Auto-Precheck**
2. **Auto-Precheck 完成后必须带着问题清单启动小切片 Sub-Agent，并由 A/B/C 汇总器收敛**
3. **每个小切片 Sub-Agent 必须独立完成指定窄范围并落盘 JSON，不得扩审完整项目**
4. **每个分析点必须形成"方法-结果描述-结果文件-证据充分性"闭环**
5. **只有图片或 PDF、没有结构化结果文件的分析点不得直接判为通过**
6. **未交付代码的项目必须在最终报告单列代码不可复现风险**
7. **交叉比对必须在全部 required slice JSON 验收通过且三路汇总完成后进行，不得提前泄露中间结果**
8. **迭代收敛最多 3 轮，达到硬限制后由 Lead Auditor 裁决**
9. **不允许用"多数一致"替代证据验证——必须有实际证据支持**
10. **审核完成后必须生成经验总结并更新框架文档**
11. **自动机械检查的每一条问题都必须有处置结论，不得既引用又不裁决**

---

## 📊 预期效果
| 指标 | 目标值 |
|------|--------|
| FATAL问题遗漏率 | <2% |
| 审核一致性 | >95% |
| 遗漏问题召回率 | >95% |
| 误判率 | <5% |
| 审核团队结构 | 小切片执行 + 三路汇总 + Lead裁决 |

---

## 📈 版本历史

详见 [v6_CHANGELOG.md](../archive/history/v6_CHANGELOG.md)

---

**版本**: v7.1
**创建日期**: 2026-04-02 | 更新: 2026-07-30
**基于**: 审核框架主线 v7.1
**状态**: ✅ 已发布，强制执行
