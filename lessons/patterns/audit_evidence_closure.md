# 模式：审核证据闭环

> 严重性：MAJOR ～ FATAL  
> 案例：26YLM139F

## P18：身份层、视觉层与可复现性层不能互相替代

**描述**：审核对象可同时有聚合键、底层原始 ID、图件处理状态、派生结果和代码工件。任一层的存在或缺失都不能替代另一层的证据结论。

**信号**：

- 一个 finding_key 对应多个 raw_finding_ids，但仲裁只写一条 disposition。
- 资产处于 unsupported/skipped，却没有可定位的替代审核记录。
- total_code_files=0 被写成“结果不存在”，或 PDF/图件被写成“代码级可复现”。
- 高风险图件缺少唯一对象标签，正文与目录却出现互相冲突的实体。

**检测**：

1. 仲裁身份闭环：convergence.classified 中的 raw_finding_ids 应等于 arbitration.raw_dispositions 的 raw_finding_id 集合。
2. 视觉闭环：needs_audit 资产必须有 completed review，或 alternative evidence（reference、reviewer、time、conclusion），或 approved waiver。
3. 可复现性边界：结果存在性、证据充分性、代码可复现性分别判定；高风险重跑联合检查脚本、参数、输入、中间工件、日志。
4. 机制实体闭环：receptor、ligand、complex、conclusion 在正文、图件与交付目录中唯一且一致。

**阻断条件**：

- raw-ID coverage 不相等；
- 高风险图件没有审核、替代证据或批准豁免；
- 将无代码结论越界为“无结果”，或将派生图越界为可重跑证明；
- 关键机制实体发生直接冲突或无法定位唯一体系。

**案例**：26YLM139F 将 18 条提案处置按收敛真源展开为 21 条底层 raw disposition；严格视觉通道对 32 个未自动解析资产保留直接 PDF 目视证据；全项目无代码被限定为不可代码级验证；HLA-DMB-quercetin/OLR1 冲突因无唯一 FEL 对象标识被判为 FATAL。
