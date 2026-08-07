#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
三路收敛审核 Prompt 自动构造器

功能：基于预检查结果和框架文档，生成“小切片 Sub-Agent + 三路汇总”审核 prompt。
解决核心问题：
1. 子代理不读文档就开始审核；
2. 单个 Sub-Agent 一次性审核内容过多，触发 remote compact 或上下文丢失。

v6.7 起默认不再让单个 Sub-Agent 承担完整项目审核；三路仍作为收敛口径，
但执行层改为多个窄切片先落盘，再由每路汇总 prompt 生成 agent_a/b/c_result.json。

用法：
    python launch_convergence_audit.py <review_dir> [--project-dir <project_dir>]

输出：
    <review_dir>/agent_prompts/
        agent_slice_manifest.json — 小切片执行清单
        slices/*.md              — 每个窄切片的 Sub-Agent prompt
        agent_a_prompt.md        — Agent A 汇总 prompt：只读取 A 路 slice JSON
        agent_b_prompt.md        — Agent B 汇总 prompt：只读取 B 路 slice JSON
        agent_c_prompt.md        — Agent C 汇总 prompt：只读取 C 路 slice JSON
        convergence_guide.md — Lead Auditor 收敛阶段指引
"""

import json
import sys
from pathlib import Path
from datetime import datetime

SCRIPT_UTILS_DIR = Path(__file__).resolve().parents[1] / 'script_utils'
if str(SCRIPT_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_UTILS_DIR))

from base_project_checker import strip_non_audit_appendix
from policy_loader import load_policy, policy_path


# --- 框架文档摘要（内嵌，避免运行时依赖文件路径） ---

_POLICY = load_policy()
_ALLOWED_SOURCE_TYPES = ", ".join(
    f"`{item}`" for item in _POLICY["finding_evidence_policy"]["allowed_source_types"]
)
_REQUIRED_FINDING_FIELDS = ", ".join(
    f"`{item}`" for item in _POLICY["finding_evidence_policy"]["required_fields"]
)
_FORBIDDEN_SHORTCUTS = " / ".join(
    f"`{item}`" for item in _POLICY["forbidden_shortcuts"]
)

_CORE_RULES_SUMMARY = f"""
## 六维审核框架
| # | 维度 | 核心问题 |
|---|------|---------|
| D1 | 覆盖完整性 | 报告是否涵盖所有分析模块和结果？ |
| D2 | 事实正确性 | 数字、术语、数据库描述是否正确？ |
| D3 | 三方一致性 | 正文、表格、图注是否一致？ |
| D4 | 结果可追溯 | 结论能否追溯到具体文件？ |
| D5 | 证据充分性 | 交付物是否足以支撑结论？ |
| D6 | 方法-代码一致 | 报告描述的方法与代码实现是否一致？ |

## 问题严重度
- FATAL: 项目根基性错误（≤30分）
- CRITICAL: 影响核心结论（≥3 个 → ≤50分）
- MAJOR: 明确错误但不影响核心结论
- WARNING: 不确定是否为错误
- INFO: 建议改进

## 每个分析点必答 4 问
1. 方法在报告中是否写清？
2. 结果描述是否出现？
3. 对应结果文件是否存在？
4. 证据是否足以支撑结论？

## 强制执行规则
- 本次任务默认属于“正式审核”，小切片执行 + A/B/C 三路汇总收敛为必做步骤，不等待额外授权
- 先读 `{policy_path().as_posix()}`，它是当前唯一机器策略源
- `mechanical_check_result.json` 中的结果只能作为候选问题，不能直接照单接收
- 你必须区分：模块真实存在 / 证据是否充分 / 是否可复现 / 结论强度是否过度外推
- 若发现正文、图注、高风险模块混入外项目对象（错误疾病、药物、体系名、图号），必须升级为实质问题
"""

_AGENT_A_EMPHASIS = """
## 你的强化维度：D1（覆盖完整性）+ D5（证据充分性）

你的核心视角："做完了吗？证据够吗？"

### 补充指令
1. 流程图中每个分析步骤是否都有对应结果章节和交付目录？
2. 是否存在隐藏的阴性结果（空交集、无显著通路、筛选后剩 0 个基因）？
3. 每个模块的证据等级评分：
   - A级：有完整证据链（数据→代码→中间结果→最终结果→图表）
   - B级：有结果但缺中间过程
   - C级：仅有图片无结构化结果
4. 仅有图片无结果表 → 标记"证据不足"
5. 药物预测需有完整检索策略和结果合并逻辑
6. 分子对接需有结合能/分数数值表
7. 单细胞 QC 前后图不能为同一张图重复使用
8. 对高风险模块（分子对接/MD/虚拟敲除）分别判断：模块是否真实存在、证据是否充分、是否可复现、结论是否外推过度
"""

_AGENT_B_EMPHASIS = """
## 你的强化维度：D2（事实正确性）+ D3（三方一致性）

你的核心视角："数字对不对？哪里不一致？"

### 补充指令
1. 关键数字在正文/表格/图注三处是否一致？
2. 基因名全文拼法一致性（不能同一基因不同位置拼法不同）
3. 利用 report_structure.json 中的 numbers_in_context 和 gene_names 字段进行交叉核对
4. 数据库名称 + URL + 功能描述三方对应（STRING→PPI，KEGG→pathway）
5. 统计判断方向正确：p<0.05 显著、|log2FC|>1 差异、HR>1 风险因素
6. TopN 列表在正文和图表中顺序、数量一致
7. 英文术语中文翻译正确
8. 全文搜索外项目残留：错误疾病名、错误药物名、错误图号、错误体系名（如 HCK-Tamibarotene）
"""

_AGENT_C_EMPHASIS = """
## 你的强化维度：D6（方法-代码一致）+ 统计判断

你的核心视角："方法对不对？统计用对了吗？"

### 补充指令
1. 报告声称的 R 包/Python 包/参数是否在代码中有实际调用？参照 project_structure.json 的 all_packages 字段
2. 参数阈值（logFC、pvalue、FDR）报告 vs 代码一致性
3. 机器学习算法名 → 代码包调用 → 输入特征集三方一致
4. 统计方法适用性判断（参考 STATISTICS_REFERENCE.md）：
   - 组间比较：参数检验 vs 非参数？样本量是否足够？
   - 生存分析：Cox 模型假设是否满足？
   - 多重检验校正是否应用？
5. 检查 project_structure.json 中的 GEO 数据集引用：
   - 代码中使用的 GEO 是否在报告中声明？
   - GEO 数据集的疾病类型是否与项目一致（如用 LUAD 的数据做 BRCA 项目）？
6. 硬编码路径默认只作背景信息；只有在路径暴露错误项目来源、错误模块来源、或结果来源无法判断时，才升级为问题
7. 对高风险模块额外检查：方法定义阈值与结论强度是否冲突；MD 是否混入外项目体系/图号/时长；虚拟敲除正文是否被结果表支撑
"""

_OUTPUT_FORMAT = """
## 输出格式要求

你的审核结果必须严格按以下 JSON 格式输出（便于收敛阶段自动比对）：

```json
{
  "agent": "A/B/C",
  "round": 1,
  "coverage_matrix": {
    "<模块名>": {
      "method_described": true/false,
      "result_present": true/false,
      "file_exists": true/false,
      "evidence_level": "A/B/C",
      "issues": ["问题描述"]
    }
  },
  "findings": [
    {
      "raw_finding_id": "A:raw:001",
      "finding_key": "fk:xxxxxxxxxxxxxxxx",
      "cluster_key": "cluster:xxxxxxxxxxxxxxxx",
      "id": "A-001",
      "severity": "FATAL/CRITICAL/MAJOR/WARNING/INFO",
      "dimension": "D1-D6",
      "location": "报告中的具体位置（章节+行号）",
      "description": "问题描述",
      "evidence": "证据（引用原文/文件路径/数值）",
      "rule": "R01-R20 对应规则编号",
      "source_type": "report_text/figure/table/result_file/code/precheck",
      "source_path": "具体文件路径或逻辑来源",
      "locator": "行号/页码/图号/表号/sheet/章节",
      "quote_or_value": "引用原句、标签或关键数值",
      "module": "分析模块",
      "claim": "被审核的具体声明",
      "error_mechanism": "错误如何产生",
      "evidence_object": "被比较的证据对象",
      "repair_path": "需要重跑或修正的路径"
    }
  ],
  "mechanical_dispositions": [
    {
      "code": "MC-005",
      "auto_severity": "CRITICAL",
      "disposition": "保留/撤销/降级/升级",
      "final_severity": "FATAL/CRITICAL/MAJOR/WARNING/INFO",
      "reason": "为什么保留或为什么是误报"
    }
  ],
  "high_risk_modules": [
    {
      "module": "molecular_docking/molecular_dynamics/virtual_knockout/graphban_virtual_screening",
      "status": "pass/fail/unknown/not_applicable",
      "module_exists": true/false,
      "evidence_sufficient": true/false,
      "reproducible": true/false,
      "conclusion_not_overstated": true/false,
      "evidence_refs": [],
      "reason": "分层判断的简要证据说明"
    }
  ],
  "self_review": {
    "missed_modules": [],
    "severity_changes": [],
    "new_findings": [],
    "confirmed": []
  },
  "summary": {
    "total_findings": 0,
    "fatal": 0,
    "critical": 0,
    "major": 0,
    "warning": 0,
    "info": 0,
    "suggested_score": 0,
    "verdict": "合格/有条件合格/不合格"
  }
}
```

**输出时直接返回 JSON**，不要包裹在 markdown 代码块中。

### 格式严格要求
- 所有数值字段（total_findings, fatal, critical, major, warning, info, suggested_score）必须是 **数字**，不能是字符串
- suggested_score 范围 0-100
- severity 只允许: FATAL, CRITICAL, MAJOR, WARNING, INFO
- verdict 只允许: 合格, 有条件合格, 不合格
- evidence_level 只允许: A, B, C
- disposition 只允许: 保留, 撤销, 降级, 升级
- 如果某个字段无值，使用空字符串 "" 或 0，不要使用 null
- 自动检查只能生成 candidate finding；不得自动决定严重度、实际结论污染或重跑结果数
- 相似问题必须保留 raw_finding_id，不得因 finding_key 相似就提前终审合并
"""

_OUTPUT_FORMAT += (
    "\n- `finding_key` 必须基于 `dimension + rule + source_path + locator + quote_or_value` 稳定生成；同一问题在三路输出中应保持一致"
    f"\n- findings 中必须包含这些字段：{_REQUIRED_FINDING_FIELDS}"
    f"\n- `source_type` 只允许使用：{_ALLOWED_SOURCE_TYPES}"
    f"\n- 禁止使用偷懒结论：{_FORBIDDEN_SHORTCUTS}\n"
)

_DOUBLE_ROUND_INSTRUCTION = """
## 双轮审核流程

### 第一轮：深度审查
完成六维全面审核，为每个分析点构建证据矩阵（方法→结果→文件→证据）。

### 第二轮：自我复查
对第一轮结论执行以下检查：
- 是否遗漏未覆盖的分析点？
- 误判严重等级的情况？
- 只看正文未看表格/图注？
- 只看结果存在未验证数值？
- 遗漏阴性结果？
- Round 0 问题是否全部回应？

标注修改类型：
- 「复查新增」：新发现的问题
- 「复查修正」：修改了严重度或结论
- 「复查确认」：无误

### 与 Round 0 预检查结果的关系
- 如果你要报告的问题在 Round 0 预检查中**已经存在**，在 findings 中标注 `"source": "confirmed_from_precheck"` 并保留原编号
- 仅 Round 0 **没有**的问题才标注 `"source": "new"`
- 不要简单复制 Round 0 的结果——你需要验证它们是否准确，然后确认或修正

### 对 mechanical_check_result.json 的强制处置
- 你必须对每一条机械检查候选问题给出处理意见：`保留 / 撤销 / 降级 / 升级`
- 如果你认为某条是误报，必须说明误报原因（如命名映射不足、目录匹配规则过窄）
"""


_MERGE_INSTRUCTION = """
## 三路汇总流程

你不是原始审核切片，不要重新做全项目审核。

### 第一轮：读取本路切片 JSON
- 只读取本 Agent 对应的 `agent_results/slices/*.json`。
- 汇总 findings、coverage_matrix、mechanical_dispositions、high_risk_modules。
- 保留每条 finding 的 `source_path`、`locator`、`quote_or_value`，不要改写成无证据概述。

### 第二轮：汇总自检
- 去重同一问题，保持稳定 `finding_key`。
- 检查机械检查候选问题是否已有处置；缺失时在 `self_review.missed_modules` 或 blocker 中标出。
- 检查高风险模块四维判断是否齐全。
- 只允许基于切片 JSON 做一致性修正；不要回到全文重新扩审。
"""


_COMPACT_SAFETY_PROTOCOL = """
## Remote Compact 防护与小切片执行硬规则

本框架把 remote compact failure 当作常态风险处理。除非项目被明确标记为 very_small，
否则禁止让单个 Sub-Agent 一次性完成全项目审核。

### 必须执行
1. **小切片**：每个 Sub-Agent 只处理本 prompt 指定的一个窄范围，不得扩审到全项目。
2. **不 fork 大上下文**：启动子代理时不要复制 leader 全量上下文；只传本 prompt 和必要路径。
3. **落盘优先**：完整发现写入指定 JSON 文件；聊天返回最多 5 行，只允许状态、证据路径、发现数量、最高严重度、阻断项。
4. **上下文预算**：单个切片最多读取 1 个大 JSON 摘要 + 必要的局部源文件；长日志写到 `.omx/logs/`。
5. **硬停止**：完成本切片输出后立即停止；不要顺手审核其他模块。
6. **批次上限**：Lead 每批最多并发 4 个切片；每批结束后写入 `review_event_log.jsonl` 并更新项目内 `subagent_supervision_summary.json`。
7. **失败再拆分**：如果任一 Sub-Agent 触发 remote compact/context loss，Lead 必须把该切片按章节、模块、图号范围、文件组或问题簇继续拆小后重试；禁止按原范围重复启动。

### 禁止执行
- 禁止要求一个 Sub-Agent “完整审核整个项目”。
- 禁止在聊天中粘贴长表、全文报告、完整日志或完整 JSON。
- 禁止把 subagent 结果只留在聊天记录；必须写入文件。
- 禁止把完整 Markdown 报告、完整 JSON、长日志、大表、完整通知 metadata 或内部归档路径贴回 Lead 主线程。
"""


_MODEL_QUALITY_PROTOCOL = """
## 模型能力与重叠上下文硬规则

小切片只用于控制上下文和防 compact，不代表降低审核判断能力。

### 模型能力
- Lead 只做监工/整合/仲裁，不在主线程展开长报告、长日志、完整清单或大证据；完整证据由 subagent 落盘。
- 正式判断型 Sub-Agent 必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；不要因为切片变小就降级或改用其他模型。
- fast/mini 模型只可用于文件定位、路径清单、格式/schema 检查、grep 类检索；explore 同样只可作为检索/定位辅助。
- 严重度裁定、跨模块一致性、统计适用性、高风险模块判断、最终仲裁不得下放给弱模型单独决定。

### 重叠上下文
- 每个判断型切片必须至少保留：项目摘要/结论段、Figure/Table 索引、机械检查摘要、case_manifest、与本切片相邻的依赖模块路径。
- 高风险模块切片必须保留模块级完整上下文，不能按单文件过窄拆分。
- 如果本切片需要的全局上下文缺失，应输出 blocker，而不是凭局部证据判通过。

### 全局复核
- A/B/C 汇总只汇总本路 slice JSON；Lead 必须再做全局一致性复核：覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块。
"""


SLICE_SPECS = [
    {
        "id": "a01",
        "agent": "A",
        "title": "模块覆盖与报告范围",
        "focus": "D1 覆盖完整性：报告章节、结果目录、流程模块是否一一对应。",
        "read_first": ["report_structure.json", "project_structure.json", "report_text.txt"],
        "questions": [
            "报告声明的分析模块是否都有结果目录或文件？",
            "结果目录中的核心模块是否在报告中出现？",
            "是否存在未报告数据集、未报告模块或跨项目残留？",
        ],
    },
    {
        "id": "a02",
        "agent": "A",
        "title": "证据充分性与交付缺口",
        "focus": "D5 证据充分性：每个核心结论是否具备结构化结果、代码或中间文件支撑。",
        "read_first": ["project_structure.json", "mechanical_check_result.json"],
        "questions": [
            "哪些分析点只有图片、没有结构化结果表？",
            "哪些结论缺少中间结果或原始输出？",
            "药物预测、富集、网络、scRNA 模块证据等级分别是多少？",
        ],
    },
    {
        "id": "b01",
        "agent": "B",
        "title": "数字、阈值和事实一致性",
        "focus": "D2 事实正确性：关键数字、阈值、基因名、数据库名是否一致。",
        "read_first": ["report_structure.json", "mechanical_check_result.json", "report_text.txt"],
        "questions": [
            "正文、表格、图注中的关键数字是否一致？",
            "阈值、p 值、logFC、TopN、样本量是否自洽？",
            "机械检查候选事实问题哪些保留、撤销、降级或升级？",
        ],
    },
    {
        "id": "b02",
        "agent": "B",
        "title": "图文一致性与视觉预筛处置",
        "focus": "D3 三方一致性：图号、图注、图片内容、视觉预筛 flags 是否闭环。",
        "read_first": ["visual_prefilter.json", "visual_audit_checklist.json", "figure_audit.md", "report_text.txt"],
        "questions": [
            "视觉预筛标记是否已逐项处置？",
            "是否存在重复图、错图、图题/正文不一致或外项目图残留？",
            "图文错误是否影响核心结论？",
        ],
    },
    {
        "id": "b03",
        "agent": "B",
        "title": "数据集与外项目残留",
        "focus": "D2+D3：GEO 编号、疾病/药物/体系名是否混入外项目或未报告来源。",
        "read_first": ["project_structure.json", "report_text.txt"],
        "questions": [
            "代码或结果中的 GEO 是否全部在报告中声明？",
            "疾病名、药物名、细胞类型、分子体系是否与本项目一致？",
            "发现残留时应升级为 WARNING、MAJOR 还是 CRITICAL？",
        ],
    },
    {
        "id": "c01",
        "agent": "C",
        "title": "方法-代码一致性",
        "focus": "D6 方法-代码一致：报告声称的软件包、算法和参数是否在代码中实现。",
        "read_first": ["project_structure.json", "mechanical_check_result.json", "report_text.txt"],
        "questions": [
            "报告声称的方法是否能在代码文件中定位？",
            "参数阈值是否与代码一致？",
            "机械检查的方法-代码候选问题哪些为误报？",
        ],
    },
    {
        "id": "c02",
        "agent": "C",
        "title": "统计与机器学习结论充分性",
        "focus": "统计判断：差异分析、模型筛选、ROC/AUC、校正方法和结论强度。",
        "read_first": ["project_structure.json", "report_structure.json", "report_text.txt"],
        "questions": [
            "统计方法是否适用于当前数据结构？",
            "机器学习输入、筛选算法、关键基因和验证结果是否对应？",
            "ROC/AUC、置信区间、样本量等是否有结构化导出？",
        ],
    },
    {
        "id": "c03",
        "agent": "C",
        "title": "高风险模块专项",
        "focus": "分子对接、分子动力学、虚拟敲除等高风险模块：存在性、证据充分性、可复现性、是否外推。",
        "read_first": ["project_structure.json", "mechanical_check_result.json", "report_text.txt"],
        "questions": [
            "高风险模块是否真实存在结果文件？",
            "是否交付可复现脚本、参数、运行命令和结构化结果？",
            "报告结论是否超过现有证据强度？",
        ],
    },
]


def slice_output_path(review_dir: Path, spec: dict) -> Path:
    return review_dir / "agent_results" / "slices" / f"agent_{spec['agent'].lower()}_{spec['id']}_result.json"


def slice_prompt_path(review_dir: Path, spec: dict) -> Path:
    return review_dir / "agent_prompts" / "slices" / f"agent_{spec['agent'].lower()}_{spec['id']}_prompt.md"


def load_precheck_results(review_dir: Path) -> dict:
    """加载预检查结果"""
    results = {}

    # 机械检查结果
    mc_path = review_dir / 'mechanical_check_result.json'
    if mc_path.exists():
        mc = json.loads(mc_path.read_text(encoding='utf-8'))
        results['mechanical_checks'] = {
            'total': mc.get('total_issues', 0),
            'counts': mc.get('counts', {}),
            'fatal_critical': [
                f"[{i['code']}] {i['severity']}: {i['message']}"
                for i in mc.get('issues', [])
                if i['severity'] in ('FATAL', 'CRITICAL')
            ],
            'all_issues': [
                f"[{i['code']}] {i['severity']}: {i['message']}"
                for i in mc.get('issues', [])
            ],
        }

    # 视觉审核准备
    va_path = review_dir / 'visual_audit_checklist.json'
    if va_path.exists():
        va = json.loads(va_path.read_text(encoding='utf-8'))
        to_audit = [item for item in va if item.get('needs_audit')]
        type_dist = {}
        for item in to_audit:
            t = item.get('guessed_type', 'unknown')
            type_dist[t] = type_dist.get(t, 0) + 1
        results['visual_audit'] = {
            'total_images': len(va),
            'to_audit': len(to_audit),
            'type_distribution': type_dist,
            'has_figure_audit': (review_dir / 'figure_audit.md').exists(),
        }

    # 报告结构
    rs_path = review_dir / 'report_structure.json'
    if rs_path.exists():
        rs = json.loads(rs_path.read_text(encoding='utf-8'))
        results['report_structure'] = {
            'total_sections': len(rs.get('sections', [])),
            'total_figures': len(rs.get('figure_refs', [])),
            'total_tables': len(rs.get('table_refs', [])),
            'gene_names_count': len(rs.get('gene_names', [])),
            'numbers_count': len(rs.get('numbers_in_context', [])),
        }

    # 项目结构
    ps_path = review_dir / 'project_structure.json'
    if ps_path.exists():
        ps = json.loads(ps_path.read_text(encoding='utf-8'))
        meta = ps.get('metadata', {})
        results['project_structure'] = {
            'modules': [m['name'] for m in ps.get('modules', [])],
            'total_code_files': meta.get('total_code_files', 0),
            'packages': meta.get('all_packages', []),
            'geo_refs': [g['id'] for g in ps.get('geo_references', [])],
            'project_ids': ps.get('project_id_references', []),
        }

    # orchestrator 结果
    orch_path = review_dir / 'auto_audit_report.json'
    if orch_path.exists():
        orch = json.loads(orch_path.read_text(encoding='utf-8'))
        results['orchestrator'] = {
            'total_findings': orch.get('total_findings', 0),
            'quality_status': orch.get('quality_status', ''),
        }

    return results


def load_report_excerpt(review_dir: Path, max_lines: int = 160) -> str:
    """加载报告文本短概览，避免把整份报告塞入每个 Sub-Agent 上下文。"""
    report_path = review_dir / 'report_text.txt'
    if not report_path.exists():
        return "(报告文本不可用)"
    lines = strip_non_audit_appendix(report_path.read_text(encoding='utf-8')).splitlines()
    if len(lines) <= max_lines:
        return '\n'.join(lines)
    return '\n'.join(lines[:max_lines]) + f"\n\n... (共 {len(lines)} 行，以上仅为前 {max_lines} 行概览。切片审核只能按需读取相关局部行段，不要全文粘贴。)"


def build_agent_prompt(
    agent_id: str,
    emphasis: str,
    review_dir: Path,
    project_dir: Path | None,
    precheck: dict,
    report_excerpt: str,
) -> str:
    """构造每路汇总 Agent prompt。

    该 prompt 只读取同一路的小切片 JSON，汇总成 convergence_compare.py
    需要的 agent_a/b/c_result.json；不得重新审核完整项目。
    """

    # 文件路径提示
    agent_slice_inputs = "\n".join(
        f"- `{slice_output_path(review_dir, spec)}`"
        for spec in SLICE_SPECS
        if spec["agent"] == agent_id
    )
    paths_section = f"""
## 文件路径

审核目录: `{review_dir}`
{f'项目目录: `{project_dir}`' if project_dir else '项目目录: (未指定)'}

### 本路必须汇总的小切片结果
{agent_slice_inputs}

### 你需要读取的文件（按优先级）
1. `{review_dir / 'agent_results' / 'slices'}` — 本 Agent 对应的小切片 JSON
2. `{review_dir / 'mechanical_check_result.json'}` — 只用于核对机械检查编号
3. `{review_dir / 'project_structure.json'}` — 只用于核对路径和模块名

不要重新全文审核 `report_text.txt`；如需补证据，只读取切片 JSON 中已经列出的局部路径/行号。
"""

    # 预检查结果摘要
    precheck_section = "## Round 0 预检查结果摘要\n\n"
    mc = precheck.get('mechanical_checks', {})
    if mc:
        precheck_section += f"### 机械检查: {mc['total']} 个问题\n"
        precheck_section += f"严重度分布: {json.dumps(mc['counts'], ensure_ascii=False)}\n\n"
        if mc['fatal_critical']:
            precheck_section += "**FATAL/CRITICAL 问题（必须回应）：**\n"
            for issue in mc['fatal_critical']:
                precheck_section += f"- {issue}\n"
            precheck_section += "\n"
        precheck_section += "**全部问题清单：**\n"
        for issue in mc['all_issues']:
            precheck_section += f"- {issue}\n"
        precheck_section += "\n"

    ps = precheck.get('project_structure', {})
    if ps:
        precheck_section += f"### 项目结构\n"
        precheck_section += f"- 模块: {', '.join(ps['modules']) if ps['modules'] else '无'}\n"
        precheck_section += f"- 代码文件: {ps['total_code_files']} 个\n"
        precheck_section += f"- GEO 数据集: {', '.join(ps['geo_refs']) if ps['geo_refs'] else '无'}\n"
        precheck_section += f"- R/Python 包: {len(ps['packages'])} 个\n\n"

    va = precheck.get('visual_audit', {})
    if va:
        precheck_section += f"### 视觉审核\n"
        precheck_section += f"- 图片总数: {va['total_images']}\n"
        precheck_section += f"- 需审核: {va['to_audit']}\n"
        precheck_section += f"- 类型分布: {json.dumps(va['type_distribution'], ensure_ascii=False)}\n\n"

    # 视觉审核指令
    visual_instruction = ""
    if va and va.get('has_figure_audit'):
        visual_instruction = f"""
## 视觉审核要求

汇总 Agent 不直接执行逐图审核；逐图或抽样检查必须由 `slices/` 中的图文一致性切片完成。
如果图文切片缺失或未落盘，输出 blocker，不要自行补做全量视觉审核。
"""

    # 组装完整 prompt
    prompt = f"""# 生物信息学报告审核 — Agent {agent_id} 汇总器

**角色**: 你是生物信息学数据分析报告审核的 Agent {agent_id} 汇总器。
**独立性**: 你只汇总 Agent {agent_id} 的小切片结果，不参考其他 Agent 的结论。
**语言**: 使用中文输出。
**注意**: 这是正式审核，不是草稿或初筛。禁止重新做全项目审核；只合并同路 slice JSON，生成最终结构化 JSON。

{_COMPACT_SAFETY_PROTOCOL}

{_MODEL_QUALITY_PROTOCOL}

{_CORE_RULES_SUMMARY}

{emphasis}

{_MERGE_INSTRUCTION}

{paths_section}

{precheck_section}

{visual_instruction}

{_OUTPUT_FORMAT}

## 报告文本短概览（仅供识别项目，不作为重新全文审核输入）

以下是报告前 160 行。不要把它扩展为全文读取任务。

```
{report_excerpt}
```

---

**开始汇总。请读取同路 slice JSON，输出 JSON 格式结果。**
"""
    return prompt


def build_slice_prompt(
    spec: dict,
    review_dir: Path,
    project_dir: Path | None,
    precheck: dict,
    report_excerpt: str,
) -> str:
    """构造一个窄切片 Sub-Agent prompt。"""
    output_path = slice_output_path(review_dir, spec)
    read_first = "\n".join(f"- `{review_dir / item}`" for item in spec["read_first"])
    questions = "\n".join(f"{idx}. {question}" for idx, question in enumerate(spec["questions"], start=1))
    agent_id = spec["agent"]

    return f"""# 生物信息学报告审核 — 小切片 {spec['id']}：{spec['title']}

**所属收敛路由**: Agent {agent_id}
**切片范围**: {spec['focus']}
**输出文件**: `{output_path}`
**项目目录**: `{project_dir if project_dir else ''}`

{_COMPACT_SAFETY_PROTOCOL}

{_MODEL_QUALITY_PROTOCOL}

## 只读输入

优先读取以下文件；除非回答本切片问题必须，不要读取其他大文件：
{read_first}

如需定位报告原文，只读取相关行段并在 finding 中写明 `report_text.txt Lx-Ly`。
如需跑 grep 或统计，请把完整日志写到 `.omx/logs/`，不要贴到聊天。

## 本切片必须回答的问题

{questions}

## 预检查摘要

```json
{json.dumps(precheck, ensure_ascii=False, indent=2)[:6000]}
```

## 报告短概览

```text
{report_excerpt}
```

## 输出要求

1. 将完整结果写入 `{output_path}`。
2. 聊天最多返回 5 行，只返回：`完成/阻塞`、输出路径、发现数量、最高严重度、阻断项；不要贴完整报告、完整 JSON、长日志、大表或内部归档路径。
3. JSON 必须包含：

```json
{{
  "slice_id": "{spec['id']}",
  "agent": "{agent_id}",
  "title": "{spec['title']}",
  "status": "completed/blocked",
  "files_read": [],
  "logs": [],
  "coverage_matrix": {{}},
  "findings": [],
  "mechanical_dispositions": [],
  "high_risk_modules": [],
  "blockers": [],
  "summary": {{
    "total_findings": 0,
    "fatal": 0,
    "critical": 0,
    "major": 0,
    "warning": 0,
    "info": 0,
    "highest_severity": "INFO"
  }}
}}
```

finding 字段必须满足最终收敛要求：{_REQUIRED_FINDING_FIELDS}
允许的 `source_type`: {_ALLOWED_SOURCE_TYPES}

**硬停止条件**: 写入 `{output_path}` 后立即停止，不要扩审其他切片。
"""


def build_slice_manifest(review_dir: Path) -> dict:
    by_agent: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    for spec in SLICE_SPECS:
        entry = {
            "id": spec["id"],
            "agent": spec["agent"],
            "title": spec["title"],
            "focus": spec["focus"],
            "prompt_file": str(slice_prompt_path(review_dir, spec)),
            "result_file": str(slice_output_path(review_dir, spec)),
            "read_first": spec["read_first"],
        }
        by_agent[spec["agent"]].append(entry)
    return {
        "schema_version": "1.0",
        "execution_model": "small_slice_subagents_then_three_route_merge",
        "compact_safety": {
            "max_parallel_slice_agents": 4,
            "must_persist_slice_results": True,
            "must_not_fork_full_context": True,
            "must_checkpoint_between_batches": True,
            "chat_output": "short_status_only",
        },
        "model_quality": {
            "principle": "small slices control context; they must not reduce judgement strength",
            "formal_judgement_slices_require": "same_model_as_lead_agent_required",
            "must_inherit_lead_model": True,
            "must_not_override_to_lower_model": True,
            "fast_model_allowed_only_for": [
                "file_mapping",
                "path_inventory",
                "format_or_schema_check",
                "grep_like_lookup",
            ],
            "must_not_downshift_for": [
                "severity_judgement",
                "cross_module_consistency",
                "statistical_validity",
                "high_risk_module_assessment",
                "final_arbitration",
            ],
            "required_overlap_context": [
                "report_summary",
                "conclusion_sections",
                "figure_table_index",
                "mechanical_check_summary",
                "case_manifest",
                "slice_neighbor_dependencies",
            ],
            "lead_global_review_required": True,
        },
        "compact_retry_policy": {
            "required_action": "split_scope_again_before_retry",
            "must_not_retry_same_scope": True,
            "split_axes": ["report_section", "analysis_module", "figure_range", "file_group", "issue_cluster"],
        },
        "slices": [item for group in by_agent.values() for item in group],
        "by_agent": by_agent,
        "merge_outputs": {
            "A": str(review_dir / "agent_results" / "agent_a_result.json"),
            "B": str(review_dir / "agent_results" / "agent_b_result.json"),
            "C": str(review_dir / "agent_results" / "agent_c_result.json"),
        },
    }


def build_convergence_guide(review_dir: Path, precheck: dict) -> str:
    """构造 Lead Auditor 收敛阶段指引"""
    slice_lines = "\n".join(
        f"- `{slice_prompt_path(review_dir, spec)}` → `{slice_output_path(review_dir, spec)}`"
        for spec in SLICE_SPECS
    )
    guide = f"""# 三路收敛审核 — Lead Auditor 收敛指引

## 流程概览

```
┌─────────────────────────────────────────────────────────┐
│ 1. 按 agent_slice_manifest.json 分批启动小切片 Sub-Agent │
│ 2. 每个切片写入 agent_results/slices/*.json              │
│ 3. 用 agent_a/b/c_prompt.md 汇总同路切片为 3 份 JSON       │
│ 4. 运行 convergence_compare.py 做三路收敛                 │
│ 5. 如有分歧，仅对分歧点启动小切片复核                     │
│ 6. 生成最终报告                                           │
└─────────────────────────────────────────────────────────┘
```

## Remote Compact 防护硬规则

- 禁止把一个完整项目交给单个 Sub-Agent 一次性审核。
- 每个切片只读自己的 prompt、指定路径和必要局部证据。
- 每批最多并发 4 个切片；每批结束更新 checkpoint。
- 所有切片完整结果必须落盘到 `agent_results/slices/`，聊天只返回短状态。
- Lead 不直接吞入长报告、长日志、完整清单或大证据；正式审核证据由 subagent 落盘。
- 正式判断型 Sub-Agent 必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini/explore 仅用于文件定位、清单、grep，不做严重度/统计/高风险裁定。
- Lead 最终必须做全局一致性复核：覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块。
- 不要 `fork_context` 复制 leader 大上下文，除非处理极小项目且已在 manifest 中说明原因。
- 如果任一 Sub-Agent 触发 remote compact/context loss，先继续拆分工作再重试，禁止原范围重跑。

## 步骤 1：启动小切片子代理

先读取 `{review_dir / 'agent_prompts' / 'agent_slice_manifest.json'}`。
按以下 prompt 启动小切片 Sub-Agent，建议每批 2-4 个：

{slice_lines}

这是正式审核默认流程；只要进入该脚本，就不再等待用户额外确认“三路”。
但“三路”是收敛口径，不等于启动 3 个大 Sub-Agent。

## 步骤 2：收集切片结果并汇总三路 JSON

所有切片必须先保存到 `agent_results/slices/`。之后分别使用以下汇总 prompt：
- `{review_dir / 'agent_results' / 'agent_a_result.json'}`
- `{review_dir / 'agent_results' / 'agent_b_result.json'}`
- `{review_dir / 'agent_results' / 'agent_c_result.json'}`

汇总 prompt 文件：
- `{review_dir / 'agent_prompts' / 'agent_a_prompt.md'}` → 只汇总 A 路 slice JSON
- `{review_dir / 'agent_prompts' / 'agent_b_prompt.md'}` → 只汇总 B 路 slice JSON
- `{review_dir / 'agent_prompts' / 'agent_c_prompt.md'}` → 只汇总 C 路 slice JSON

## 步骤 3：收敛比对

运行：
```
python convergence_compare.py {review_dir}
```

输出 `{review_dir / 'convergence_report.json'}`，包含：
- 共识问题（3/3 一致）
- 多数一致（2/3）
- 单方发现（1/3）
- 分歧问题（结论矛盾）
- 自动机械检查处置汇总（保留/撤销/降级/升级）

## 步骤 4：迭代收敛

如果共识率 < 95%：
1. 构建问题并集
2. 要求各 Agent 针对他方发现进行回溯验证
3. 重复比对，最多 3 轮

终止条件：
- 共识率 ≥ 95% 且分歧率 < 5%
- 连续两轮无变化
- 已达 3 轮上限

## 步骤 5：仲裁规则

| 一致情况 | 裁决方式 |
|---------|---------|
| 3/3 一致 | 直接采纳 |
| 2/3 一致 | 多数优先，附证据说明少数方为何不成立 |
| 1/1/1 各异 | 回溯 report_text.txt 原文验证后裁决 |

## 最终输出

生成以下文件：
- `final_review_report.md`
- `coverage_matrix.md`
- `fact_check_list.md`
- `unresolved_items.md`（如有分歧）
- `convergence_report.md`（必须含投票表 + 机械检查处置表）
- `{{项目ID}}_audit_report.html`
"""
    return guide


def main():
    if len(sys.argv) < 2:
        print("用法: python launch_convergence_audit.py <review_dir> [--project-dir <project_dir>]")
        sys.exit(1)

    review_dir = Path(sys.argv[1])
    project_dir = None
    if '--project-dir' in sys.argv:
        idx = sys.argv.index('--project-dir')
        if idx + 1 < len(sys.argv):
            project_dir = Path(sys.argv[idx + 1])

    if not review_dir.exists():
        print(f"错误: 审核目录不存在: {review_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  三路收敛审核 Prompt 构造器")
    print("=" * 60)
    print(f"  审核目录: {review_dir}")
    if project_dir:
        print(f"  项目目录: {project_dir}")

    # 校验必要文件
    required_files = ['report_text.txt', 'report_structure.json', 'project_structure.json']
    missing = [f for f in required_files if not (review_dir / f).exists()]
    if missing:
        print(f"❌ 缺少必要文件: {missing}")
        print("   请先运行 auto_audit_pipeline.py 生成预检查结果")
        sys.exit(1)

    # 加载预检查结果
    precheck = load_precheck_results(review_dir)
    report_excerpt = load_report_excerpt(review_dir)

    # 创建输出目录
    prompt_dir = review_dir / 'agent_prompts'
    prompt_dir.mkdir(exist_ok=True)
    slice_prompt_dir = prompt_dir / 'slices'
    slice_prompt_dir.mkdir(exist_ok=True)
    results_dir = review_dir / 'agent_results'
    slice_results_dir = results_dir / 'slices'
    results_dir.mkdir(exist_ok=True)
    slice_results_dir.mkdir(exist_ok=True)

    # 生成小切片 prompt 与 manifest
    for spec in SLICE_SPECS:
        prompt = build_slice_prompt(spec, review_dir, project_dir, precheck, report_excerpt)
        out_path = slice_prompt_path(review_dir, spec)
        out_path.write_text(prompt, encoding='utf-8')
        print(f"  ✅ Slice {spec['id']} prompt: {out_path}")

    slice_manifest = build_slice_manifest(review_dir)
    slice_manifest_path = prompt_dir / 'agent_slice_manifest.json'
    slice_manifest_path.write_text(json.dumps(slice_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  ✅ 小切片清单: {slice_manifest_path}")

    # 生成 3 个 Agent 汇总 prompt
    agents = [
        ('A', _AGENT_A_EMPHASIS),
        ('B', _AGENT_B_EMPHASIS),
        ('C', _AGENT_C_EMPHASIS),
    ]

    for agent_id, emphasis in agents:
        prompt = build_agent_prompt(
            agent_id, emphasis, review_dir, project_dir, precheck, report_excerpt
        )
        out_path = prompt_dir / f'agent_{agent_id.lower()}_prompt.md'
        out_path.write_text(prompt, encoding='utf-8')
        print(f"  ✅ Agent {agent_id} 汇总 prompt: {out_path}")

    # 生成收敛指引
    guide = build_convergence_guide(review_dir, precheck)
    guide_path = prompt_dir / 'convergence_guide.md'
    guide_path.write_text(guide, encoding='utf-8')
    print(f"  ✅ 收敛指引: {guide_path}")

    print(f"\n  📂 输出目录: {prompt_dir}")
    print(f"  📂 小切片 prompt: {slice_prompt_dir}")
    print(f"  📂 结果目录: {results_dir}")
    print(f"  📂 小切片结果目录: {slice_results_dir}")
    print("\n  下一步: 按 agent_slice_manifest.json 分批启动小切片子代理；不要启动 3 个大子代理")
    print("  参考: agent_prompts/convergence_guide.md")


if __name__ == '__main__':
    main()
