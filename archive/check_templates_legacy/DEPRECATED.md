# check_templates — 已归档 (v6.4)

> ⚠️ 本目录已于 v6.4 框架升级时移动至 `archive/check_templates_legacy/`。

## 说明

此目录原包含基于 `UniversalChecker` 基类的旧版检查器模板（v3-5 时期）。
当前主线检查器位于 `script_utils/`，基于 `BaseProjectChecker` 基类，由 `check_orchestrator.py` 统一调度。

## 如需使用旧模板

```
archive/check_templates_legacy/
├── check_clinical.py
├── check_deg.py
├── check_gwas_mr.py
├── check_ml.py
├── check_scrna.py
├── check_structure.py
├── report_consistency_checker.py
└── README.md
```

请勿将旧模板直接用于生产审核。如需复用其逻辑，请迁移至 `script_utils/` 并继承 `BaseProjectChecker`。
