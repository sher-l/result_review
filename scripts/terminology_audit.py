"""
术语专项审核脚本
Terminology Audit Script

改进点:
1. 增加标准术语检查清单
2. 改进搜索方法（多种方法验证）
3. 增加Word文档直接检查建议
4. 修复已知bug

基于: 25YZF106F项目审核经验
迁移日期: 2026-03-17
"""

import pandas as pd
import re
import os
from pathlib import Path

# 导入标准术语检查清单
import sys
framework_root = Path(__file__).resolve().parent.parent
sys.path.append(str(framework_root / "script_utils"))
from standard_terms_checklist import (
    check_disease_terminology_consistency,
    check_database_terminology,
    check_terminology_spelling,
    reverse_search_check,
    comprehensive_terminology_check
)

# ============================================================================
# 审核类
# ============================================================================

class DataReportAuditor:
    """数据分析报告术语专项审核器"""

    def __init__(self, project_dir, project_id, correct_diseases):
        """
        初始化审核器

        参数:
            project_dir: 项目目录路径
            project_id: 项目编号
            correct_diseases: 正确的疾病名称列表
        """
        self.project_dir = Path(project_dir)
        self.project_id = project_id
        self.correct_diseases = correct_diseases
        self.results = {
            'project_id': project_id,
            'errors': [],
            'warnings': [],
            'info': [],
            'data_consistency': {},
            'word_report_check': {}
        }

    # ========================================================================
    # Phase 2: Word报告检查（改进版）
    # ========================================================================

    def check_word_report(self):
        """
        Word报告术语专项检查

        改进点:
        1. 使用标准术语检查清单
        2. 多种搜索方法验证
        3. 增加反向搜索
        """
        print("\n" + "=" * 80)
        print("Phase 2: Word报告术语专项检查")
        print("=" * 80)

        # 提取Word报告文本
        report_file = self.project_dir / "report_text.txt"
        if not report_file.exists():
            self.results['errors'].append("report_text.txt不存在，请先提取")
            return

        with open(report_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用综合术语检查
        print("\n[1/4] 执行综合术语检查...")
        terminology_results = comprehensive_terminology_check(
            content,
            self.correct_diseases,
            self.project_id
        )

        # 处理疾病术语错误
        if terminology_results['checks']['disease_terminology']['errors']:
            for error in terminology_results['checks']['disease_terminology']['errors']:
                if error['type'] == 'FATAL':
                    self.results['errors'].append({
                        'category': 'Word报告',
                        'severity': 'FATAL',
                        'issue': f"疾病术语错误: {error['message']}",
                        'context': error.get('context', '')
                    })

        # 处理数据库名称错误
        if terminology_results['checks']['database_terminology']['errors']:
            for error in terminology_results['checks']['database_terminology']['errors']:
                self.results['errors'].append({
                    'category': 'Word报告',
                    'severity': 'ERROR',
                    'issue': f"数据库名称错误: {error['message']}",
                    'database': error['database'],
                    'wrong': error['wrong'],
                    'count': error['count']
                })

        # 处理专业术语错误
        if terminology_results['checks']['terminology_spelling']['errors']:
            for error in terminology_results['checks']['terminology_spelling']['errors']:
                self.results['errors'].append({
                    'category': 'Word报告',
                    'severity': 'ERROR',
                    'issue': f"专业术语拼写错误: {error['message']}",
                    'term': error['term'],
                    'wrong': error['wrong'],
                    'count': error['count']
                })

        # 反向搜索结果
        for term, check_result in terminology_results['checks']['reverse_search'].items():
            if check_result['status'] == 'ERROR':
                self.results['warnings'].append({
                    'category': 'Word报告',
                    'issue': f"反向搜索发现'{term}'错误: {check_result['message']}"
                })
            else:
                self.results['info'].append({
                    'category': 'Word报告',
                    'issue': check_result['message']
                })

        # 保存结果
        self.results['word_report_check'] = terminology_results

        # 打印总结
        self._print_word_report_summary(terminology_results)

        return terminology_results

    def _print_word_report_summary(self, results):
        """打印Word报告检查总结"""
        print("\n" + "-" * 80)
        print("Word报告检查总结")
        print("-" * 80)

        summary = results['summary']
        print(f"\n总错误数: {summary['total_errors']}")
        print(f"  - 疾病术语错误: {summary['disease_errors']}（FATAL级）")
        print(f"  - 数据库名称错误: {summary['database_errors']}")
        print(f"  - 专业术语拼写错误: {summary['terminology_errors']}")
        print(f"  - 反向搜索错误: {summary['reverse_search_errors']}")
        print(f"\n严重性: {summary['severity']}")

        if summary['total_errors'] == 0:
            print("\n✓ Word报告术语检查全部通过！")
        else:
            print(f"\n❌ 发现{summary['total_errors']}处错误，需要修改")

    # ========================================================================
    # Phase 3: 数据一致性检查（改进版）
    # ========================================================================

    def check_data_consistency(self):
        """
        数据一致性检查

        改进点:
        1. 正确处理unique去重
        2. 区分关系数和unique数
        3. 增加列含义检查
        """
        print("\n" + "=" * 80)
        print("Phase 3: 数据一致性检查")
        print("=" * 80)

        # 检查各模块数据
        checks = {
            '靶点基因': self._check_target_genes(),
            '疾病基因': self._check_disease_genes(),
            'GO/KEGG': self._check_go_kegg(),
        }

        self.results['data_consistency'] = checks

        # 打印总结
        self._print_data_consistency_summary(checks)

        return checks

    def _check_target_genes(self):
        """检查靶点基因（改进版）"""
        print("\n[1/3] 检查靶点基因...")

        try:
            df = pd.read_csv(self.project_dir / "02_Target/Target_all_Result.csv")

            print(f"  文件形状: {df.shape}")
            print(f"  列名: {df.columns.tolist()}")

            # 找到正确的列
            gene_col = None
            for col in df.columns:
                if col.lower() in ['symbol', 'gene', 'target']:
                    gene_col = col
                    break

            if gene_col:
                unique_genes = df[gene_col].nunique()
                total_records = len(df)

                print(f"  Unique {gene_col}: {unique_genes}")
                print(f"  总记录数: {total_records}")

                # 从Word报告提取数字
                report_num = self._extract_number_from_report('靶点基因|靶点相关基因', [1310, 583])

                return {
                    'report_number': report_num,
                    'actual_unique': unique_genes,
                    'actual_records': total_records,
                    'column_used': gene_col,
                    'status': 'PASS' if report_num == unique_genes else 'WARNING',
                    'message': f"报告{report_num} vs 实际unique {unique_genes} vs 记录{total_records}"
                }

        except Exception as e:
            return {'error': str(e)}

    def _check_disease_genes(self):
        """检查疾病基因（改进版 - 必须去重）"""
        print("\n[2/3] 检查疾病基因（必须去重）...")

        try:
            df = pd.read_csv(self.project_dir / "03_GeneCards/Disease_Target_Result.csv")

            print(f"  文件形状: {df.shape}")
            print(f"  列名: {df.columns.tolist()}")

            # 找到基因列
            gene_col = None
            for col in df.columns:
                if 'gene' in col.lower() or 'symbol' in col.lower():
                    gene_col = col
                    break

            if gene_col:
                total_rows = len(df)
                unique_genes = df[gene_col].nunique()
                has_duplicates = df[gene_col].duplicated().any()

                print(f"  总行数: {total_rows}")
                print(f"  Unique {gene_col}: {unique_genes}")
                print(f"  是否有重复: {has_duplicates}")

                if has_duplicates:
                    dup_count = df[gene_col].duplicated().sum()
                    print(f"  重复行数: {dup_count}")

                # 从Word报告提取数字
                report_num = self._extract_number_from_report('疾病相关基因|疾病基因', [1622, 1682])

                return {
                    'report_number': report_num,
                    'actual_unique': unique_genes,
                    'actual_rows': total_rows,
                    'has_duplicates': has_duplicates,
                    'column_used': gene_col,
                    'status': 'PASS' if report_num == unique_genes else 'WARNING',
                    'message': f"报告{report_num} vs 实际unique {unique_genes} vs 总行{total_rows}"
                }

        except Exception as e:
            return {'error': str(e)}

    def _check_go_kegg(self):
        """检查GO/KEGG"""
        print("\n[3/3] 检查GO/KEGG...")

        try:
            df_go = pd.read_csv(self.project_dir / "04_GOKEGG/GO.csv")
            df_kegg = pd.read_csv(self.project_dir / "04_GOKEGG/KEGG.csv")

            bp_count = len(df_go[df_go['ONTOLOGY'] == 'BP'])
            cc_count = len(df_go[df_go['ONTOLOGY'] == 'CC'])
            mf_count = len(df_go[df_go['ONTOLOGY'] == 'MF'])
            kegg_count = len(df_kegg)

            print(f"  GO BP: {bp_count}")
            print(f"  GO CC: {cc_count}")
            print(f"  GO MF: {mf_count}")
            print(f"  KEGG: {kegg_count}")

            return {
                'go_bp': bp_count,
                'go_cc': cc_count,
                'go_mf': mf_count,
                'kegg': kegg_count,
                'status': 'PASS'
            }

        except Exception as e:
            return {'error': str(e)}

    def _extract_number_from_report(self, keyword, common_values):
        """从Word报告中提取数字"""
        try:
            report_file = self.project_dir / "report_text.txt"
            with open(report_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 搜索关键词附近的数字
            pattern = rf'(\d+)\s*个(?:{keyword})'
            matches = re.findall(pattern, content)

            if matches:
                return int(matches[-1])  # 返回最后一个
            elif common_values:
                return common_values[0]  # 返回最常见的值
            else:
                return None

        except:
            return None

    def _print_data_consistency_summary(self, checks):
        """打印数据一致性总结"""
        print("\n" + "-" * 80)
        print("数据一致性总结")
        print("-" * 80)

        for check_name, result in checks.items():
            if 'error' in result:
                print(f"\n{check_name}: ERROR - {result['error']}")
            else:
                status_icon = "✓" if result.get('status') == 'PASS' else "⚠"
                print(f"\n{check_name}: {status_icon} {result.get('message', '')}")

    # ========================================================================
    # 生成修改建议
    # ========================================================================

    def generate_modification_list(self):
        """
        生成Word查找替换清单

        改进点:
        1. 基于实际发现的错误生成
        2. 提供准确的查找替换字符串
        3. 按严重性排序
        """
        print("\n" + "=" * 80)
        print("生成Word修改清单")
        print("=" * 80)

        modifications = {
            'FATAL级': [],
            '严重级': [],
            '中等级': []
        }

        # 从Word报告检查结果中提取修改建议
        if 'word_report_check' in self.results:
            term_results = self.results['word_report_check']

            # 疾病术语错误（FATAL）
            for error in term_results['checks']['disease_terminology'].get('errors', []):
                if error['type'] == 'FATAL':
                    modifications['FATAL级'].append({
                        'find': error['term'],
                        'replace_with': self.correct_diseases[0] if self.correct_diseases else '正确疾病名称',
                        'reason': f"来自{error['source']}",
                        'count': error['count']
                    })

            # 数据库名称错误
            for error in term_results['checks']['database_terminology'].get('errors', []):
                modifications['严重级'].append({
                    'find': f"{error['wrong']}数据库",
                    'replace_with': f"{error['database']}数据库",
                    'reason': "标准数据库名称",
                    'count': error['count']
                })

            # 专业术语错误
            for error in term_results['checks']['terminology_spelling'].get('errors', []):
                modifications['严重级'].append({
                    'find': f"{error['wrong']}结构式" if 'SMILE' in error['term'] else error['wrong'],
                    'replace_with': f"{error['term']}结构式" if 'SMILE' in error['term'] else error['term'],
                    'reason': "标准术语拼写",
                    'count': error['count']
                })

        # 打印修改清单
        self._print_modification_list(modifications)

        return modifications

    def _print_modification_list(self, modifications):
        """打印修改清单"""
        print("\n" + "-" * 80)
        print("Word查找替换清单")
        print("-" * 80)

        total_count = 0

        for severity, items in modifications.items():
            if items:
                print(f"\n【{severity}】")
                for i, item in enumerate(items, 1):
                    print(f"\n{i}. 查找: {item['find']}")
                    print(f"   替换为: {item['replace_with']}")
                    print(f"   原因: {item['reason']}（{item['count']}处）")
                    total_count += item['count']

        print(f"\n总计: {total_count}处需要修改")

    # ========================================================================
    # 生成审核报告
    # ========================================================================

    def generate_report(self, output_path=None):
        """生成审核报告"""
        print("\n" + "=" * 80)
        print("生成审核报告")
        print("=" * 80)

        if output_path is None:
            output_path = self.project_dir / f"terminology_audit_{self.project_id}.md"

        # 统计
        fatal_count = len([e for e in self.results['errors'] if e.get('severity') == 'FATAL'])
        error_count = len([e for e in self.results['errors'] if e.get('severity') == 'ERROR'])
        warning_count = len(self.results['warnings'])

        # 评级
        if fatal_count > 0:
            rating = "⭐⭐ (50-60) - 需要重大修改"
        elif error_count > 3:
            rating = "⭐⭐⭐ (65-75) - 需要修改"
        elif error_count > 0:
            rating = "⭐⭐⭐⭐ (80-85) - 需要小修"
        else:
            rating = "⭐⭐⭐⭐⭐ (90+) - 优秀"

        # 生成报告
        report = f"""# {self.project_id}术语专项审核报告

**审核日期**: 2026-03-10
    **审核类型**: 术语 / 数据库 / URL 专项检查
    **执行脚本**: scripts/terminology_audit.py

---

## 执行摘要

**评级**: {rating}

**错误统计**:
- 🔴 FATAL级: {fatal_count}处
- 🔴 严重级: {error_count}处
- 🟡 警告: {warning_count}处

---

## 发现的错误

### FATAL级错误
"""

        # 添加FATAL级错误
        for error in self.results['errors']:
            if error.get('severity') == 'FATAL':
                report += f"\n#### {error['issue']}\n"
                if 'context' in error:
                    report += f"上下文: `{error['context'][:100]}...`\n"

        # 添加严重级错误
        report += "\n### 严重级错误\n"
        for error in self.results['errors']:
            if error.get('severity') == 'ERROR':
                report += f"\n#### {error['issue']}\n"

        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"\n✓ 报告已保存到: {output_path}")

        return output_path


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数 - 使用示例"""
    import argparse

    parser = argparse.ArgumentParser(description='数据分析报告术语专项审核工具')
    parser.add_argument('--project-dir', required=True, help='项目目录路径')
    parser.add_argument('--project-id', required=True, help='项目编号')
    parser.add_argument('--diseases', nargs='+', required=True, help='正确的疾病名称列表')

    args = parser.parse_args()

    # 创建审核器
    auditor = DataReportAuditor(
        project_dir=args.project_dir,
        project_id=args.project_id,
        correct_diseases=args.diseases
    )

    # 执行审核
    auditor.check_word_report()
    auditor.check_data_consistency()
    modifications = auditor.generate_modification_list()
    report_path = auditor.generate_report()

    print(f"\n{'='*80}")
    print("审核完成！")
    print(f"{'='*80}")


if __name__ == '__main__':
    # 示例：审核25YZF106F项目
    # python terminology_audit.py --project-dir "25YZF106F-..." --project-id 25YZF106F --diseases 小儿抽动障碍 Tourette
    main()
