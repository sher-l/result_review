# 26YSH065F framework_optimization_notes.md

## 本次是否需要框架优化
需要。当前 v6.7 已能通过机械检查提示 GSVA/高风险模块代码缺失，但对 GraphBAN/MD 这类“有最终图表但缺中间证据”的 CRITICAL 升级仍主要依赖人工分片。

## 建议加严点
1. `check_evidence_completeness.py`：当报告含 GraphBAN/ZINC/ADMET/Lipinski/PAINS，结果表仅有 SMILES/Protein/pred 且无过滤指标字段时，输出 MAJOR/CRITICAL 候选。
2. `check_model_consistency.py` 或新增高风险 MD checker：当报告含 GROMACS/100ns/MD/RMSD/RMSF/Hbond/Rg/SASA/FEL，但对应目录无 `.mdp/.top/.itp/.tpr/.xtc/.trr/.edr/.log/.xvg/.csv` 时，标记 CRITICAL 待AI确认。
3. `check_report_data_match.py`：方法标题含 GSVA 但代码/包/结果无 GSVA 时，不应只作 WARNING，可按“并列方法无交付证据”升为 MAJOR。
4. `check_reference_consistency`（建议新增）：抽取方法段引用编号，核对参考文献题名主题是否与软件包/数据库/方法名匹配。

## 无需改变的口径
- 公司宣传页位于参考文献后，继续按 boilerplate 不纳入正式审核范围。
- 单纯未交付某模块代码仍不应自动 CRITICAL；本次 CRITICAL 的依据是“核心结论证据链断裂”，不是单纯无代码。
