# 26YLM192F framework_optimization_notes

- 生成日期：2026-06-29
- 总体结论：需要小幅强化现有框架的高风险模块、数据来源追踪、模型结构化证据和复制粘贴残留检查；无需改动企业微信安全规则。

## 1. 高风险模块空目录阻断规则
- 现状：MC-016已识别MD目录为空，但收敛脚本把A/C相似发现放入arbitration_queue，未自动合并。
- 应变严格的策略/检查：high-risk text-file-image consistency；convergence similarity merge。
- 建议：对“MD/分子动力学/Gromacs/100ns”正文命中且目录file_count=0的情况，直接产生唯一阻断finding，并在合并阶段按目录路径优先去重。
- 本项目证据：F-CR-01。

## 2. 数据集疾病背景四联核对
- 现状：框架未自动把报告主题、GEO ID、样本量和参考文献疾病标题联动检查。
- 应变严格的策略/检查：data_flow_coverage；foreign disease/template residue。
- 建议：新增可选规则：抽取GSE编号附近疾病词和参考文献标题疾病词，出现OA/osteoarthritis与RA/rheumatoid arthritis交叉时提示AI复核。
- 本项目证据：F-MJ-01。

## 3. 下游矩阵样本ID provenance 检查
- 现状：GSVA矩阵header中的GSM样本未在报告数据来源声明中出现，需要子代理发现。
- 应变严格的策略/检查：module evidence review；data lineage check。
- 建议：对CSV header抽取GSM/GSE/E-MTAB样本标识，和report_text、00.数据文件名、case_manifest datasets交叉比对。
- 本项目证据：F-MJ-02。

## 4. 模型模块结构化证据门槛
- 现状：SHAP、nomogram、ROC只交付PDF时，框架仍需AI判断证据不足。
- 应变严格的策略/检查：statistical reproducibility prompt；model evidence completeness。
- 建议：对SHAP/列线图/ROC/DCA目录增加结构化证据最低要求：矩阵/系数/预测概率/指标表/代码至少部分存在；否则自动生成MAJOR候选。
- 本项目证据：F-MJ-05、F-MJ-06、F-MJ-07。

## 5. HALLMARK/KEGG和NES拼写一致性
- 现状：通路数据库错写和|NS|拼写错误由事实核对切片发现。
- 应变严格的策略/检查：copy_paste_residue；GSEA terminology check。
- 建议：在机械检查中加入文件名数据库词与报告结果段数据库词一致性；加入“|NS|”固定模式提醒。
- 本项目证据：F-MJ-08、F-WN-02。

## 6. 通知规则
- 本项目处理：用户明确授权企业微信正式完成通知；未做WeCom测试发送。
- 框架变化：no-op，现有Local Notification Safety Rules足够；需要继续禁止任何WeCom smoke/test发送。
