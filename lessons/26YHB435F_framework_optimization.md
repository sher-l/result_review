# 26YHB435F 框架优化记录

## 需要加固的策略/提示
1. **外项目路径残留扫描**：当前机械检查未把 `16_26YBB086F`、`17_26YLC070F` 作为 `foreign_project_ids` 抓出。建议在 `check_project_id_consistency` 或代码存在性检查中扫描所有代码正文的项目编号、`setwd`、`os.chdir`、`readRDS`、`read_h5ad`。
2. **显著性语言-表格联动**：对报告表格中的 `p_val_adj` 与正文“显著增强/显著上调”建立邻近窗口检查，尤其 CellChat/NicheNet 表。
3. **TopN 药物去重口径**：新增 DrugReflector/CLUE TopN 文件检查：rows、unique pert_id、unique cmap_name、MOA 统计单位，并要求 final report 标注口径。
4. **空表与仅图件门禁**：对 SCENIC RSS、BEAM、CytoTRACE2、Augur、CellChat LR 等高风险模块，检查是否存在非空结构化结果；空表应比“文件存在”更高优先级。

## 本次不直接修改框架代码的理由
- 当前任务边界是正式审核项目，不是框架升级；因此仅镜像 lessons，避免在审核收尾前引入框架代码改动风险。
- 上述规则可执行且可复用，建议后续框架维护任务统一实现。

## 建议更新目标
- `result_review_framework/lessons/patterns/copy_paste_residue.md`：加入外项目可执行路径残留示例。
- `result_review_framework/lessons/patterns/numerical_direction_errors.md`：加入 p_val_adj=1 仍写显著增强示例。
- `result_review_framework/lessons/patterns/data_flow_coverage.md`：加入 Top100 rows vs unique compounds 口径示例。
