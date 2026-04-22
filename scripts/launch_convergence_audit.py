#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
三路收敛审核 Prompt 自动构造器

功能：基于预检查结果和框架文档，为 3 个独立 Sub-Agent 生成完整的审核 prompt。
解决核心问题：子代理不读文档就开始审核。此脚本确保每个子代理 prompt 包含所有必要上下文。

用法：
    python launch_convergence_audit.py <review_dir> [--project-dir <project_dir>]

输出：
    <review_dir>/agent_prompts/
        agent_a_prompt.md  — Agent A: D1(覆盖) + D5(证据)
        agent_b_prompt.md  — Agent B: D2(事实) + D3(一致性)
        agent_c_prompt.md  — Agent C: D6(方法-代码) + 统计判断
        convergence_guide.md — Lead Auditor 收敛阶段指引
"""

import json
import sys
from pathlib import Path
from datetime import datetime

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
- 本次任务默认属于“正式审核”，三路独立审核为必做步骤，不等待额外授权
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
      "finding_key": "fk:xxxxxxxxxxxxxxxx",
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
      "quote_or_value": "引用原句、标签或关键数值"
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
      "module": "molecular_docking/md/virtual_knockout",
      "module_exists": true/false,
      "evidence_sufficient": true/false,
      "reproducible": true/false,
      "conclusion_not_overstated": true/false,
      "notes": "鍒嗗眰鍒ゆ柇鐨勭煭璇存槑"
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


def load_report_excerpt(review_dir: Path, max_lines: int = 500) -> str:
    """加载报告文本（截取前 N 行作为概览，完整文本由子代理自行读取）"""
    report_path = review_dir / 'report_text.txt'
    if not report_path.exists():
        return "(报告文本不可用)"
    lines = report_path.read_text(encoding='utf-8').splitlines()
    if len(lines) <= max_lines:
        return '\n'.join(lines)
    return '\n'.join(lines[:max_lines]) + f"\n\n... (共 {len(lines)} 行，以上为前 {max_lines} 行。请自行读取完整文件)"


def build_agent_prompt(
    agent_id: str,
    emphasis: str,
    review_dir: Path,
    project_dir: Path | None,
    precheck: dict,
    report_excerpt: str,
) -> str:
    """构造单个 Sub-Agent 的完整 prompt"""

    # 文件路径提示
    paths_section = f"""
## 文件路径

审核目录: `{review_dir}`
{f'项目目录: `{project_dir}`' if project_dir else '项目目录: (未指定)'}

### 你需要读取的文件（按优先级）
1. `{review_dir / 'report_text.txt'}` — 报告全文（含 [IMAGE: xxx] 标记）
2. `{review_dir / 'report_structure.json'}` — 报告结构索引
3. `{review_dir / 'project_structure.json'}` — 项目结构索引
4. `{review_dir / 'mechanical_check_result.json'}` — 机械检查结果
5. `{review_dir / 'figure_audit.md'}` — 视觉审核清单（逐图检查用）
6. `{review_dir / 'visual_audit_checklist.json'}` — 图片审核详细清单
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

**你必须使用 view_image 工具检查每张需审核的图片。**

读取 `{review_dir / 'figure_audit.md'}` 获取每张图片的检查项清单。
对每张图片至少检查：
1. 文件可渲染（无空白/截断/损坏）
2. 标题/副标题与本项目一致（无 copy-paste 残留）
3. 轴标签存在且可读
4. 图例存在且标签正确

图片路径格式: `{review_dir / 'images' / 'image_XXX.png'}`
"""

    # 组装完整 prompt
    prompt = f"""# 生物信息学报告审核 — Sub-Agent {agent_id}

**角色**: 你是生物信息学数据分析报告的高级审核员（Sub-Agent {agent_id}）。
**独立性**: 你是三路独立审核中的一路。不要参考其他 Agent 的结论。独立完成全面审核后输出结果。
**语言**: 使用中文输出。
**注意**: 这是正式审核，不是草稿或初筛。你必须完成完整双轮审核，并对机械检查误报做裁决。

{_CORE_RULES_SUMMARY}

{emphasis}

{_DOUBLE_ROUND_INSTRUCTION}

{paths_section}

{precheck_section}

{visual_instruction}

{_OUTPUT_FORMAT}

## 报告文本概览

以下是报告前 500 行。如不完整，请自行读取 report_text.txt 完整文件。

```
{report_excerpt}
```

---

**开始审核。请严格按照双轮流程执行，输出 JSON 格式结果。**
"""
    return prompt


def build_convergence_guide(review_dir: Path, precheck: dict) -> str:
    """构造 Lead Auditor 收敛阶段指引"""
    guide = f"""# 三路收敛审核 — Lead Auditor 收敛指引

## 流程概览

```
┌──────────────────────────────────────────────┐
│ 1. 启动 3 个子代理（使用 agent_prompts/ 中的 prompt）│
│ 2. 收集 3 份 JSON 审核结果                        │
│ 3. 运行收敛比对脚本 convergence_compare.py        │
│ 4. 如有分歧，启动迭代收敛（最多 3 轮）             │
│ 5. 生成最终报告                                   │
└──────────────────────────────────────────────┘
```

## 步骤 1：启动子代理

分别用以下 prompt 文件启动 3 个独立子代理：
- `{review_dir / 'agent_prompts' / 'agent_a_prompt.md'}` → Agent A (D1+D5)
- `{review_dir / 'agent_prompts' / 'agent_b_prompt.md'}` → Agent B (D2+D3)
- `{review_dir / 'agent_prompts' / 'agent_c_prompt.md'}` → Agent C (D6+统计)

使用 `runSubagent` 工具，将 prompt 内容作为任务描述传入。
这是正式审核默认流程；只要进入该脚本，就不再等待用户额外确认“三路”。

## 步骤 2：收集结果

每个子代理返回 JSON，保存为：
- `{review_dir / 'agent_results' / 'agent_a_result.json'}`
- `{review_dir / 'agent_results' / 'agent_b_result.json'}`
- `{review_dir / 'agent_results' / 'agent_c_result.json'}`

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

    # 生成 3 个 Agent prompt
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
        print(f"  ✅ Agent {agent_id} prompt: {out_path}")

    # 生成收敛指引
    guide = build_convergence_guide(review_dir, precheck)
    guide_path = prompt_dir / 'convergence_guide.md'
    guide_path.write_text(guide, encoding='utf-8')
    print(f"  ✅ 收敛指引: {guide_path}")

    # 创建 agent_results 目录
    (review_dir / 'agent_results').mkdir(exist_ok=True)

    print(f"\n  📂 输出目录: {prompt_dir}")
    print(f"  📂 结果目录: {review_dir / 'agent_results'}")
    print("\n  下一步: 使用 runSubagent 启动 3 个独立审核子代理")
    print("  参考: agent_prompts/convergence_guide.md")


if __name__ == '__main__':
    main()
