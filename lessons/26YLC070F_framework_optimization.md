# 26YLC070F framework_optimization_notes

## 结论

本项目暴露的可复用框架改进点为：外项目主动读取自动升级、GEO三方闭合矩阵、机器学习验证集选模/cutoff泄漏检测、高风险模块结构化证据门、文本病种残留与代码残留联动。

## 建议加严的政策 / 检查 / subagent prompt

| 改进项 | 应加严位置 | 当前问题 | 建议改法 | 是否可复用 |
|---|---|---|---|---|
| 外项目主动读取CRITICAL门 | mechanical checker + B03数据残留prompt | 当前机械项主要提示GSE，项目ID主动读取需要AI仲裁后发现 | 静态扫描项目ID正则 `\d{2}_[0-9A-Z]+F` 与 readRDS/load/read.csv 同行或近邻，非注释则CRITICAL | 是 |
| GEO三方闭合矩阵 | case_manifest生成与A/B路prompt | code_only GSE与report/result对照不够直观 | 自动输出 report_only/code_only/result_only/declared_used 四列矩阵 | 是 |
| 外部验证泄漏检测 | C02统计/ML prompt | 101ML模型选择与验证cutoff需要代码级判断 | 检查验证集文件名附近的C-index选优、best_model赋值、surv_cutpoint/optimal cutoff | 是 |
| 高风险结构化证据门 | A02/C03 prompt + finalize前检查 | PDF图存在但结构化表和中间对象缺失 | 对CellChat、scTenifoldKnk、MISTy、药敏、评分模块列必需表和输入对象 | 是 |
| 文本残留联动 | B02图文一致性prompt | “结直肠癌”单看是文本错误，但结合外项目路径提示污染风险 | 当疾病名残留与foreign_project_id/code_only_GSE同现时，强制开数据污染专项 | 是 |
| no-op项目 | 本项目不需要修改企业微信安全规则 | 本次用户允许正式企业微信，且仅通过finalize正式流程发送 | 保持禁止测试/手动WeCom，允许正式完成通知 | 是 |

## 下一轮执行提醒

1. finalizer前应确认 `subagent_supervision_summary.json` 和学习文件存在。
2. 对CRITICAL外项目读取，不接受“未运行该段代码”的口头说明，必须用清理后的代码和重跑证据闭合。
3. 对101ML项目，外部验证是否独立应作为统计主审的必答题。
