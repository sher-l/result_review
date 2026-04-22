#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
中文文本校对检查器 (P1级)

检测报告中的中文关键术语缺字/错字：
1. 医学术语缺字（如「疫细胞浸润」应为「免疫细胞浸润」）
2. 常见同音错字（如「局势细胞」应为「巨噬细胞」）
3. 生物信息学方法名称错误

基于 26YHB147F 审核经验：'疫细胞浸润' 缺 '免' 字未检出。

作者: 审核框架 v6.5
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from base_project_checker import BaseProjectChecker


class ChineseProofreadingChecker(BaseProjectChecker):
    """中文文本校对检查器"""

    # ── 缺字检测词典 ──
    # 格式: (错误片段, 正确完整形式, 缺失字符描述)
    MISSING_CHAR_RULES: List[Tuple[str, str, str]] = [
        # 免疫相关
        ('疫细胞浸润', '免疫细胞浸润', '缺"免"字'),
        ('疫浸润', '免疫浸润', '缺"免"字'),
        ('疫逃逸', '免疫逃逸', '缺"免"字'),
        ('疫微环境', '免疫微环境', '缺"免"字'),
        ('疫检查点', '免疫检查点', '缺"免"字'),
        ('疫调节', '免疫调节', '缺"免"字'),
        # 转录相关
        ('录组', '转录组', '缺"转"字'),
        ('录因子', '转录因子', '缺"转"字'),
        # 磷酸化相关
        ('酸化修饰', '磷酸化修饰', '缺"磷"字'),
        ('酸化位点', '磷酸化位点', '缺"磷"字'),
        # 凋亡/焦亡
        ('胞凋亡', '细胞凋亡', '缺"细"字'),
        ('胞焦亡', '细胞焦亡', '缺"细"字'),
        ('胞自噬', '细胞自噬', '缺"细"字'),
        ('胞增殖', '细胞增殖', '缺"细"字'),
        ('胞分化', '细胞分化', '缺"细"字'),
        ('胞迁移', '细胞迁移', '缺"细"字'),
        # 基因/蛋白
        ('因表达', '基因表达', '缺"基"字'),
        ('白互作', '蛋白互作', '缺"蛋"字'),
        ('白质互作', '蛋白质互作', '缺"蛋"字'),
        # 分析方法
        ('异表达', '差异表达', '缺"差"字'),
        ('集分析', '富集分析', '缺"富"字'),
        ('线图', '列线图', '缺"列"字'),  # 注意歧义：「折线图」是正确的
        # 疾病
        ('巢癌', '卵巢癌', '缺"卵"字'),
        ('腺癌', '前列腺癌', '缺"前列"'),  # 注意：「腺癌」本身可能是合法术语
    ]

    # ── 同音错字检测 ──
    # 格式: (错误写法, 正确写法)
    HOMOPHONE_RULES: List[Tuple[str, str]] = [
        ('局势细胞', '巨噬细胞'),
        ('巨势细胞', '巨噬细胞'),
        ('拟时间序', '拟时序'),
        ('多能干性', '多能干细胞'),
        ('铁失亡', '铁死亡'),
        ('铜失亡', '铜死亡'),
        ('网路药理学', '网络药理学'),
        ('分子对结', '分子对接'),
        ('生存分折', '生存分析'),
        ('差异分折', '差异分析'),
        ('富积分析', '富集分析'),
    ]

    # 避免误报的排除模式
    _EXCLUDE_CONTEXTS = {
        '线图': [re.compile(r'折线图|曲线图|路线图|虚线图|实线图|箱线图|散点线图|连线图|点线图|热图.*线图')],
        '腺癌': [re.compile(r'乳腺癌|甲状腺癌|胰腺癌|前列腺癌')],
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行中文文本校对"""
        report_text = self.load_report_text()
        if not report_text:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到报告文本',
            }

        self._check_missing_chars(report_text)
        self._check_homophones(report_text)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': 2,
            'failed_checks': len(self.issues),
        }

    def _check_missing_chars(self, text: str):
        """检测缺字"""
        lines = text.split('\n')
        for line_num, line in enumerate(lines, 1):
            for wrong, correct, desc in self.MISSING_CHAR_RULES:
                if wrong not in line:
                    continue
                # 检查排除上下文
                if wrong in self._EXCLUDE_CONTEXTS:
                    excluded = False
                    for exclude_pat in self._EXCLUDE_CONTEXTS[wrong]:
                        if exclude_pat.search(line):
                            excluded = True
                            break
                    if excluded:
                        continue
                # 检查是否完整形式已存在（同一行）
                if correct in line:
                    continue
                self.issues.append({
                    'severity': 'MAJOR',
                    'category': '中文术语缺字',
                    'message': f'发现疑似缺字：「{wrong}」应为「{correct}」（{desc}）',
                    'evidence': {
                        'line': line_num,
                        'context': line.strip()[:120],
                        'wrong': wrong,
                        'correct': correct,
                    },
                })

    def _check_homophones(self, text: str):
        """检测同音错字"""
        lines = text.split('\n')
        for line_num, line in enumerate(lines, 1):
            for wrong, correct in self.HOMOPHONE_RULES:
                if wrong not in line:
                    continue
                self.issues.append({
                    'severity': 'MAJOR',
                    'category': '中文同音错字',
                    'message': f'发现疑似错字：「{wrong}」应为「{correct}」',
                    'evidence': {
                        'line': line_num,
                        'context': line.strip()[:120],
                        'wrong': wrong,
                        'correct': correct,
                    },
                })


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='中文文本校对检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    args = parser.parse_args()

    checker = ChineseProofreadingChecker(args.project_path)
    result = checker.check_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
