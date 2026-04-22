#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目编号一致性检查器（P0级 - FATAL）

基于项目25YLC105F的发现：所有14个代码文件使用错误的项目编号25YLC135F

FATAL级标准：
- 发现任何错误项目编号 → FATAL，代码无法复现
- 多处(>3处)错误 → FATAL，系统性复制粘贴

作者: 审核框架 v6.5
创建日期: 2026-02-13
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

from base_project_checker import BaseProjectChecker


PROJECT_ID_RE = re.compile(r'(\d{2}[A-Z]+\d+[A-Z])')
PROJECT_ID_WORD_RE = re.compile(r'\b(\d{2}[A-Z]+\d+[A-Z])\b')


class ProjectIDChecker(BaseProjectChecker):
    """项目编号一致性检查器"""

    def __init__(self, project_path: str, project_id: str = None, metadata=None, layer0_data: dict = None):
        """
        初始化检查器

        参数:
            project_path: 项目根目录路径
            project_id: 项目编号（如果为None，从文件夹名提取）
        """
        super().__init__(project_path, metadata=metadata, layer0_data=layer0_data)
        self.project_id = project_id or self._extract_project_id()
        self.errors = []
        self.code_dir = self.find_code_directory()

    def _extract_project_id(self) -> str:
        """
        从文件夹名提取项目编号

        项目编号格式: XX###X##X (如25YLC105F)
        """
        dir_name = self.project_path.name
        # 匹配格式: 数字+字母+数字+F
        match = PROJECT_ID_RE.search(dir_name)
        if match:
            return match.group(1)
        return "Unknown"

    def check_all(self) -> Dict:
        """统一入口，委托给 check_all_files"""
        return self.check_all_files()

    def check_all_files(self) -> Dict:
        """
        检查所有代码文件中的项目编号

        返回:
            {
                'project_id': 正确的项目编号,
                'total_files': 检查的文件总数,
                'error_files': 有错误的文件数,
                'errors': 错误列表,
                'fatal': 是否为FATAL级问题
            }
        """
        if not self.code_dir:
            return {
                'project_id': self.project_id,
                'total_files': 0,
                'error_files': 0,
                'issues': [{'type': 'no_code_dir', 'message': '未找到代码目录'}],
                'fatal': False
            }

        # 查找所有R和Python文件（去重，避免 Windows 大小写不敏感重复）
        seen = set()
        all_files = []
        for pattern in ('*.r', '*.R', '*.py'):
            for f in self.code_dir.glob(pattern):
                key = str(f).lower()
                if key not in seen:
                    seen.add(key)
                    all_files.append(f)

        for file_path in all_files:
            self._check_file(file_path)

        # 判断是否为FATAL
        fatal = len(self.errors) > 0

        return {
            'project_id': self.project_id,
            'total_files': len(all_files),
            'error_files': len(set(e['file'] for e in self.errors)),
            'issues': self.errors,
            'warnings': self.warnings,
            'fatal': fatal
        }

    def _check_file(self, file_path: Path):
        """检查单个文件"""
        try:
            from utils import safe_read_file
            content = safe_read_file(file_path)[0]
            self._check_setwd_paths(file_path, content)
            self._check_project_id_mentions(file_path, content)
        except Exception as e:
            self.warnings.append({
                'file': str(file_path.relative_to(self.project_path)),
                'type': 'read_error',
                'message': f'无法读取文件: {str(e)}'
            })

    def _check_setwd_paths(self, file_path: Path, content: str):
        """
        检查setwd路径中的项目编号

        匹配模式: setwd(".../项目编号/...")
        """
        # 匹配setwd()中的路径
        setwd_pattern = r'setwd\s*\(\s*["\']([^"\']+)[\"\']'
        matches = re.findall(setwd_pattern, content, re.IGNORECASE)

        for match in matches:
            if self.project_id not in match:
                # 尝试提取路径中的项目编号
                path_id = self._extract_id_from_path(match)
                if path_id and path_id != self.project_id:
                    self.errors.append({
                        'file': str(file_path.relative_to(self.project_path)),
                        'line': self._find_line_number(content, match),
                        'type': 'setwd_wrong_id',
                        'wrong_id': path_id,
                        'correct_id': self.project_id,
                        'path': match,
                        'message': f"setwd路径使用错误编号: {path_id} (应为: {self.project_id})"
                    })

    def _check_project_id_mentions(self, file_path: Path, content: str):
        """
        检查代码中所有项目编号的出现

        匹配格式: XX###X##X (如25YLC105F, 25YLC135F)
        """
        # 通用项目编号模式
        matches = PROJECT_ID_WORD_RE.findall(content)

        for match in matches:
            if match != self.project_id:
                line_num = self._find_line_number(content, match)
                # 排除setwd已经报告的错误
                already_reported = any(
                    e['file'] == str(file_path.relative_to(self.project_path)) and
                    e['line'] == line_num and
                    e.get('wrong_id') == match
                    for e in self.errors
                )
                if not already_reported:
                    self.errors.append({
                        'file': str(file_path.relative_to(self.project_path)),
                        'line': line_num,
                        'type': 'wrong_project_id',
                        'wrong_id': match,
                        'correct_id': self.project_id,
                        'message': f"发现错误项目编号: {match} (应为: {self.project_id})"
                    })

    def _extract_id_from_path(self, path: str) -> str:
        """从路径中提取项目编号"""
        match = PROJECT_ID_RE.search(path)
        return match.group(1) if match else None

    def _find_line_number(self, content: str, search_text: str) -> int:
        """查找文本所在的行号"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if search_text in line:
                return i
        return 0

    def generate_report(self) -> str:
        """生成检查报告"""
        result = self.check_all_files()

        report_lines = [
            "# 项目编号一致性检查报告",
            "",
            f"**项目编号**: {result['project_id']}",
            f"**检查文件数**: {result['total_files']}",
            f"**问题文件数**: {result['error_files']}",
            f"**严重性**: {'🔴 FATAL' if result['fatal'] else '✅ 通过'}",
            ""
        ]

        if result['errors']:
            report_lines.extend([
                "## 发现的错误",
                ""
            ])
            for i, error in enumerate(result['errors'], 1):
                report_lines.extend([
                    f"### 错误 {i}",
                    f"- **文件**: {error['file']}",
                    f"- **行号**: {error.get('line', 'N/A')}",
                    f"- **类型**: {error['type']}",
                    f"- **描述**: {error['message']}",
                    ""
                ])

        if result['warnings']:
            report_lines.extend([
                "## 警告",
                ""
            ])
            for i, warning in enumerate(result['warnings'], 1):
                report_lines.append(f"{i}. {warning['message']}")

        if result['fatal']:
            report_lines.extend([
                "",
                "## 🔴 FATAL级问题",
                "",
                "**影响**: 代码完全无法复现",
                "**建议**: 立即修正所有项目编号后重新检查",
                ""
            ])

        return "\n".join(report_lines)

    def is_fatal(self) -> bool:
        """判断是否为FATAL级问题"""
        result = self.check_all_files()
        return result['fatal']


def main():
    """命令行入口"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='项目编号一致性检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--project-id', help='项目编号（可选，默认从文件夹名提取）')
    parser.add_argument('--output', help='输出报告文件路径')

    args = parser.parse_args()

    checker = ProjectIDChecker(args.project_path, args.project_id)
    report = checker.generate_report()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存到: {args.output}")
    else:
        print(report)

    # FATAL级问题返回退出码1
    sys.exit(1 if checker.is_fatal() else 0)


if __name__ == '__main__':
    main()
