# Archive 清理记录

> **日期**: 2026-04-07  
> **版本**: v6.4 框架优化  
> **操作人**: Copilot (用户确认后执行)

---

## 已删除内容

| 路径 | 文件数 | 原用途 | 删除原因 |
|------|--------|--------|---------|
| `analysis_tools/` | 4 py | v3-v4 旧版扫描工具 (_scan*.py, _deep_scan.py) | 被 check_orchestrator.py 替代 |
| `orphan_v6/` | 8 件 | v6 早期实验代码 (universal_checker.py 等) | 被 script_utils/ 新检查器替代 |
| `old_docs/` | 2 md | 框架优化摘要、legacy 问题文档 | 已并入主线文档 |
| `old_plans/` | 1 目录 | 旧版 agent_plans/ (内容已空) | 已迁移到 agent_plans/ 主目录 |
| `tmp_tests/` | 3 py | 临时测试脚本 | 开发过程临时文件 |
| `init_check.py` | 1 py | 初始化检查（空壳） | 无生产用途 |
| `MODULE_CHECK_TEMPLATE.md` | 1 md | 空模板 | 无生产用途 |
| `REPORT_CHECK_PLAN.md` | 1 md | 空模板 | 无生产用途 |
| `check_templates_legacy/*.py` | 7 py | v3-v5 旧检查器 (UniversalChecker 系列) | 被 BaseProjectChecker 系列替代 |

## 保留内容

| 路径 | 原因 |
|------|------|
| `history/CHANGELOG.md` | 框架演进记录 |
| `history/FRAMEWORK_V4_IMPLEMENTATION_SUMMARY.md` | v4 实现历史 |
| `history/V43_TERMINOLOGY_*.md` | 术语改进历史 |
| `check_templates_legacy/README.md` | 旧检查器说明 |
| `check_templates_legacy/DEPRECATED.md` | 迁移指引 |
| `MASTER_PROMPT_v5.0_backup.md` | v5 主提示词备份 |

## 回溯方式

如需恢复已删除文件：
- BaiduSyncdisk 版本历史（文件级回溯）
- 2026-04-07 之前的快照
