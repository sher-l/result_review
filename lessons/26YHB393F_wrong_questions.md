# 26YHB393F wrong_question_set

## 1. MD双靶标复用同一套图件和原始轨迹
- 错误类型：高风险模块证据链断裂。
- 触发场景：报告分别声称 DSP 与 ITGB2/2JF1 两套 100 ns MD，但 Figure 19/20 逐面板重复，17_MD 仅一套 2JF1-CID_54614400。
- 证据依据：report_text.txt L249-L273；images/image_067-image_076；结果/17_MD。
- 正确标准：每个靶标-配体对必须有独立输入结构、轨迹/数值、图件、日志和参数。
- 下次提醒：MD图件重复不仅是视觉问题，应升级为核心结论证据问题。
- 严重程度：CRITICAL。
- 可执行规则建议：对 MD 图按图像哈希+靶标名+rawdata目录三联检查。

## 2. 报告声称 scRNA disease-vs-control DEG 但只交付 cluster marker
- 错误类型：交集入口证据不足。
- 触发场景：报告称 sc-DEGs=12542 并参与 bulk/scRNA/机械力交集。
- 证据依据：report_text.txt L21-L23/L132；01_QC/AllMarkers.csv。
- 正确标准：交集每个输入集合必须保留原始结构化导出和比较维度。
- 下次提醒：AllMarkers 不能自动等同 Disease vs Control DEG。
- 严重程度：MAJOR。
- 可执行规则建议：识别 scDEG 声称数量后必须在结果表中复算行数和比较列。

## 3. AI药物/Geneformer/DrugReflector只给最终排名或泛化方法
- 错误类型：AI高风险模块中间证据缺失。
- 触发场景：报告使用 DrugReflector/Geneformer/scTenifoldKnk 支撑机制和药物筛选。
- 证据依据：report_text.txt L209-L233；15_sc；16_docking/DrugReflector_Results.csv。
- 正确标准：必须有输入签名、模型版本、阈值、完整输出和靶点映射规则。
- 下次提醒：AI模型名出现时不要只看最终CSV，必须检查策略与中间矩阵。
- 严重程度：MAJOR。
- 可执行规则建议：新增 DrugReflector/Geneformer 证据清单。
