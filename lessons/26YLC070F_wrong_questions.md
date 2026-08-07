# 26YLC070F wrong_question_set

| 典型错误 | 触发场景 | 证据基础 | 正确标准 | 下一次审核提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| 跨项目RDS主动读取被当作普通代码残留 | 代码中出现其他项目编号和可执行readRDS/load路径 | `Code/01.02...`读取 `16_26YBB086F/3Dataset`；仲裁列为CRITICAL | 任何外项目主动读取均应阻断，除非报告、数据和结果明确声明且可追溯 | 搜索项目编号模式和绝对路径；区分注释与非注释执行代码 | CRITICAL | 增加规则：非注释代码命中其他项目ID + readRDS/load/read.csv 时自动升CRITICAL并进入仲裁 |
| 未声明GSE被低估为模板噪声 | 代码引用多个GSE但报告数据来源未列出 | mechanical_check_result和A/B路复核均发现多GSE | 使用过的数据集必须在报告、代码、结果索引三处闭合 | 对所有GSE/GSM建立三方索引矩阵 | MAJOR | 生成GEO交叉矩阵：report_only/code_only/result_only并要求Lead AI处置 |
| 验证集参与选模仍称外部验证 | 101ML或多模型筛选用训练集+验证集C-index选优 | `04_Cox_101ML_KM.r`共同计算C-index并选择SuperPC | 外部验证集不能参与模型选择或cutoff优化 | 检查best_model选择和cutoff来源 | MAJOR | 静态规则：验证集文件名附近出现best_model/Cindex selection/surv_cutpoint时标记验证偏倚 |
| PDF图件替代结构化证据 | CellChat、评分、药敏等只有PDF图 | A02/C01/C02指出缺LR表、评分明细、方向统计 | 核心数值结论必须有CSV/XLSX/RDS结构化表 | 不把“有图”视为“可复核” | MAJOR | 对高风险模块要求结果表清单：score、pvalue、effect、source/target、LR、cutoff |
| 高风险方法缺中间对象 | scTenifoldKnk/Geneformer/MISTy等只留终图或少量结果 | C03发现缺RDS/GRN对象、Geneformer无输出 | 高风险推断必须交付输入对象、中间模型、参数和完整输出 | 先查输入对象，再查最终图 | MAJOR | 高风险模块增加必需文件模板和缺失即MAJOR/CRITICAL的判定门 |
| 文本病种残留未与代码残留联动 | BLCA报告出现“结直肠癌” | report_text L297/L318 | 疾病名称残留在存在跨项目代码残留时应提高警惕 | 文本残留与外项目路径同时出现时进入重点复核 | WARNING | 加权规则：疾病残留 + foreign_project_id/code_only_GSE 同时出现时触发数据污染专项 |
