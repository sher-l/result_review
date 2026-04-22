# 模式：方法声称与代码实现不一致

> 严重性：🔴 CRITICAL
> 涉及项目：26YSH015F, 26YHB100F, 26YLM076F, 26YHB087F

---

## P05: 统计方法声称不一致

**描述**：报告中声称使用某种分析方法，但代码中缺少对应的函数调用或参数与标准定义不符。

**信号**：
- 声称"逐步回归"但代码无 `step()`/`stepAIC()` 调用
- 声称"LASSO 筛选"但代码无 `glmnet`/`cv.glmnet`
- 声称"VIF 筛选"但代码无 `car::vif` 调用
- 报告写"6 种算法"但代码只实现 5 种

**检测方法**：
```
# R 代码搜索（按声称方法）
声称"逐步回归" → grep -rn "step\b|stepAIC" *.R
声称"LASSO"     → grep -rn "glmnet|cv\\.glmnet" *.R  
声称"VIF 筛选"  → grep -rn "vif\b|car::vif" *.R
声称"随机森林"  → grep -rn "randomForest|ranger|rf" *.R
```

**案例**：26YSH015F — 报告声称"逐步回归优化模型"，代码实际为全模型取 P<0.05

---

## P16: 机器学习方法名称不匹配

**描述**：ML 方法名称与实际参数配置不一致。

**信号**：
- 报告写"LASSO"但 glmnet `alpha≠1`（实际为 Elastic Net）
- 报告写"SVM-RFE"但 `rfeControl(functions=rfFuncs)`（实际为 RF-RFE）
- 算法名与输入特征集不符

**检测**：
```
# 关键参数验证
LASSO    → glmnet alpha 必须 = 1
Ridge    → glmnet alpha 必须 = 0
SVM-RFE  → rfeControl(functions=caretFuncs) 或 svmFuncs
RF-RFE   → rfeControl(functions=rfFuncs)
```

**案例**：26YHB100F — glmnet alpha=0.6 报告却写"LASSO"

---

## P19: 临床统计方法虚假声明

**描述**：临床统计特有——方法段和结果段声称使用某技术但代码完全未实现。

**信号**：
- 声称"逐步回归"但代码无 step() 调用
- 方法段和结果段的方法描述互相矛盾（一处写逐步回归，一处写全模型）
- 声称使用验证集但代码无数据拆分

**检测**：同 P05，重点关注临床统计项目特有方法

**案例**：26YSH015F — 方法段和结果段均声称逐步回归，代码实际为全模型 P<0.05 过滤

---

## 综合检测策略

```
1. 自动检测 (Round 0):
   - check_ml_anomaly.py → 部分 P16 检测
   - check_clinical_statistics.py → 部分 P19 检测

2. Sub-Agent 审核 (Layer 3):
   - 方法段关键词提取 → 代码 grep 验证 → P05
   - glmnet/rfe 参数精确核对 → P16

3. 关键参数速查表:
   | 声称方法 | 必须存在的代码 | 关键参数 |
   |---------|--------------|---------|
   | LASSO | glmnet(..., alpha=1) | alpha=1 |
   | Ridge | glmnet(..., alpha=0) | alpha=0 |
   | SVM-RFE | rfeControl(functions=svmFuncs) | functions |
   | 逐步回归 | step() / stepAIC() | — |
   | VIF 筛选 | car::vif() | — |
```
