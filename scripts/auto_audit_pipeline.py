#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动检查流水线（审核框架 v6.5入口）

集成所有P0级检查器，自动执行预检查并汇总全部问题：
1. 项目编号一致性检查 (FATAL级)
2. 术语主题匹配检查 (FATAL级)
3. 物种匹配检查 (FATAL级)
4. 标准基因集数量验证
5. 跨模块数据流验证 (FATAL级)
6. 证据完整性与参数完备性检查 (CRITICAL级)

软性评估：发现FATAL也继续检查，输出完整问题清单

作者: 审核框架 v6.5
创建日期: 2026-02-13
"""

import sys
import json
import shutil
import zipfile
import re
from pathlib import Path
from datetime import datetime

# 添加script_utils到路径
SCRIPT_DIR = Path(__file__).parent.parent / 'script_utils'
sys.path.insert(0, str(SCRIPT_DIR))

# 添加scripts到路径（用于导入 extract_report）
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from check_orchestrator import CheckOrchestrator
    from quality_gate import QualityGate, QualityGateBuilder
    from utils import extract_project_id
    from audit_runtime import (
        append_event,
        build_case_manifest,
        detect_html_path,
        update_case_manifest,
        write_json,
    )
except ImportError as e:
    print(f"错误: 无法导入模块: {e}")
    print(f"请确保在项目根目录下运行此脚本")
    sys.exit(1)


class AutoAuditPipeline:
    """自动审核流水线"""

    def __init__(self, project_path: str, project_type: str = None, review_dir: str = None,
                 source_archive_path: str | None = None, review_lane: str = "standard"):
        """
        初始化流水线

        参数:
            project_path: 项目根目录路径
            project_type: 项目疾病类型（可选，None则自动推断）
            review_dir: 审核输出根目录（可选，默认 result_review_report）
        """
        self.project_path = Path(project_path)
        self.source_archive_path = Path(source_archive_path) if source_archive_path else None
        self.project_type = project_type or self._infer_project_type()
        self._custom_review_root = Path(review_dir) if review_dir else None
        self.review_lane = review_lane
        self.start_time = datetime.now()
        self.results = {}
        self.docx_only = False  # 自动检测后设置

    @staticmethod
    def normalize_project_input(project_input: Path) -> Path:
        """支持传入 zip：自动解压到 raw/待审核/<项目编号> 并返回项目目录。"""
        if project_input.is_dir():
            return project_input

        if project_input.is_file() and project_input.suffix.lower() == '.zip':
            workspace_root = Path(__file__).resolve().parents[2]
            pending_root = workspace_root / 'raw' / '待审核'
            pending_root.mkdir(parents=True, exist_ok=True)

            project_id = extract_project_id(project_input.stem)
            target_dir = pending_root / project_id
            target_dir.mkdir(parents=True, exist_ok=True)

            print(f"📦 检测到 ZIP，解压到: {target_dir}")
            with zipfile.ZipFile(project_input, 'r') as zf:
                zf.extractall(target_dir)

            children = [p for p in target_dir.iterdir() if p.name != '__MACOSX']
            if len(children) == 1 and children[0].is_dir():
                return children[0]
            return target_dir

        return project_input

    @staticmethod
    def resolve_pending_project_root(project_path: Path) -> Path | None:
        """定位 raw/待审核 下应整体移动的项目根目录。

        兼容两种输入：
        1. 直接目录：raw/待审核/<项目目录>
        2. ZIP 解压后的内层目录：raw/待审核/<项目编号>/<项目目录>
        """
        current = project_path
        while True:
            parent = current.parent
            if parent == current:
                return None
            if parent.name == '待审核':
                return current
            current = parent

    def move_to_ai_reviewed(self) -> Path | None:
        """审核完成后将 raw/待审核/<项目目录> 及其原始 ZIP 自动移动到 raw/已AI审核一次/。"""
        project_dir = self.resolve_pending_project_root(self.project_path)
        if project_dir is None or not project_dir.exists():
            return None

        raw_root = project_dir.parent.parent
        target_root = raw_root / '已AI审核一次'
        target_root.mkdir(parents=True, exist_ok=True)

        dst = target_root / project_dir.name
        if dst.exists():
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = target_root / f"{project_dir.name}_{stamp}"

        shutil.move(str(project_dir), str(dst))
        self._move_source_archive(target_root)
        return dst

    def _move_source_archive(self, target_root: Path) -> Path | None:
        """如原始输入为 raw/待审核 下的 ZIP，则一并移动到 raw/已AI审核一次。"""
        archive = self.source_archive_path
        if archive is None or not archive.exists():
            return None
        if archive.suffix.lower() != '.zip':
            return None
        if archive.parent.name != '待审核':
            return None

        destination = target_root / archive.name
        if destination.exists():
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            destination = target_root / f"{archive.stem}_{stamp}{archive.suffix}"

        shutil.move(str(archive), str(destination))
        return destination

    # 文件夹名关键词 → 项目类型映射（默认值，优先被 standards/disease_types.json 覆盖）
    _DEFAULT_TYPE_KEYWORDS = {
        '癌症': [
            '癌', '瘤', '肉瘤', 'TCGA', '转录组+单细胞',
            'LIHC', 'PAAD', 'LUAD', 'LUSC', 'BRCA', 'STAD',
            'COAD', 'READ', 'KIRC', 'BLCA', 'HNSC', 'GBM',
            'OV', 'UCEC', 'THCA', 'PRAD', 'SKCM', 'ESCA',
        ],
        '肾结石': ['肾结石', '尿石', '草酸钙', '兰德尔斑块'],
        '心血管': ['心肌', '心血管', '动脉粥样硬化', '心力衰竭', '心衰',
                  '脑卒中', '缺血性脑', '脑梗'],
        '免疫': ['脓毒症', '免疫', '干扰素', '炎症', '自身免疫',
                '系统性红斑狼疮', 'SLE'],
        '代谢': ['糖尿病', '肥胖', '代谢', '脂肪肝', 'NAFLD', 'NASH',
                'PCOS', '多囊卵巢', '胰岛素抵抗'],
        '神经': ['阿尔茨海默', '帕金森', '癫痫', '神经退行', '抑郁',
                '精神分裂', '抽动障碍'],
        'IBD': ['溃疡性结肠炎', '克罗恩', '炎症性肠病', 'IBD', '结肠炎'],
    }

    @classmethod
    def _load_type_keywords(cls) -> dict:
        """从 JSON 加载疾病类型关键词；加载失败时回退内置默认值。"""
        config_path = Path(__file__).resolve().parents[1] / 'standards' / 'disease_types.json'
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception as e:
            print(f"⚠️ disease_types.json 加载失败，使用默认关键词: {e}")
        return cls._DEFAULT_TYPE_KEYWORDS

    def _infer_project_type(self) -> str | None:
        """从项目文件夹名推断疾病类型"""
        folder = self.project_path.name
        type_keywords = self._load_type_keywords()
        for ptype, keywords in type_keywords.items():
            for kw in keywords:
                if kw in folder:
                    return ptype
        return None

    def run(self, stop_on_fatal: bool = False) -> dict:
        """
        执行自动检查流水线

        参数:
            stop_on_fatal: 兼容旧参数，当前默认不中断并继续汇总全部问题

        返回:
            {
                'success': 是否成功完成,
                'can_proceed': 是否可以继续逐项证据复核,
                'fatal_triggered': 是否发现FATAL级问题,
                'summary': 汇总信息,
                'report_path': 报告文件路径
            }
        """
        print("\n" + "="*70)
        print(" "*20 + "审核框架 v6.5 - 自动化检查流水线")
        print("="*70)
        print(f"\n项目路径: {self.project_path}")
        print(f"项目类型: {self.project_type or '自动检测'}")
        print(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("质量评估: 软性模式（继续检查并汇总全部问题）")
        print("="*70 + "\n")

        # Step 0：报告文本提取（含内联图片标记）
        print("\n" + "─"*70)
        print("📄 阶段0: 报告文本提取 (docx → report_text.txt + images/)")
        print("─"*70)
        self._extract_report_text()

        # Step 0.5：Layer 0 预解析 + 机械检查
        print("\n" + "─"*70)
        print("🔍 阶段0.5: Layer 0 预解析 + 机械检查")
        print("─"*70)
        self._run_layer0_checks()

        # 仅文档模式提示
        if self.docx_only:
            print("\n" + "─"*70)
            print("📄 当前为仅文档审核模式")
            print("   部分依赖代码/结果文件的检查器将自动跳过")
            print("─"*70)

        # 第一步：Auto-Precheck阶段（P0级FATAL检查）
        print("\n" + "─"*70)
        print("📋 阶段1: Auto-Precheck (P0级FATAL检查)")
        print("─"*70)

        orchestrator = CheckOrchestrator(
            str(self.project_path), self.project_type,
            review_dir=str(self._review_dir) if hasattr(self, '_review_dir') else None
        )
        summary = orchestrator.run_all_checks(stop_on_fatal=stop_on_fatal)

        # 构建质量评估
        gate_builder = QualityGateBuilder()
        for priority_results in orchestrator.results.values():
            for check_result in priority_results:
                if 'result' in check_result:
                    gate_builder.add_from_check_result(check_result['name'], check_result.get('result', {}))

        # 将 Layer 0 机械检查结果也纳入质量评估
        mc_result_path = self._review_dir / 'mechanical_check_result.json' if hasattr(self, '_review_dir') else None
        if mc_result_path and mc_result_path.exists():
            import json as _json
            try:
                mc_data = _json.loads(mc_result_path.read_text(encoding='utf-8'))
                gate_builder.add_from_mechanical_checks(mc_data)
            except (_json.JSONDecodeError, ValueError, OSError) as e:
                print(f"  ⚠️ 机械检查结果解析失败: {e}")

        quality_gate = gate_builder.build()
        gate_status = quality_gate.get_status()

        # 记录结果
        self.results['orchestrator'] = summary
        self.results['quality_gate'] = gate_status

        # 显示最终状态
        self._print_final_status(gate_status)

        # 生成报告
        report_path = self._save_report(orchestrator, quality_gate)

        # 生成 AI 执行围栏与三路 prompt
        guardrail_path = self._prepare_ai_guardrails()
        if hasattr(self, '_review_dir') and self._review_dir.exists():
            append_event(
                self._review_dir,
                "auto_precheck_completed",
                actor="auto_audit_pipeline",
                outputs=[
                    str(self._review_dir / 'report_structure.json'),
                    str(self._review_dir / 'project_structure.json'),
                    str(self._review_dir / 'mechanical_check_result.json'),
                    str(self._review_dir / 'case_manifest.json'),
                    str(self._review_dir / 'review_event_log.jsonl'),
                ],
                details={
                    "project_type": self.project_type or "",
                    "review_lane": self.review_lane,
                    "docx_only": self.docx_only,
                    "can_proceed": gate_status['can_proceed'],
                },
            )

        # 计算耗时
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        return {
            'success': True,
            'can_proceed': gate_status['can_proceed'],
            'fatal_triggered': gate_status.get('has_fatal', False),
            'docx_only': self.docx_only,
            'summary': {
                'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'duration_seconds': duration,
                'duration_formatted': f"{duration//60}分{duration%60}秒"
            },
            'report_path': report_path,
            'guardrail_manifest': guardrail_path,
            'audit_state_path': str(self._review_dir / 'audit_state.json') if hasattr(self, '_review_dir') else None,
            'quality_gate_status': gate_status
        }

    def _extract_report_text(self):
        """Step 0: 从 docx 提取报告文本（含内联图片标记），保存到 review 目录"""
        # 查找 docx 文件（根目录 + 常见子目录）
        docx_files = [
            f for f in self.project_path.glob('*.docx')
            if not f.name.startswith('~$') and '审核' not in f.name
        ]
        if not docx_files:
            for subdir_name in ('result', 'Result', '结果文件', '结果', '报告', 'report', 'Report'):
                subdir = self.project_path / subdir_name
                if subdir.is_dir():
                    docx_files.extend(
                        f for f in subdir.glob('*.docx')
                        if not f.name.startswith('~$') and '审核' not in f.name
                    )
        if not docx_files:
            print("  ⚠️ 未找到 .docx 文件，跳过报告提取")
            return

        # 优先选不含"审核"的主报告（取最大文件）
        docx_path = max(docx_files, key=lambda f: f.stat().st_size)
        print(f"  📄 DOCX: {docx_path.name}")

        # 确定输出目录
        project_id = extract_project_id(self.project_path.name)
        workspace_root = Path(__file__).resolve().parents[2]
        review_root = self._custom_review_root or (workspace_root / 'result_review_report')
        review_dir = review_root / project_id
        review_dir.mkdir(parents=True, exist_ok=True)
        append_event(
            review_dir,
            "report_extraction_started",
            actor="auto_audit_pipeline",
            inputs=[str(docx_path)],
        )

        try:
            from extract_report import extract_report
            text_path, img_dir, img_count = extract_report(docx_path, review_dir)
            self.results['extract'] = {
                'docx': str(docx_path.name),
                'text_path': str(text_path),
                'image_count': img_count,
            }
            print(f"  ✅ 提取完成: {text_path.name} + {img_count} 张图片（内联标记）")
            append_event(
                review_dir,
                "report_extraction_completed",
                actor="auto_audit_pipeline",
                inputs=[str(docx_path)],
                outputs=[str(text_path), str(img_dir)],
                details={"image_count": img_count},
            )
        except Exception as e:
            print(f"  ⚠️ 报告提取失败: {e}")
            self.results['extract'] = {'error': str(e)}
            append_event(
                review_dir,
                "report_extraction_failed",
                actor="auto_audit_pipeline",
                status="error",
                inputs=[str(docx_path)],
                details={"error": str(e)},
            )

    def _run_layer0_checks(self):
        """Step 0.5: Layer 0 预解析 + 机械检查"""
        # 确定 review 目录
        project_id = extract_project_id(self.project_path.name)
        workspace_root = Path(__file__).resolve().parents[2]
        review_root = self._custom_review_root or (workspace_root / 'result_review_report')
        self._review_dir = review_root / project_id

        report_text_path = self._review_dir / 'report_text.txt'
        if not report_text_path.exists():
            print("  ⚠️ report_text.txt 不存在，跳过 Layer 0")
            return

        # 1. 结构化预解析
        try:
            from parse_report_structure import parse_report
            structure = parse_report(report_text_path)
            structure_path = self._review_dir / 'report_structure.json'
            write_json(structure_path, structure)
            meta = structure['metadata']
            n_mismatch = len(structure.get('figure_mismatches', []))
            n_anomaly = len(structure.get('chinese_anomalies', []))
            print(f"  ✅ 预解析: {meta['total_sections']}章节, "
                  f"{meta['total_figures']}图引用(不匹配:{n_mismatch}), "
                  f"{meta['total_genes']}基因, {n_anomaly}中文异常")
            self.results['layer0_parse'] = {
                'structure_path': str(structure_path),
                'sections': meta['total_sections'],
                'figures': meta['total_figures'],
                'figure_mismatches': n_mismatch,
                'chinese_anomalies': n_anomaly,
            }
        except Exception as e:
            print(f"  ⚠️ 预解析失败: {e}")
            self.results['layer0_parse'] = {'error': str(e)}
            return

        # 2. 项目目录结构解析
        try:
            from parse_project_structure import parse_project
            proj_struct = parse_project(self.project_path)
            proj_struct_path = self._review_dir / 'project_structure.json'
            write_json(proj_struct_path, proj_struct)
            pm = proj_struct['metadata']
            has_code = pm['total_code_files'] > 0
            has_data = pm['total_data_files'] > 0
            print(f"  ✅ 项目结构: {pm['total_modules']}模块, "
                  f"{pm['total_code_files']}代码, {pm['total_data_files']}数据, "
                  f"{pm['total_images']}图片, {len(pm['all_packages'])}包, "
                  f"{len(proj_struct['geo_references'])}个GEO引用")
            if not has_code and not has_data:
                self.docx_only = True
                print("  📄 仅文档模式: 未检测到代码或数据文件，D4(可追溯性)和D6(方法-代码一致性)将跳过")
                print("  ⚠️ 最终报告需标注「代码不可复现风险」")
            elif not has_code:
                self.docx_only = True
                print("  📄 仅文档+数据模式: 未检测到代码文件，D6(方法-代码一致性)将跳过")
            self.results['layer0_project'] = {
                'structure_path': str(proj_struct_path),
                'modules': pm['total_modules'],
                'code_files': pm['total_code_files'],
                'config_files': pm.get('total_config_files', 0),
                'packages': len(pm['all_packages']),
                'geo_refs': len(proj_struct['geo_references']),
                'docx_only': self.docx_only,
            }
            manifest = build_case_manifest(
                review_dir=self._review_dir,
                project_dir=self.project_path,
                report_structure=structure,
                project_structure=proj_struct,
                source_archive_path=self.source_archive_path,
                review_lane=self.review_lane,
                docx_only=self.docx_only,
            )
            write_json(self._review_dir / 'case_manifest.json', manifest)
            append_event(
                self._review_dir,
                "case_manifest_created",
                actor="auto_audit_pipeline",
                outputs=[str(self._review_dir / 'case_manifest.json')],
                details={
                    "project_id": manifest["project_id"],
                    "review_lane": self.review_lane,
                    "total_modules": pm['total_modules'],
                },
            )
        except Exception as e:
            # 检测是否是因为目录只有 docx 文件
            non_docx = [f for f in self.project_path.iterdir()
                        if f.is_file() and f.suffix.lower() != '.docx' and not f.name.startswith('~$')]
            subdirs = [d for d in self.project_path.iterdir() if d.is_dir()]
            if not non_docx and not subdirs:
                self.docx_only = True
                print(f"  📄 仅文档模式: 项目目录仅包含 docx 文件，无结果目录")
                print(f"  ⚠️ D4(可追溯性)和D6(方法-代码一致性)将跳过，最终报告需标注「代码不可复现风险」")
            else:
                print(f"  ⚠️ 项目结构解析失败: {e}")
            self.results['layer0_project'] = {'error': str(e), 'docx_only': self.docx_only}

        # 3. 机械检查
        try:
            from mechanical_checks import run_all_checks, format_report
            result = run_all_checks(structure_path, self.project_path)
            mc_path = self._review_dir / 'mechanical_check_result.json'
            write_json(mc_path, result)
            counts = result['counts']
            print(f"  ✅ 机械检查: {result['total_issues']}个问题 "
                  f"(FATAL:{counts.get('FATAL',0)} CRITICAL:{counts.get('CRITICAL',0)} "
                  f"MAJOR:{counts.get('MAJOR',0)} WARNING:{counts.get('WARNING',0)} "
                  f"INFO:{counts.get('INFO',0)})")
            # 输出 FATAL/CRITICAL 问题概要
            for issue in result['issues']:
                if issue['severity'] in ('FATAL', 'CRITICAL'):
                    icon = '💀' if issue['severity'] == 'FATAL' else '🔴'
                    print(f"     {icon} [{issue['code']}] {issue['message']}")
            self.results['layer0_mechanical'] = {
                'result_path': str(mc_path),
                'total_issues': result['total_issues'],
                'counts': counts,
            }
        except Exception as e:
            print(f"  ⚠️ 机械检查失败: {e}")
            self.results['layer0_mechanical'] = {'error': str(e)}

        # 4. Layer 2 视觉审核准备
        try:
            from visual_audit import prepare_visual_audit
            va_result = prepare_visual_audit(self._review_dir, self.project_path, review_lane=self.review_lane)
            self.results['layer2_visual'] = va_result
            update_case_manifest(
                self._review_dir,
                {
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "visual_prefilter_ready": bool((self._review_dir / 'visual_prefilter.json').exists()),
                },
            )
        except Exception as e:
            print(f"  ⚠️ Layer 2 视觉审核准备失败: {e}")
            self.results['layer2_visual'] = {'error': str(e)}

    def _print_final_status(self, gate_status: dict):
        """打印最终状态"""
        print("\n" + "="*70)
        print(" "*25 + "最终状态")
        print("="*70)

        # 问题统计
        counts = gate_status['counts']
        print("\n📊 问题统计:")
        print(f"  � FATAL:    {counts.get('FATAL', 0)}")
        print(f"  🔴 CRITICAL: {counts.get('CRITICAL', 0)}")
        print(f"  🟤 MAJOR:    {counts.get('MAJOR', 0)}")
        print(f"  🟡 WARNING:  {counts.get('WARNING', 0)}")
        print(f"  🟢 INFO:     {counts.get('INFO', 0)}")

        # 质量评估结果
        print(f"\n{gate_status['message']}")
        print(f"审核建议: {gate_status.get('review_recommendation', '进入逐项证据复核')}")

        print("\n✅ 自动检查已完成")
        if gate_status.get('has_fatal'):
            print("   已发现FATAL级问题，但未中断；请在逐项证据复核中优先处理")
        else:
            print("   可以继续进行逐项证据复核（Agent Team）")

        print("="*70)

    def _save_report(self, orchestrator, quality_gate) -> str:
        """保存报告"""
        # 创建报告目录
        reports_dir = self.project_path / 'check_reports' / 'auto_audit'
        reports_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名（包含时间戳）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = reports_dir / f'auto_audit_report_{timestamp}.md'

        # 生成报告内容
        report_lines = [
            "# 自动化检查报告",
            "",
            orchestrator.generate_report(),
            "\n\n",
            "---",
            "\n\n",
            quality_gate.generate_report()
        ]

        # 保存
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))

        # 同时保存JSON格式
        json_file = reports_dir / f'auto_audit_result_{timestamp}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'pipeline_status': self.results,
                'checker_details': orchestrator.results,
                'quality_gate': quality_gate.get_status(),
                'timestamp': timestamp
            }, f, ensure_ascii=False, indent=2)

        print(f"\n📄 报告已保存:")
        print(f"   Markdown: {report_file}")
        print(f"   JSON: {json_file}")

        return str(report_file)

    def _prepare_ai_guardrails(self) -> str | None:
        """为正式审核生成 AI 可执行围栏和三路 prompt。"""
        if not hasattr(self, '_review_dir') or not self._review_dir.exists():
            return None

        guardrail_script = Path(__file__).parent / 'prepare_ai_audit_guardrails.py'
        if not guardrail_script.exists():
            print("⚠️ prepare_ai_audit_guardrails.py 未找到，跳过 AI 围栏生成")
            return None

        try:
            from subprocess import run
            cmd = [
                sys.executable,
                str(guardrail_script),
                str(self._review_dir),
                '--project-dir',
                str(self.project_path),
            ]
            completed = run(cmd, capture_output=True, text=True, encoding='utf-8')
            if completed.returncode != 0:
                print(f"⚠️ AI 围栏生成失败: {completed.stderr.strip() or completed.stdout.strip()}")
                return None
            if completed.stdout.strip():
                print(completed.stdout.strip())
            manifest_path = self._review_dir / 'ai_execution_manifest.json'
            if self.source_archive_path is not None and manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                    manifest.setdefault('paths', {})['source_archive_path'] = str(self.source_archive_path)
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                except Exception as e:
                    print(f"⚠️ 写入 source_archive_path 失败: {e}")
            if manifest_path.exists():
                append_event(
                    self._review_dir,
                    "ai_guardrails_prepared",
                    actor="auto_audit_pipeline",
                    outputs=[str(manifest_path)],
                )
            return str(manifest_path)
        except Exception as e:
            print(f"⚠️ AI 围栏生成失败: {e}")
            return None

    def infer_final_report_dir(self) -> Path | None:
        """推断 result_review_report/<项目编号> 目录。

        仅在同一工作区中存在最终审核报告时返回对应目录，避免对纯预检查场景产生副作用。
        """
        workspace_root = Path(__file__).resolve().parents[2]
        report_root = workspace_root / 'result_review_report'
        if not report_root.exists():
            return None

        project_id = extract_project_id(self.project_path.name)
        candidate_dir = report_root / project_id
        for name in ('final_review_report.md', 'REVIEW_REPORT.md',
                      'FINAL_COMPREHENSIVE_REPORT.md'):
            if (candidate_dir / name).exists():
                return candidate_dir
        return None

    @staticmethod
    def ensure_html(report_dir: str) -> bool:
        """在审核报告目录上运行 ensure_review_html.py 补齐 HTML 交付件。

        参数:
            report_dir: result_review_report/<项目编号> 路径

        返回:
            True 如果成功生成或已存在，False 如果失败
        """
        report_dir = Path(report_dir)
        final_md = None
        for name in ('final_review_report.md', 'REVIEW_REPORT.md',
                      'FINAL_COMPREHENSIVE_REPORT.md'):
            candidate = report_dir / name
            if candidate.exists():
                final_md = candidate
                break
        if final_md is None:
            print("ℹ️ 未找到 final_review_report.md 或 REVIEW_REPORT.md，跳过 HTML 导出")
            return False

        ensure_script = Path(__file__).parent / 'ensure_review_html.py'
        if not ensure_script.exists():
            print("⚠️ ensure_review_html.py 未找到，跳过 HTML 导出")
            return False

        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, str(ensure_script), str(report_dir)],
                capture_output=True, text=True, timeout=60,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                html_path = detect_html_path(report_dir)
                print(f"\n📄 HTML 导出完成: {html_path}")
                return True
            else:
                print(f"\n⚠️ HTML 导出失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"\n⚠️ HTML 导出异常: {e}")
            return False

    @staticmethod
    def send_completion_notification(project_id: str, review_dir: Path, html_path: Path | None,
                                     summary: str) -> bool:
        """审核真正完成后尝试发送 webhook 通知。

        若 notification_config.json 不存在或未启用，则安静跳过，不影响主流程。
        """
        notify_script = Path(__file__).parent / 'send_completion_notification.py'
        if not notify_script.exists():
            return False

        import subprocess
        cmd = [
            sys.executable,
            str(notify_script),
            '--task-type', 'audit',
            '--task-name', f'审核完成 {project_id}',
            '--status', 'completed',
            '--summary', summary,
            '--meta', f'项目编号={project_id}',
            '--meta', f'审核目录={review_dir}',
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                encoding='utf-8',
                errors='replace'
            )
            output = (result.stdout or result.stderr or '').strip()
            if output:
                print(f"🔔 {output}")
            return result.returncode == 0 and 'notification sent' in (result.stdout or '')
        except Exception as e:
            print(f"⚠️ 通知发送异常: {e}")
            return False


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='自动检查流水线 - 审核框架 v6.5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础运行（自动检测项目类型）
  python auto_audit_pipeline.py /path/to/project

  # 指定项目类型
  python auto_audit_pipeline.py /path/to/project --project-type 肾结石

    # 默认继续检查并汇总全部问题
    python auto_audit_pipeline.py /path/to/project

流程说明:
  1. Auto-Precheck阶段（5-10分钟）
     - 项目编号一致性检查 (FATAL)
     - 术语主题匹配检查 (FATAL)
     - 跨模块数据流验证 (FATAL)
    - 证据完整性与参数完备性检查 (CRITICAL)

  2. 质量评估
      - 发现FATAL → 继续检查并标记为最高优先级
    - 输出完整问题清单 → 进入逐项证据复核

  3. 生成报告
     - Markdown格式
     - JSON格式（供后续处理）
        """
    )

    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--project-type', '-t',
                      help='项目疾病类型 (肾结石/癌症/心血管/代谢/神经/免疫/IBD)')
    parser.add_argument('--continue-on-fatal', action='store_true',
                      help='兼容旧参数；当前默认即继续检查并汇总全部问题')
    parser.add_argument('--output-dir', '-o',
                      help='报告输出目录（默认: 项目路径/check_reports/auto_audit）')
    parser.add_argument('--review-dir', '-r',
                      help='审核输出根目录（默认: result_review_report）')
    parser.add_argument('--review-lane', choices=('standard', 'strict'), default='standard',
                      help='视觉审核路线（standard=机器预筛+人工分层复核, strict=全量人工复核）')
    parser.add_argument('--auto-move-reviewed', dest='auto_move_reviewed', action='store_true',
                      help='兼容旧参数；归档已拆分到 archive_reviewed_project.py，当前不再由 auto_audit_pipeline 执行')
    parser.add_argument('--no-auto-move-reviewed', dest='auto_move_reviewed', action='store_false',
                      help='兼容旧参数，无实际效果')
    parser.set_defaults(auto_move_reviewed=False)

    args = parser.parse_args()

    # 验证项目路径
    project_path = AutoAuditPipeline.normalize_project_input(Path(args.project_path))
    if not project_path.exists():
        print(f"错误: 项目路径不存在: {project_path}")
        sys.exit(1)

    # 创建并运行流水线
    pipeline = AutoAuditPipeline(
        str(project_path),
        project_type=args.project_type,
        review_dir=args.review_dir,
        source_archive_path=args.project_path,
        review_lane=args.review_lane,
    )

    try:
        if args.continue_on_fatal:
            print("ℹ️ --continue-on-fatal 已无须显式传入，当前默认就是全量检查模式")

        result = pipeline.run(stop_on_fatal=False)

        final_report_dir = pipeline.infer_final_report_dir()
        if final_report_dir is not None:
            html_ok = pipeline.ensure_html(str(final_report_dir))
            html_path = None
            if html_ok:
                project_id_match = re.search(r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b", final_report_dir.name)
                final_project_id = project_id_match.group(0) if project_id_match else final_report_dir.name
                html_path = final_report_dir / f'{final_project_id}_audit_report.html'
                summary = "最终审核报告和 HTML 已生成"
                pipeline.send_completion_notification(final_project_id, final_report_dir, html_path, summary)
            if args.auto_move_reviewed:
                print("ℹ️ auto_move_reviewed 已废弃；请显式运行 archive_reviewed_project.py")
        else:
            print("ℹ️ 当前仅完成预检查，未检测到最终审核报告目录，暂不导出 HTML")

        print("\n✅ 自动检查完成，已输出完整问题清单")
        if result['fatal_triggered']:
            print("   已发现FATAL级问题，请在逐项证据复核中优先处理")
        else:
            print("   下一步: 启动当前主线Agent Team方案进行逐项证据复核")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
