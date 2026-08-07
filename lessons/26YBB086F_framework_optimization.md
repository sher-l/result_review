# 26YBB086F 框架优化笔记

## 需要加强的检查

1. GEO 反向扫描应区分“报告声明、目录存在、代码读取、对象名、交集参与”五级证据；若未声明 GSE 出现在读取路径或 common_genes，自动升级为高风险。
2. 101ML 检查应要求 C-index/AUC 完整矩阵、best_model 选择代码、事件编码和方向翻转记录；仅 PDF 热图不足。
3. 视觉预筛应把核心模型图中的疾病名/癌种缩写 OCR 作为高优先级项；出现 LUAD/CRC 等外癌种时不应仅作为普通图文问题。
4. 高风险模块应强制列出 Rdata/H5AD/checkpoint/helper/sessionInfo 是否交付，缺失时与结论强度绑定。
5. final report 可允许 convergence=False，但必须有 arbitration 说明和主问题合并表，避免单方高风险项被丢失。

## 本次无需修改框架代码的事项

- 监督 gate 和 final linter 已能阻止缺少 subagent summary、学习产物和 final report 的 finalize。
- 本次主要是项目质量问题，不需要改变通知策略；企业微信仍只允许正式 finalize 路径。
