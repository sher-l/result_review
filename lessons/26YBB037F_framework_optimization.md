# 26YBB037F 框架优化记录

## 是否需要沉淀为框架规则

需要。当前框架已捕获部分 GSE 与阈值问题，但空间转录组高风险证据包、验证集参与选模、CytoTRACE方向反读仍需要更强规则。

| 优化点 | 目标文件/提示 | 当前不足 | 建议规则 | 是否复用 |
|---|---|---|---|---|
| 可执行 GSE 未声明升级 | mechanical_check MC-008 / B03 prompt | 注释与执行代码未充分区分 | 对非注释 readRDS/read.csv/CreateSeuratObject 附近 GSE 做 executable_code_only 标记 | 是 |
| 空间转录组 minimum evidence package | C03 高风险模块 prompt / policy | docking/MD/virtual KO 有模板，RCTD/MISTy/PSTS 缺模板 | RCTD需 weights/top标签/spot metadata；MISTy需重要性矩阵/置换/FDR；PSTS需 pseudotime表/root规则 | 是 |
| 验证集选模泄漏 | C02统计ML prompt / check_model_consistency | 只看模型口径不够 | 若验证集矩阵参与 best model 排序且后文称外部验证，生成 MAJOR | 是 |
| CytoTRACE方向核对 | B02视觉/图文 prompt | standard lane 可误判图类型 | 对 CytoTRACE/potency/relative order 强制图例与正文方向核对 | 是 |
| 方法名-函数名一致 | C01方法代码 prompt | ssGSEA/GSVA 同类词易混用 | 报告方法关键词必须匹配实际函数参数，如 method=ssgsea 或 gsvaParam | 是 |

## 本次无操作项

未修改框架代码；仅将可复用教训镜像到 `result_review_framework/lessons/26YBB037F_framework_optimization.md`。
