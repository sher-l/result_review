# 26YHB452F 框架优化记录

## 本次可复用规则建议

1. **标题范围一致性规则加强**
   - 目标：`policy/audit_policy.json` / 预解析标题-模块一致性检查。
   - 建议：提取题名/研究方向中的 `bulk|空转|空间|单细胞|GWAS|scPagwas`，与 `project_structure.modules` 做覆盖矩阵；题名声明但目录/代码无对应模块时标记 MAJOR。

2. **方向性总括语规则加强**
   - 目标：`check_report_data_match.py` 或数字交叉验证。
   - 建议：命中“所有/均/全部 + 显著/高于/低于”时，强制读取对应 result CSV 中的 `significance|p_value|higher_group|median`，不满足逐项一致即标记 MAJOR。

3. **关键输入对象复现链规则加强**
   - 目标：`check_code_existence.py` / `check_data_flow.py`。
   - 建议：解析 R 脚本 `read.*|load|Single_data|vcf|h5ad|rds|qs2`，若读入文件未在项目交付目录出现，输出复现链缺口；结果图存在不得自动豁免。

## 本次无需要立即修改的事项

- 企业微信通知策略无需修改：本次未做测试发送，仅允许最终正式完成路径。
