# 26YBB035F reusable audit lessons

## GEO 外项目路径参与核心读取
- Trigger: 代码读取路径含非当前项目编号，且该数据集支撑报告核心单细胞/空间/验证结论。
- Rule: 不应仅作为路径风格问题；若原始输入不在当前交付包内，至少 MAJOR；若支撑核心结论且来自外项目路径，升级 CRITICAL。
- Reminder: B03/C01 切片必须同时核对 report_text 数据来源、rawdata、代码读取路径和 project_id。

## 不同组别图件完全重复
- Trigger: visual_prefilter duplicate 图对应不同组别、疾病状态、时间点或实验条件。
- Rule: 不能按“图存在”通过；若影响核心机制/分组结论，升级 CRITICAL。
- Reminder: B02 视觉切片需把 duplicate 预筛和 DOCX 图注语义绑定。

## 验证队列内重新寻找 cutpoint
- Trigger: 外部验证队列再次调用 surv_cutpoint/maxstat/最佳阈值寻优。
- Rule: 这不是训练阈值外部验证，只能作为探索性队列内分层；强验证结论至少 MAJOR。
- Reminder: C02 统计切片检查训练阈值是否固定应用到外部队列。

## 高风险模块 PDF-only
- Trigger: Cottrazm/RCTD/TF/MISTy/KNK 等机制模块仅有 PDF/PNG，缺对象、结构化表和统计输出。
- Rule: 不足以支撑机制强结论；至少 MAJOR，必要时作为 proof gap。
- Reminder: A02/C03 需逐项给证据等级 A/B/C。
