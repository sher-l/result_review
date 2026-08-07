#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate framework docs from the canonical policy and command flow."""

from __future__ import annotations

import argparse
from pathlib import Path

from policy_loader import load_policy


DOC_ROOT = Path(__file__).resolve().parents[1]


def _banner(policy: dict, source_files: str) -> str:
    return (
        f"> Generated from `{source_files}`\n"
        f"> Source of truth: `result_review_framework/policy/audit_policy.json`\n"
        f"> Framework version: `{policy['framework_version']}`\n"
        f"> Policy updated at: `{policy['updated_at']}`\n"
        f"> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`\n"
    )


def _command_flow() -> list[tuple[str, str, str]]:
    return [
        ("Precheck", "scripts/auto_audit_pipeline.py", "Extract report/project structure, build case_manifest, run mechanical checks, prepare visual audit assets."),
        ("Guardrails", "scripts/prepare_ai_audit_guardrails.py", "Generate AI execution manifest, prompts, and audit state baseline."),
        ("Slice Agents", "agent_prompts/agent_slice_manifest.json", "Launch small, bounded slice subagents in batches; every slice writes JSON to agent_results/slices/."),
        ("Convergence", "scripts/convergence_compare.py", "Validate slice JSONs, build traceable candidate clusters, and emit arbitration artifacts."),
        ("Prepare Final", "scripts/prepare_audit_finalize.py", "Run local lint/autofix/backfill before the leader seals final_decision.json; never notify or archive."),
        ("Professional Gate", "scripts/validate_professional_contracts.py", "Validate arbitration v2 and the policy-owned professional artifacts; domain observations remain candidates."),
        ("Contract Gate", "scripts/validate_audit_contract.py", "Validate the sealed decision, source hashes, counts, and mode-aware blocking."),
        ("Finalize", "scripts/finalize_audit.py", "Verify sealed artifacts without rewriting them, publish HTML, send at most once, and auto archive."),
        ("Archive Fallback", "scripts/archive_reviewed_project.py", "Manual recovery command for already-published review dirs when archive state must be repaired."),
    ]


def _appendix_policy_lines(policy: dict) -> list[str]:
    appendix_policy = policy.get("report_appendix_policy", {})
    if not appendix_policy:
        return []
    markers = appendix_policy.get("boilerplate_markers", [])
    marker_text = " / ".join(markers) if markers else "公司介绍 / 服务领域 / 联系我们"
    return [
        "## 报告附页口径",
        "",
        "- 参考文献后的公司宣传页默认视为交付 boilerplate，不纳入正式审核范围。",
        f"- 默认识别标记：{marker_text}",
        "- 只有当这些内容出现在参考文献前的正式正文中，或污染编号章节时，才升级为实质问题。",
        "",
    ]


def _lesson_bank_policy_lines(policy: dict, *, compact: bool = False) -> list[str]:
    lesson_policy = policy.get("lesson_bank_policy", {})
    if not lesson_policy:
        return []
    rule_policy = lesson_policy.get("rule_suggestion_policy", {})

    if compact:
        lines = [
            "## 错题集闭环",
            "",
            "- 审核前读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把相同或相近内容列为重点复核项。",
            "- 审核后将典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议沉淀到 `lessons/`。",
            "- 错题集只提供风险提示；后续项目必须结合当前证据独立判断，不能机械套用历史结论。",
        ]
        if rule_policy.get("apply_when_actionable"):
            lines.append("- 若规则建议已明确且证据充分，直接同步更新对应 `patterns/`、索引或政策文档，不只留待办。")
        lines.append("")
        return lines

    fields = " / ".join(lesson_policy.get("required_entry_fields", []))
    targets = "、".join(lesson_policy.get("update_targets", []))
    lines = [
        "## 错题集闭环",
        "",
        "- 审核前必须读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把命中的相同或相近内容列为重点复核项。",
        f"- 审核后必须把本次典型错误点沉淀到 `lessons/`；建议更新位置：{targets}。",
        f"- 单条错题至少记录：{fields}。",
        "- 后续审核其他项目时，错题集只作为风险提示；必须结合当前项目证据独立核验，不能机械套用历史结论。",
    ]
    if rule_policy.get("apply_when_actionable"):
        lines.append("- 错题集中的规则建议如果已可执行，必须直接更新对应模式库、索引或政策文档；证据不足时才标注待复核。")
    lines.append("")
    return lines


def _code_delivery_policy_lines(policy: dict) -> list[str]:
    code_policy = policy.get("code_delivery_policy", {})
    if not code_policy:
        return []
    return [
        "## 代码交付严重度口径",
        "",
        f"- 单纯未交付代码 / 未发现代码文件 / 代码不可复现风险：`{code_policy.get('standalone_no_code_severity', 'WARNING')}`。",
        "- 不得仅因无代码把问题升级为 CRITICAL，也不得把无代码作为唯一不通过原因。",
        "- 若同时存在错误项目路径、方法参数矛盾、核心统计错误、结论无证据或数据链断裂，应按这些实质问题独立升级。",
        "",
    ]


def _figure_delivery_policy_lines(policy: dict) -> list[str]:
    delivery_policy = policy.get("figure_delivery_policy", {})
    if not delivery_policy:
        return []
    return [
        "## 图件交付格式",
        "",
        f"- {delivery_policy.get('format_rule', '结果图件可以仅交付可渲染 PDF。')}",
        "",
    ]


def _structured_contract_policy_lines(policy: dict, *, compact: bool = False) -> list[str]:
    contract = policy.get("audit_contract_policy", {})
    visual = policy.get("visual_closure_policy", {})
    professional = policy.get("professional_contract_policy", {})
    notification = policy.get("notification_idempotency_policy", {})
    binding = policy.get("framework_binding_policy", {})
    if not contract:
        return []
    lines = ["## 结构化完成契约", ""]
    lines.extend(
        [
            f"- `final_decision.json` 是分数、结论和发布决定的唯一来源；当前门禁模式：`{contract.get('mode', 'enforce')}`。",
            "- `prepare_audit_finalize.py` 只能在封存前修复报告；正式 finalize 不得改写已确认 source。",
            f"- 视觉闭环写入 `{visual.get('result_json', 'visual_audit_result.json')}`，所有范围内资产必须守恒且无未入账项。",
            "- `formal_delivery_manifest.json` 必须绑定封存后的 `final_decision.json`、最终 Markdown、HTML 与视觉闭环；任一文件缺失、变化或未完成都不得发送或归档。",
            f"- 完成通知收据写入 `{notification.get('receipt_json', 'completion_notification_receipt.json')}`；匹配的 sent 收据禁止重复发送。",
            f"- `case_manifest.json` 与 `ai_execution_manifest.json` 必须绑定当前 policy 原始字节的 `{binding.get('hash_algorithm', 'sha256')}`；禁止静默换版。",
            "- 测试、回归、shadow replay、smoke 和 dry-run 禁止任何真实通知网络调用。",
        ]
    )
    if not compact:
        artifacts = professional.get("structured_artifacts", {})
        if artifacts:
            lines.append("- 专业契约产物：" + "、".join(f"`{name}`" for name in artifacts.values()) + "。")
        lines.append(
            f"- 专业契约验证写入 `{professional.get('validation_json', 'professional_contract_validation.json')}`；shadow 只暴露 would-block，enforce 才阻断。"
        )
        lines.append("- `leader_confirmed` 后，每个正式 F-ID 必须唯一绑定 retained canonical finding；reject/revoked 原始发现不得进入正式问题链。")
        lines.append("- 相同 `error_mechanism + repair_path` 即使定位不同也必须归并；保留为独立问题时必须提交差异维度和双方独立证据。")
        lines.append(f"- 旧项目迁移只能显式使用 `{binding.get('legacy_rebuild_flag', '--rebuild-policy-binding')}`，并保留旧版本与旧 SHA 记录。")
        lines.append("- 专业机械检查只生成 candidate；严重度、实际污染和科学结论由仲裁决定。")
    lines.append("")
    return lines




def _subagent_quality_policy_lines(policy: dict) -> list[str]:
    compact_policy = policy.get("subagent_compact_policy", {})
    model_policy = compact_policy.get("model_quality_policy", {})
    overlap_policy = compact_policy.get("overlap_and_global_review", {})
    subagent_budget = compact_policy.get("subagent_chat_return_budget", {})
    final_budget = compact_policy.get("leader_final_reply_budget", {})
    if not model_policy and not overlap_policy:
        return []
    subagent_max_lines = subagent_budget.get("max_lines", 5)
    final_max_lines = final_budget.get("max_lines", 8)
    return [
        "## Sub-Agent 质量门禁",
        "",
        "- 正式审核默认采用“Lead 监工/整合 + Sub-Agent 分片审核”模式；Lead 不直接吞入长报告、长日志、完整文件清单或大证据。",
        "- Sub-Agent 必须把完整证据落盘，Lead 只读取短状态、证据路径、计数和最终必要片段，避免 leader 触发 remote compact。",
        f"- Sub-Agent 聊天回传最多 {subagent_max_lines} 行，只允许状态、输出路径、发现数量、最高严重度和阻断项；完整 Markdown/JSON/长日志/大表必须落盘，不得贴回主线程。",
        f"- Lead 最终回复最多 {final_max_lines} 行；正式审核完成通知只保留状态、时间、项目、报告文件、审核结果和问题统计，不贴任务类型、任务名称、摘要、workspace、内部路径或监督 JSON 元数据。",
        "- 小切片只用于控制上下文和防 remote compact，不允许降低正式审核判断能力；若子代理触发 remote compact/context loss，必须继续拆分切片后重试，禁止原范围重跑。",
        "- 正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini 只用于文件定位、清单、schema、grep 类任务。",
        "- 严重度、跨模块一致性、统计适用性、高风险模块和最终仲裁不得由弱模型单独裁定。",
        "- 判断型切片必须保留重叠上下文：摘要/结论、Figure/Table 索引、机械检查摘要、case_manifest、相邻依赖模块。",
        "- Lead 最终必须复核覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块。",
        "",
    ]


def build_readme(policy: dict) -> str:
    default_lane = policy.get("review_lane_policy", {}).get("default_lane", "strict")
    lines = [
        "# 结果审核框架",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 当前主线",
        "",
        "正式审核只认下面这条流水线：",
        "",
    ]
    for index, (title, script_name, summary) in enumerate(_command_flow(), start=1):
        lines.append(f"{index}. `{script_name}`")
        lines.append(f"   {title}: {summary}")
    lines.extend(_appendix_policy_lines(policy))
    lines.extend(_figure_delivery_policy_lines(policy))
    lines.extend(_code_delivery_policy_lines(policy))
    lines.extend(_structured_contract_policy_lines(policy))
    lines.extend(_subagent_quality_policy_lines(policy))
    lines.extend(
        [
            "",
            "## 核心约束",
            "",
            "- 统一事实底座：每个项目必须生成 `case_manifest.json`。",
            "- 统一事件留痕：每个阶段都写 `review_event_log.jsonl`。",
            "- 统一问题主键：每条 finding 必须带 `finding_key`。",
            "- 统一收敛出口：三路收敛必须产出 `convergence_report.*` 和 `arbitration_queue.json`。",
            "- 统一收口：先通过 `prepare_audit_finalize.py` 完成本地修复并由 Lead 封存 `final_decision.json`，再运行 `finalize_audit.py`。",
            "- 强制自动归档：`finalize_audit.py` 在 HTML 发布成功后必须移动项目到 `raw/已AI审核一次`；不再支持 `--no-auto-archive`，归档失败则 finalize 失败。",
            "",
        ]
    )
    lines.extend(_lesson_bank_policy_lines(policy))
    lines.extend(
        [
            "## 视觉审核",
            "",
        f"- 当前默认：`review_lane={default_lane}`。",
        "- `review_lane=standard`：仅高风险图件或机器预筛标红图件进入 AI逐图复核。",
        "- `review_lane=strict`：所有非装饰图进入 AI逐图复核。",
        "- 图件交付格式：PDF-only 可接受；PNG/JPG-only 且无 PDF 时才按格式缺失提示。",
        "- 机器预筛当前覆盖：完全重复图、OCR 检出的外项目编号、明显错图、疑似字体风格不一致。",
            "",
            "## 必交付件",
            "",
        ]
    )
    for filename in policy["required_final_files"]:
        lines.append(f"- `{filename}`")
    lines.extend(
        [
            "- `<project_id>_audit_report.html`",
            "",
            "## 参考文档",
            "",
            "- `README.md` / `AI_INDEX.md`：入口与路径说明",
            "- `guides/QUICKSTART.md`：执行步骤",
            "- `guides/QUICK_REFERENCE.md`：速查表",
            "- `guides/IMAGE_ANALYSIS_ROADMAP.md`：视觉审核演进方向",
        ]
    )
    return "\n".join(lines) + "\n"


def build_ai_index(policy: dict) -> str:
    commands = _command_flow()
    lines = [
        "# AI 使用索引",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## AI 审核员先读什么",
        "",
        "1. `policy/audit_policy.json`",
        "2. `README.md`",
        "3. `MASTER_PROMPT.md`",
        "4. `CORE_RULES.md`",
        "",
        "## 正式审核路径",
        "",
    ]
    for index, (_, script_name, summary) in enumerate(commands, start=1):
        lines.append(f"{index}. `{script_name}`")
        lines.append(f"   {summary}")
    lines.extend(_appendix_policy_lines(policy))
    lines.extend(_figure_delivery_policy_lines(policy))
    lines.extend(_code_delivery_policy_lines(policy))
    lines.extend(_structured_contract_policy_lines(policy, compact=True))
    lines.extend(_subagent_quality_policy_lines(policy))
    lines.extend(
        [
            "",
            "## AI 输出协议",
            "",
            "- finding 需要完整结构化字段，并且必须带 `finding_key`。",
            "- `mechanical_check_result.json` 只能作为候选问题，不能直接当最终结论。",
            "- 高风险模块必须拆成 4 个维度判断：`module_exists` / `evidence_sufficient` / `reproducible` / `conclusion_not_overstated`。",
            "- `CRITICAL/FATAL` finding 如果证据字段不完整，必须进入 `arbitration_queue.json`。",
            "",
        ]
    )
    lines.extend(_lesson_bank_policy_lines(policy, compact=True))
    lines.extend(
        [
            "## 发布与归档",
            "",
            "- 发布状态写入 `case_manifest.json.publish_status`。",
            "- 归档状态写入 `case_manifest.json.archive_approved` 与 `archived_at`。",
            "- `ensure_review_html.py` 只负责 HTML 生成，不单独承担归档。",
            "- `finalize_audit.py` 只验证封存产物，不再自动改写最终报告；发布成功后自动调用 `archive_reviewed_project.py`。",
            "- `archive_reviewed_project.py` 仅作为正式 finalize 后的手动回补命令；没有当前正式交付清单、学习产物和匹配的 sent 通知收据时必须拒绝归档。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_quickstart(policy: dict) -> str:
    default_lane = policy.get("review_lane_policy", {}).get("default_lane", "strict")
    lines = [
        "# 审核框架 Quickstart",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 1. 运行预检查",
        "",
        "```powershell",
        "python result_review_framework/scripts/auto_audit_pipeline.py \"raw/待审核/<项目目录>\" --project-type <类型>",
        "```",
        "",
        "输出：`report_text.txt`、`report_structure.json`、`project_structure.json`、`mechanical_check_result.json`、`case_manifest.json`、`visual_audit_checklist.json`、`visual_prefilter.json`。",
        "",
        "## 2. 生成 AI 围栏",
        "",
        "```powershell",
        "python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`ai_execution_manifest.json`、`audit_state.json`、`agent_prompts/*`。",
        "",
        "## 3. 收集三路 agent 结果并收敛",
        "",
        "先读取 `agent_prompts/agent_slice_manifest.json`，按 `agent_prompts/slices/*.md` 分批启动小切片 subagent（每批 2-4 个）。",
        "",
        "硬要求：",
        "- Lead 是监工/整合者，不是全文审核执行者；不得在主线程直接展开长报告、长日志、完整清单或大证据。",
        "- 正式审核证据由 subagent 落盘，Lead 只读取短状态、证据路径、计数和最终必要片段，防止 leader 上下文被塞满。",
        "- Sub-Agent 聊天回传最多 5 行：状态、输出路径、发现数量、最高严重度、阻断项；完整报告、JSON、长日志或大表只写文件。",
        "- Lead 最终回复最多 8 行；正式审核完成通知只保留状态、时间、项目、报告文件、审核结果和问题统计。",
        "- 不要 fork/copy leader 的完整上下文给子代理。",
        "- 小切片不等于弱模型：正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high。",
        "- fast/mini 只用于文件定位、清单、schema、grep；不得单独裁定严重度、统计适用性、高风险模块或最终仲裁。",
        "- 每个判断型切片必须保留重叠上下文：摘要/结论、Figure/Table 索引、机械检查摘要、case_manifest、相邻依赖模块。",
        "- 每个切片只读自己的 prompt、指定路径和必要局部证据；若触发 remote compact/context loss，必须按章节、模块、图号范围、文件组或问题簇继续拆分后重试。",
        "- 每个切片必须把完整 JSON 写入 `agent_results/slices/`，聊天只返回状态、路径、数量和 blocker。",
        "- 每批完成后将状态写入 `review_event_log.jsonl`，并更新项目内 `subagent_supervision_summary.json`。",
        "",
        "切片全部落盘后，Lead 先复核覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块，再运行收敛：",
        "",
        "```powershell",
        "python result_review_framework/scripts/convergence_compare.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`convergence_report.json`、`convergence_report.md`、`arbitration_queue.json`。",
        "",
        "## 4. 准备、封存并完成最终交付",
        "",
        "```powershell",
        "python result_review_framework/scripts/prepare_audit_finalize.py result_review_report/<项目编号>",
        "# Lead 确认并写入 final_decision.json 后：",
        "python result_review_framework/scripts/validate_professional_contracts.py result_review_report/<项目编号>",
        "python result_review_framework/scripts/validate_audit_contract.py result_review_report/<项目编号>",
        "python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`final_review_report.md`、`final_decision.json`、`professional_contract_validation.json`、`audit_contract_validation.json`、`completion_notification_receipt.json`、`audit_state.json`、`<项目编号>_audit_report.html`，并默认移动项目到已审核目录。",
        "",
        "## 5. 归档硬门禁",
        "",
        "`finalize_audit.py` 不再支持只发布不移动。HTML 发布成功后必须自动移动到 `raw/已AI审核一次`，否则本次 finalize 失败。",
        "",
        "## 6. 错题集闭环",
        "",
        "- 审核前读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，将相同或相近历史错误列为重点复核项。",
        "- 审核后把本次典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议写回 `lessons/`。",
        "- 规则建议若已明确且证据充分，直接同步到对应 `patterns/`、索引或政策文档；证据不足才标注待复核。",
        "- 历史错题只提示风险；必须结合当前项目证据独立判断，不能机械套用历史结论。",
        "",
        "## 7. 代码交付严重度口径",
        "",
        "- 单纯未交付代码 / 未发现代码文件 / 代码不可复现风险只按 WARNING 记录。",
        "- 不得仅因无代码升级为 CRITICAL，也不得把无代码作为唯一不通过原因。",
        "- 错误项目路径、方法参数矛盾、核心统计错误、结论无证据或数据链断裂按实质问题独立升级。",
        "",
        "## 关键规则",
        "",
        f"- 默认 `{default_lane}` lane；只有显式选择时才切换其他 lane。",
        "- 不要在封存后修改报告；修复必须通过 `prepare_audit_finalize.py` 在 `final_decision.json` 确认前完成。",
        "- 旧项目若缺少 policy SHA，只能显式运行 `prepare_ai_audit_guardrails.py <review_dir> --rebuild-policy-binding` 后重新生成围栏；不得自动补写或静默换版。",
        "- HTML 生成失败时，不允许归档。",
        "- finalize 成功必须同时满足 `publish_status=success` 且 `archived_at` 已写入。",
        "- 不允许使用 `--no-auto-archive`；如归档失败，修正 manifest/源路径后重跑 `finalize_audit.py` 或 `archive_reviewed_project.py --approve`。",
        "- 参考文献后的公司宣传页默认不纳入正式审核；不要因为宣传附页里的“分子对接/分子动力学”等词触发问题。",
    ]
    return "\n".join(lines) + "\n"


def build_quick_reference(policy: dict) -> str:
    required_fields = ", ".join(policy["finding_evidence_policy"]["required_fields"])
    source_types = ", ".join(policy["finding_evidence_policy"]["allowed_source_types"])
    lines = [
        "# 审核框架 Quick Reference",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 主命令",
        "",
        "| 阶段 | 命令 |",
        "|---|---|",
        "| Precheck | `python result_review_framework/scripts/auto_audit_pipeline.py <project_dir> --project-type <类型>`（默认 strict） |",
        "| Guardrails | `python result_review_framework/scripts/prepare_ai_audit_guardrails.py <review_dir>` |",
        "| Convergence | `python result_review_framework/scripts/convergence_compare.py <review_dir>` |",
        "| Prepare Final | `python result_review_framework/scripts/prepare_audit_finalize.py <review_dir>` |",
        "| Professional Gate | `python result_review_framework/scripts/validate_professional_contracts.py <review_dir>` |",
        "| Contract Gate | `python result_review_framework/scripts/validate_audit_contract.py <review_dir>` |",
        "| Finalize | `python result_review_framework/scripts/finalize_audit.py <review_dir>` |",
        "| Archive Fallback | `python result_review_framework/scripts/archive_reviewed_project.py <review_dir> --approve` |",
        "",
        "## Review Lane",
        "",
        "| Lane | 规则 |",
        "|---|---|",
        "| `standard` | 仅高风险图件或机器预筛标红图件进入 AI复核 |",
        "| `strict` | 所有非装饰图件都进入 AI复核 |",
        "",
        "## 图件格式",
        "",
        "- PDF-only 可接受，不再因缺少 PNG 单独记问题。",
        "- PNG/JPG-only 且无 PDF 时，记录交付规范 WARNING 或说明例外。",
        "",
        "## Sub-Agent 质量门禁",
        "",
        "- 正式审核默认 Lead 只做监工/整合；subagent 执行分片审核并落盘证据。",
        "- Lead 不直接吞入长报告、长日志、完整清单或大证据，避免 leader 触发 remote compact。",
        "- Sub-Agent 聊天回传最多 5 行；完整 Markdown/JSON/长日志/大表只写文件并回路径。",
        "- Lead 最终回复最多 8 行；正式通知不贴摘要、内部路径、workspace 或监督 JSON 元数据。",
        "- 小切片只控上下文，不降低模型判断能力；若子代理触发 remote compact/context loss，必须继续拆分切片后重试，禁止原范围重跑。",
        "- 正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini 只做定位/清单/grep/schema。",
        "- Lead 必须做全局一致性复核。",
        "",
        "## 报告附页口径",
        "",
        "- 参考文献后的公司宣传页默认视为 boilerplate，不纳入正式审核范围。",
        "- 只有当这些内容出现在参考文献前或污染编号正文章节时，才升级为问题。",
        "",
        "## Finding Contract",
        "",
        f"- 必填字段：{required_fields}",
        f"- `source_type` 允许值：{source_types}",
        "- `finding_key` 由 `dimension + rule + source_path + locator + quote_or_value` 稳定生成。",
        "- 高等级 finding 证据不完整时，必须进入 `arbitration_queue.json`。",
        "",
        "## 最终文件",
        "",
    ]
    for filename in policy["required_final_files"]:
        lines.append(f"- `{filename}`")
    lines.extend(
        [
            "- `<project_id>_audit_report.html`",
            "",
            "## 发布/归档状态",
            "",
            "- `publish_status`: `pending | success | failed`",
            "- `archive_approved`: `true | false`",
            "- `archived_at`: 必须在 `finalize_audit.py` 自动归档成功后写入。",
            "- `--no-auto-archive`: 已禁用；使用该参数会失败。",
            "",
        ]
    )
    lines.extend(_lesson_bank_policy_lines(policy, compact=True))
    lines.extend(_code_delivery_policy_lines(policy))
    lines.extend(_structured_contract_policy_lines(policy, compact=True))
    return "\n".join(lines) + "\n"


def build_image_analysis_roadmap(policy: dict) -> str:
    default_lane = policy.get("review_lane_policy", {}).get("default_lane", "strict")
    lines = [
        "# 图像审核路线图",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 当前已实现",
        "",
        "- `visual_prefilter.json`：视觉预筛结构化产物。",
        "- `visual_audit_result.json`：资产守恒、跳过/不支持理由和高风险派生证据的最终闭环。",
        "- 完全重复图检测：基于文件 SHA1。",
            "- OCR 项目编号失配检测：可选依赖 `pytesseract`。",
            "- 明显错图检测：用轻量视觉家族分类拦截“图表位被文字页替代”类错误。",
            "- 字体风格不一致检测：基于 OCR 文本块和字形统计做启发式预警。",
        f"- `review_lane`：`standard` / `strict` 双车道，当前默认 `{default_lane}`。",
        "",
        "## 后续增强建议",
        "",
        "1. 感知哈希或向量相似度，覆盖裁剪后重复图。",
        "2. 图注 OCR 与正文自动对齐，提升跨项目污染检出率。",
        "3. 图表类型识别从规则法升级为轻量模型。",
        "4. 把 `visual_prefilter` 风险标签回灌到 mechanical checks 和最终报告模板。",
        "",
        "## 使用原则",
        "",
        "- 机器预筛只负责排序和标红，不直接替代最终裁定。",
        "- `strict` 项目仍保留全量 AI看图。",
        "- 图件格式不要求 PDF+PNG 双格式；PDF-only 可接受，PNG/JPG-only 需说明或补 PDF。",
    ]
    return "\n".join(lines) + "\n"


def build_documents(policy: dict) -> dict[Path, str]:
    return {
        DOC_ROOT / "README.md": build_readme(policy),
        DOC_ROOT / "AI_INDEX.md": build_ai_index(policy),
        DOC_ROOT / "guides" / "QUICKSTART.md": build_quickstart(policy),
        DOC_ROOT / "guides" / "QUICK_REFERENCE.md": build_quick_reference(policy),
        DOC_ROOT / "guides" / "IMAGE_ANALYSIS_ROADMAP.md": build_image_analysis_roadmap(policy),
    }


def write_documents(check_only: bool = False) -> list[Path]:
    policy = load_policy()
    documents = build_documents(policy)
    mismatches = []
    for path, content in documents.items():
        if check_only:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            if existing != content:
                mismatches.append(path)
            continue
        path.write_text(content, encoding="utf-8")
    return mismatches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate policy-derived framework docs.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated docs differ from files on disk.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mismatches = write_documents(check_only=args.check)
    if args.check and mismatches:
        for path in mismatches:
            print(f"Doc drift: {path}")
        return 1
    if not args.check:
        for path in build_documents(load_policy()):
            print(f"Updated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
