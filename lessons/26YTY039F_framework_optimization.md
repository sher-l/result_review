# 26YTY039F 框架优化沉淀

## 建议落地规则

1. `report_text.txt` 首页项目号与 case_manifest 项目号不一致时，至少 CRITICAL，若结果路径/代码也指向旧项目则 FATAL。
2. 发现“客户最终不想做 X，要做 Y”时，必须把 X/Y 与主体数据类型、标题和结论比较。
3. 静态扫描 ML 脚本中验证集变量参与特征选择或模型训练的模式：`p_test`、`test_data`、`final_roc_genes`、`train_data = test_data`。
4. 对验证集 sensitivity/F1 低但结论含“较优、稳定、泛化、良好”的句子自动提示。
5. ROC/SHAP 只交付 PDF 图而缺 CSV/XLSX 时，至少 MAJOR 或 WARNING，按是否支撑核心结论升级。

## 适用范围

适用于癌症机器学习、生物标志物筛选、独立验证集和 SHAP 解释类报告审核。
