# LESSONS_LEARNED_26YLM139F

来源：result_review_report/26YLM139F_reaudit_20260730/26YLM139F 的正式仲裁决议、视觉审核、三路原始结果和机械检查。

## L01：仲裁覆盖必须使用底层 raw ID

- finding_key 是聚合键，不是 coverage 身份；唯一真源为 convergence_report.json.classified 中的 raw_finding_ids。
- 构造时按键展开到底层 raw；一个键映射多个 raw 时，为每个 raw 写 disposition，并保持单源 canonical 或显式 merge。
- 阻断规则：expected_raw_ids 与 actual_raw_ids 不相等时不得写入 leader_confirmed。

## L02：严格视觉审核必须闭环到证据对象

- unsupported、skipped 表达处理状态，不能表达审核结论。
- 高风险资产必须有完成审核，或有包含来源、审核人、时间和结论的替代直接证据/批准豁免。
- 图件结论应检查可读性、正文锚点、时间轴/单位、唯一对象标签及对核心结论的影响。

## L03：无代码的结论边界

- 无代码可支持“不可代码级核验/不可独立重跑”，不能单独支持“结果不存在”。
- 结果存在性、证据充分性、代码级可复现性必须独立记录。
- 高风险计算需要脚本或命令、版本与参数、输入、关键中间工件和运行日志的联合证据。

## L04：高风险机制结论须有实体链

- 对接、MD、FEL 等结论建立“受体—配体—复合物—结论”四元组。
- 任一跨正文、图件、目录的实体冲突，或图件不标唯一体系，均不得以趋势图支撑机制性结论。

可复用模式见 patterns/audit_evidence_closure.md。
