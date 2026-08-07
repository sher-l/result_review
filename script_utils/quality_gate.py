#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
质量评估模块（审核框架 v6.5）

定义问题严重性级别和软性评估逻辑：
- FATAL: 最高优先级问题，需要优先 AI核对
- CRITICAL: 严重问题，需重点处理
- MAJOR: 较严重问题，影响报告质量
- WARNING: 警告级别
- INFO: 信息级别

作者: 审核框架 v6.5
创建日期: 2026-02-13
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field


class SeverityLevel(Enum):
    """问题严重性级别（5级）"""
    FATAL = "FATAL"       # 最高优先级问题
    CRITICAL = "CRITICAL"   # 严重错误
    MAJOR = "MAJOR"        # 较严重问题
    WARNING = "WARNING"     # 警告
    INFO = "INFO"          # 信息


@dataclass
class Issue:
    """问题数据类"""
    severity: SeverityLevel
    category: str           # 问题类别
    description: str        # 问题描述
    file: Optional[str] = None      # 文件位置
    line: Optional[int] = None       # 行号
    code: Optional[str] = None       # 问题代码
    suggestion: Optional[str] = None # 修复建议
    evidence: Optional[dict] = None  # 证据数据

    def __str__(self) -> str:
        severity_icons = {
            SeverityLevel.FATAL: '🔴',
            SeverityLevel.CRITICAL: '🟠',
            SeverityLevel.MAJOR: '🟤',
            SeverityLevel.WARNING: '🟡',
            SeverityLevel.INFO: '🔵'
        }
        icon = severity_icons.get(self.severity, '⚪')

        location = f"{self.file}:{self.line}" if self.file and self.line else (self.file or '')

        return f"{icon} [{self.severity.value}] {self.category}: {self.description} ({location})"


class QualityGate:
    """质量评估器

    当前只做风险分层和审核建议，不做“发现问题立即停止”的硬门禁。
    """

    def __init__(self, strict_mode: bool = False):
        """
        初始化质量评估器

        参数:
            strict_mode: 兼容旧字段；当前始终采用软评估模式
        """
        self.strict_mode = strict_mode
        self.issues: List[Issue] = []

        # 风险阈值配置：用于提示优先级，不用于中断审核
        self.thresholds = {
            SeverityLevel.FATAL: 0,
            SeverityLevel.CRITICAL: 5,
            SeverityLevel.MAJOR: 10,
            SeverityLevel.WARNING: 20,
        }

    def add_issue(self, issue: Issue):
        """添加问题"""
        self.issues.append(issue)

    def add_fatal(self, category: str, description: str, **kwargs):
        """添加FATAL级问题"""
        self.add_issue(Issue(
            severity=SeverityLevel.FATAL,
            category=category,
            description=description,
            **kwargs
        ))

    def add_critical(self, category: str, description: str, **kwargs):
        """添加CRITICAL级问题"""
        self.add_issue(Issue(
            severity=SeverityLevel.CRITICAL,
            category=category,
            description=description,
            **kwargs
        ))

    def add_major(self, category: str, description: str, **kwargs):
        """添加MAJOR级问题"""
        self.add_issue(Issue(
            severity=SeverityLevel.MAJOR,
            category=category,
            description=description,
            **kwargs
        ))

    def add_warning(self, category: str, description: str, **kwargs):
        """添加WARNING级问题"""
        self.add_issue(Issue(
            severity=SeverityLevel.WARNING,
            category=category,
            description=description,
            **kwargs
        ))

    def add_info(self, category: str, description: str, **kwargs):
        """添加INFO级问题"""
        self.add_issue(Issue(
            severity=SeverityLevel.INFO,
            category=category,
            description=description,
            **kwargs
        ))

    def get_issues_by_severity(self, severity: SeverityLevel) -> List[Issue]:
        """按严重性获取问题"""
        return [i for i in self.issues if i.severity == severity]

    def get_issues_by_category(self, category: str) -> List[Issue]:
        """按类别获取问题"""
        return [i for i in self.issues if i.category == category]

    def count_by_severity(self) -> Dict[SeverityLevel, int]:
        """统计各级别问题数量"""
        counts = {level: 0 for level in SeverityLevel}
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts

    def check_gate(self) -> tuple[bool, str]:
        """
        生成软性质量评估结果

        返回:
            (passed, message) - 是否达到低风险状态及消息
        """
        counts = self.count_by_severity()

        if counts[SeverityLevel.FATAL] > 0:
            return False, f"🔴 发现{counts[SeverityLevel.FATAL]}个FATAL级问题，需优先 AI核对，但自动审核不应中断"

        if counts[SeverityLevel.CRITICAL] > self.thresholds[SeverityLevel.CRITICAL]:
            return False, f"🟠 发现{counts[SeverityLevel.CRITICAL]}个CRITICAL级问题（提示阈值：{self.thresholds[SeverityLevel.CRITICAL]}），需重点 AI复核"

        if counts[SeverityLevel.MAJOR] > self.thresholds[SeverityLevel.MAJOR]:
            return False, f"🟤 发现{counts[SeverityLevel.MAJOR]}个MAJOR级问题（提示阈值：{self.thresholds[SeverityLevel.MAJOR]}），建议逐项复核"

        if counts[SeverityLevel.WARNING] > self.thresholds[SeverityLevel.WARNING]:
            return False, f"🟡 发现{counts[SeverityLevel.WARNING]}个WARNING级问题（提示阈值：{self.thresholds[SeverityLevel.WARNING]}），建议复核"

        return True, "✅ 自动检查完成，当前未发现超阈值高风险问题"

    def get_status(self) -> dict:
        """
        获取评估状态

        返回:
            {
                'passed': 是否达到低风险状态,
                'message': 状态消息,
                'counts': 各级别问题数,
                'can_proceed': 是否可以继续逐项证据复核
            }
        """
        passed, message = self.check_gate()
        counts = self.count_by_severity()

        has_fatal = counts[SeverityLevel.FATAL] > 0
        has_critical_overflow = counts[SeverityLevel.CRITICAL] > self.thresholds[SeverityLevel.CRITICAL]

        if has_fatal:
            review_recommendation = '优先复核FATAL问题'
        elif has_critical_overflow:
            review_recommendation = '优先复核CRITICAL问题'
        else:
            review_recommendation = '进入常规逐项证据复核'

        return {
            'passed': passed,
            'message': message,
            'counts': {level.value: count for level, count in counts.items()},
            'can_proceed': True,
            'strict_mode': self.strict_mode,
            'review_recommendation': review_recommendation,
            'has_fatal': has_fatal
        }

    def generate_report(self) -> str:
        """生成评估报告"""
        status = self.get_status()
        counts = status['counts']

        report_lines = [
            "# 质量评估报告",
            "",
            f"**评估状态**: {'✅ 低风险' if status['passed'] else '⚠️ 需重点复核'}",
            f"**可以继续审核**: {'是' if status['can_proceed'] else '否'}",
            f"**审核建议**: {status['review_recommendation']}",
            f"**严格模式兼容标记**: {'是' if self.strict_mode else '否'}",
            "",
            "## 问题统计",
            "",
            f"| 级别 | 数量 | 阈值 | 状态 |",
            f"|------|------|------|------|",
        ]

        # 生成统计表格
        severity_order = ['FATAL', 'CRITICAL', 'MAJOR', 'WARNING', 'INFO']
        for sev_name in severity_order:
            count = counts.get(sev_name, 0)
            threshold = self.thresholds.get(SeverityLevel(sev_name), '-')
            if isinstance(threshold, int):
                status_icon = '✅' if count <= threshold else '⚠️'
            else:
                status_icon = 'ℹ️'
            report_lines.append(f"| {sev_name} | {count} | {threshold} | {status_icon} |")

        report_lines.extend(["", "## 详细问题列表", ""])

        # 按严重性分组显示问题
        if not self.issues:
            report_lines.append("✅ 未发现问题")
        else:
            for severity in [SeverityLevel.FATAL, SeverityLevel.CRITICAL,
                           SeverityLevel.MAJOR, SeverityLevel.WARNING, SeverityLevel.INFO]:
                issues = self.get_issues_by_severity(severity)
                if not issues:
                    continue

                report_lines.extend([
                    f"### {severity.value}级问题 ({len(issues)}个)",
                    ""
                ])

                for i, issue in enumerate(issues, 1):
                    report_lines.extend([
                        f"#### 问题 {i}",
                        f"- **类别**: {issue.category}",
                        f"- **描述**: {issue.description}",
                    ])

                    if issue.file:
                        report_lines.append(f"- **位置**: {issue.file}" + (f":{issue.line}" if issue.line else ""))
                    if issue.suggestion:
                        report_lines.append(f"- **建议**: {issue.suggestion}")
                    if issue.evidence:
                        report_lines.append(f"- **证据**: ```{issue.evidence}```")

                    report_lines.append("")

        # 建议部分
        if status['has_fatal']:
            report_lines.extend([
                "## 🔴 高优先级提醒",
                "",
                "**影响**: 自动检查已完成，但逐项证据复核应优先处理FATAL问题",
                "",
                "**建议操作**:",
                "1. 汇总全部FATAL问题并逐项核对证据",
                "2. 在最终审核报告中优先列出这些问题",
                "3. 如已修正，可重新运行自动检查对比前后差异",
                ""
            ])
        elif not status['passed']:
            report_lines.extend([
                "## ⚠️ 质量警告",
                "",
                "**影响**: 自动检查已完成，建议逐项证据复核优先关注高风险项",
                "",
                "**建议操作**:",
                "1. 先检查CRITICAL级问题",
                "2. 再补充WARNING级问题的复核记录",
                ""
            ])

        return "\n".join(report_lines)


class QualityGateBuilder:
    """质量评估构建器 - 用于从检查结果快速构建风险分层结果"""

    def __init__(self):
        self.gate = QualityGate()

    def add_from_check_result(self, check_name: str, result: dict):
        """
        从检查结果添加问题

        # 说明：orchestrator 已通过 _normalize_result() 统一输出为标准 6 字段。
        下方 4 个特殊处理器保持向后兼容，处理 P0 检查器的非标准键（errors/mismatches）。
        其余 checker 走通用 _add_from_generic_check，使用标准化的 issues/warnings 键。

        参数:
            check_name: 检查名称
            result: 检查结果字典（已标准化）
        """
        if check_name == '项目编号一致性检查':
            self._add_from_project_id_check(result)
        elif check_name == '术语主题一致性检查':
            self._add_from_term_check(result)
        elif check_name == '跨模块数据流验证':
            self._add_from_data_flow_check(result)
        elif check_name == '证据完整性与参数完备性检查':
            self._add_from_evidence_check(result)
        else:
            # 通用处理：支持所有返回 issues/warnings 列表的 checker
            self._add_from_generic_check(check_name, result)

    def _add_from_project_id_check(self, result: dict):
        """从项目编号检查结果添加问题"""
        if result.get('fatal'):
            for error in result.get('errors', []):
                self.gate.add_fatal(
                    category='项目编号不一致',
                    description=error.get('message', '发现错误项目编号'),
                    file=error.get('file'),
                    line=error.get('line'),
                    suggestion=f'将{error.get("wrong_id")}修正为{error.get("correct_id")}'
                )

    def _add_from_term_check(self, result: dict):
        """从术语检查结果添加问题"""
        for mismatch in result.get('mismatches', []):
            severity = SeverityLevel.FATAL if mismatch.get('severity') == 'FATAL' else SeverityLevel.CRITICAL

            self.gate.add_issue(Issue(
                severity=severity,
                category='术语主题不匹配',
                description=f'发现不匹配术语: {mismatch.get("term")}',
                file=mismatch.get('file'),
                line=mismatch.get('line'),
                suggestion=f'使用项目正确的术语: {mismatch.get("correct_term", "查看术语库")}',
                evidence={'context': mismatch.get('context', '')}
            ))

    def _add_from_data_flow_check(self, result: dict):
        """从数据流检查结果添加问题"""
        for issue in result.get('issues', []):
            severity = SeverityLevel.FATAL if issue.get('severity') == 'FATAL' else SeverityLevel.CRITICAL

            self.gate.add_issue(Issue(
                severity=severity,
                category='数据流断裂',
                description=issue.get('message', '数据流不一致'),
                file=issue.get('monocle_file') or issue.get('inter_file'),
                suggestion='确保下游分析使用完整的上游输出结果',
                evidence=issue
            ))

    def _add_from_evidence_check(self, result: dict):
        """从证据完整性检查结果添加问题"""
        severity_map = {
            'FATAL': SeverityLevel.FATAL,
            'CRITICAL': SeverityLevel.CRITICAL,
            'MAJOR': SeverityLevel.MAJOR,
            'WARNING': SeverityLevel.WARNING,
            'INFO': SeverityLevel.INFO,
        }

        for issue in result.get('issues', []):
            severity = severity_map.get(issue.get('severity', 'WARNING'), SeverityLevel.WARNING)
            self.gate.add_issue(Issue(
                severity=severity,
                category=issue.get('category', '证据完整性'),
                description=issue.get('message', '发现证据完整性问题'),
                file=issue.get('file'),
                suggestion=issue.get('suggestion'),
                evidence=issue.get('evidence')
            ))

    def _add_from_generic_check(self, check_name: str, result: dict):
        """通用 checker 结果处理：支持 issues/warnings/mismatches/species_mismatches 等键"""
        severity_map = {
            'FATAL': SeverityLevel.FATAL,
            'CRITICAL': SeverityLevel.CRITICAL,
            'MAJOR': SeverityLevel.MAJOR,
            'WARNING': SeverityLevel.WARNING,
            'INFO': SeverityLevel.INFO,
        }

        # 处理标准 issues 键和 mismatches 变体
        for key in ('issues', 'mismatches', 'species_mismatches'):
            for issue in result.get(key, []):
                if not isinstance(issue, dict):
                    continue
                severity = severity_map.get(issue.get('severity', 'CRITICAL'), SeverityLevel.CRITICAL)
                description = issue.get('message') or issue.get('description')
                if not description and key == 'species_mismatches':
                    description = f"物种不匹配: 基因集={issue.get('gmt_species')}, 数据={issue.get('data_species')}"
                self.gate.add_issue(Issue(
                    severity=severity,
                    category=issue.get('category', check_name),
                    description=description or f'{check_name} 发现问题',
                    file=issue.get('file'),
                    suggestion=issue.get('suggestion'),
                    evidence=issue.get('evidence')
                ))

        for warning in result.get('warnings', []):
            if not isinstance(warning, dict):
                continue
            severity = severity_map.get(warning.get('severity', 'WARNING'), SeverityLevel.WARNING)
            self.gate.add_issue(Issue(
                severity=severity,
                category=warning.get('category', check_name),
                description=warning.get('message', f'{check_name} 发现警告'),
                file=warning.get('file'),
                suggestion=warning.get('suggestion'),
                evidence=warning.get('evidence')
            ))

    def add_from_mechanical_checks(self, mc_result: dict):
        """从 Layer 0 机械检查结果导入问题到质量评估"""
        if not mc_result or not isinstance(mc_result, dict):
            return
        severity_map = {
            'FATAL': SeverityLevel.FATAL,
            'CRITICAL': SeverityLevel.CRITICAL,
            'MAJOR': SeverityLevel.MAJOR,
            'WARNING': SeverityLevel.WARNING,
            'INFO': SeverityLevel.INFO,
        }
        issues = mc_result.get('issues', [])
        if not isinstance(issues, list):
            return
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = severity_map.get(issue.get('severity', 'WARNING'), SeverityLevel.WARNING)
            self.gate.add_issue(Issue(
                severity=severity,
                category=f"机械检查-{issue.get('code', 'MC')}",
                description=issue.get('message', '机械检查发现问题'),
                line=issue.get('line'),
                evidence={'context': issue.get('context', '')}
            ))

    def build(self) -> QualityGate:
        """构建并返回评估器"""
        return self.gate


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='质量评估模块')
    parser.add_argument('--output', '-o', help='输出报告文件路径')

    args = parser.parse_args()

    # 示例：创建一个测试评估器
    gate = QualityGate()

    # 添加一些测试问题
    gate.add_fatal(
        category='测试',
        description='这是一个FATAL级测试问题',
        file='test.py',
        line=1
    )

    gate.add_warning(
        category='测试',
        description='这是一个WARNING级测试问题',
        file='test.py',
        line=2
    )

    report = gate.generate_report()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存到: {args.output}")
    else:
        print(report)


if __name__ == '__main__':
    main()
