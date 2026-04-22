# 检查模板使用指南

本目录包含针对不同分析类型的检查器模板，均继承 `script_utils/universal_checker.py` 的 `UniversalChecker` 基类。

> 旧版基类 `checker_template.py (AnalysisModuleChecker)` 已移入 `archive/old_docs/`。

---

## 🎯 基类

新检查器应继承 `UniversalChecker`：

```python
from universal_checker import UniversalChecker

class MyChecker(UniversalChecker):
    def check_all(self, config=None):
        ...
        return self.results
```

---

### report_consistency_checker.py
**用途**: 报告一致性检查器模板

**功能**:
- 提取报告中的数值陈述
- 验证陈述与结果文件的一致性
- 检测统计方法描述错误
- 支持多种分析模块（DEG、WGCNA、ML等）

**使用场景**: 检查报告陈述与实际结果的一致性

**示例**:
```python
from templates.report_consistency_checker import ReportConsistencyChecker

checker = ReportConsistencyChecker(project_path, report_text)
checker.check_deg_statements('结果文件/04_DEG/DEG.csv')
checker.check_wgcna_statements({'blue': '结果文件/03_WGCNA/05.blue.csv'})
print(checker.generate_report())
```

**文档**: 见下方"一致性检查器使用指南"

---

## 📋 检查脚本模板

### 1. check_structure.py
**用途**: 项目结构完整性检查
**适用**: 所有项目

### 2. check_deg.py
**用途**: 差异表达基因分析检查
**适用**: 转录组、单细胞项目

### 3. check_ml.py
**用途**: 机器学习筛选检查
**适用**: 使用机器学习的项目

### 4. check_clinical.py ✅ NEW (v4.4)
**用途**: 临床统计分析检查（基线→Logistic→列线图→ML 建模）
**适用**: 临床数据分析项目
**继承**: UniversalChecker

### 5. check_scrna.py ✅ NEW (v4.4)
**用途**: 单细胞 RNA-seq 分析检查
**检查内容**:
- QC 过滤参数
- 降维聚类（UMAP/tSNE）
- 细胞类型注释
- Marker 基因方向性
- monocle 轨迹分析
- CellChat 细胞通讯
- 空间转录组映射
- 上下游基因集数据流一致性（P0 级）

**适用**: 单细胞项目
**继承**: UniversalChecker

### 6. check_gwas_mr.py ✅ NEW (v4.4)
**用途**: GWAS / 孟德尔随机化 (MR) 分析检查
**检查内容**:
- GWAS 数据来源
- 工具变量 (IV) 筛选条件（r², kb, F 统计量）
- MR 五种方法完整性（IVW / MR-Egger / Weighted median / Simple mode / Weighted mode）
- 敏感性检验 P 值方向（MR-Egger截距 / HEIDI / Cochrane's Q）
- 暴露因素完整性
- 多效性/异质性检验

**适用**: GWAS / MR 项目
**继承**: UniversalChecker

---

> ⚠️ 旧基类 `checker_template.py` (AnalysisModuleChecker) 已归档至 `archive/old_docs/`。
> 新模板请基于 `universal_checker.py` (UniversalChecker) 或 `report_consistency_checker.py`。

---

## 📖 一致性检查器使用指南

### report_consistency_checker.py 使用方法

#### 基本使用

```python
from templates.report_consistency_checker import ReportConsistencyChecker

# 读取报告文本
with open('check_reports/report_text.txt', 'r', encoding='utf-8') as f:
    report_text = f.read()

# 创建检查器
checker = ReportConsistencyChecker(project_path, report_text)

# 执行各种一致性检查
checker.check_deg_statements('结果文件/04_DEG_GSE117261/DEG_logFC0.5.csv')
checker.check_wgcna_statements({
    'blue': '结果文件/03_WGCNA_GSE117261/05.blue.csv',
    'yellow': '结果文件/03_WGCNA_GSE117261/05.yellow.csv'
})
checker.check_ml_statements({
    'lasso': '结果文件/08_Machine_GSE117261/01_PAH_lasso_genes.csv'
})
checker.check_key_gene_statements('结果文件/11_Nomo/01_final_key_gene.csv')

# 生成报告
print(checker.generate_report())
checker.save_report('consistency_check_report.txt')
```

#### 提供的检查方法

**DEG检查**:
```python
checker.check_deg_statements(
    deg_file='结果文件/04_DEG/DEG.csv',
    logfc_col='log2FoldChange',      # 默认值
    pvalue_col='pvalue',             # 默认值
    logfc_threshold=0.5,             # 默认值
    pvalue_threshold=0.05            # 默认值
)
```

**WGCNA检查**:
```python
checker.check_wgcna_statements({
    'blue': '结果文件/03_WGCNA/05.blue.csv',
    'yellow': '结果文件/03_WGCNA/05.yellow.csv',
    'brown': '结果文件/03_WGCNA/05.brown.csv'
})
```

**机器学习检查**:
```python
checker.check_ml_statements({
    'lasso': '结果文件/08_Machine/01_lasso_genes.csv',
    'svm': '结果文件/08_Machine/04_svm_genes.csv',
    'rf': '结果文件/08_Machine/10_RF_features.csv'
})
```

**关键基因检查**:
```python
checker.check_key_gene_statements('结果文件/11_Nomo/01_final_key_gene.csv')
```

**细胞类型检查**:
```python
checker.check_celltype_statements('结果文件/02_scRNA/04_celltype/celltype_stats.csv')
```

#### 输出报告格式

```
================================================================================
报告一致性检查报告
================================================================================

【FATAL】问题数量: 1
  ❌ 行0: DEG文件不存在: 结果文件/04_DEG/DEG.csv
     无法验证DEG相关陈述

【SEVERE】问题数量: 3
  ❌ 行234: 共筛选到150个差异表达基因
     报告称150，实际为142
  ❌ 行567: 其中80个上调基因
     报告称80，实际为75
  ❌ 行890: 其中70个下调基因
     报告称70，实际为67

================================================================================
总计: 4 个一致性问题
  FATAL: 1
  SEVERE: 3
================================================================================
```

---

## 💡 最佳实践

### 1. 命名规范
- 检查器类名: `XxxChecker` (如 `DEGChecker`, `WGCNAChecker`)
- 文件名: `check_xxx.py` (如 `check_deg.py`, `check_wgcna.py`)
- 报告文件: `xxx_check_report.txt`

### 2. 错误级别
- `fatal`: 致命错误，必须修正才能继续
- `severe`: 严重错误，严重影响结果可信度
- `moderate`: 中等错误，影响结果质量
- `minor`: 轻微错误，小问题
- `info`: 信息提示

### 3. 检查顺序
建议的检查顺序：
1. 文件存在性检查 (`check_file_existence`)
2. 数据完整性检查 (`check_data_integrity`)
3. 数值一致性检查 (`check_value_consistency`)
4. 统计方法检查 (`check_statistical_methods`)

### 4. 日志记录
- 使用 `self.log()` 方法记录所有发现
- 提供准确的位置信息（文件路径或行号）
- 使用清晰的描述性消息

---

## 📚 相关文档

- **主框架**: [../README.md](../README.md)
- **工具脚本**: [../scripts/README.md](../scripts/README.md)
- **使用示例**: [../examples/README.md](../examples/README.md)
- **工作流程**: [../WORKFLOW.md](../WORKFLOW.md)
- **检查清单**: [../CHECKLIST_TEMPLATE.md](../CHECKLIST_TEMPLATE.md)

---

## 🆕 更新日志

**2026-02-03**
- 添加基类模板 `checker_template.py`
- 添加一致性检查器模板 `report_consistency_checker.py`
- 更新模板使用文档

**2025-XX-XX**
- 创建原始模板文档

---

## 🔧 如何使用模板

### 方法1: 直接使用

```python
from templates.check_deg import DEGChecker

checker = DEGChecker(project_path)
checker.check_all()
```

### 方法2: 继承和定制

```python
from templates.check_deg import DEGChecker

class MyDEGChecker(DEGChecker):
    """定制化的DEG检查器"""
    
    def check_custom_threshold(self):
        """添加自定义阈值检查"""
        # 你的定制逻辑
        pass
```

### 方法3: 复制和修改

1. 复制模板到项目检查目录
2. 根据项目特点修改
3. 测试和验证

---

## 📝 模板开发规范

### 基本结构

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[模板名称]
[用途描述]
"""

from common.universal_checker import UniversalChecker

class TemplateChecker(UniversalChecker):
    """模板检查器"""
    
    def __init__(self, project_path, project_id="Unknown"):
        super().__init__(project_path, project_id)
    
    def check_all(self):
        """执行所有检查"""
        print(f"=" * 80)
        print(f"[检查名称]")
        print(f"=" * 80)
        
        # 1. 检查点1
        self.check_point_1()
        
        # 2. 检查点2
        self.check_point_2()
        
        # 3. 生成报告
        self._generate_summary()
    
    def check_point_1(self):
        """检查点1"""
        section = "检查点1"
        self.log_info(section, "开始检查")
        # 检查逻辑
    
    def _generate_summary(self):
        """生成总结"""
        print("\n" + "=" * 80)
        print("检查总结")
        print("=" * 80)
        # 总结逻辑


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        project_path = input("请输入项目路径: ")
    
    checker = TemplateChecker(project_path)
    checker.check_all()


if __name__ == "__main__":
    main()
```

### 关键要点

1. **继承UniversalChecker** - 获得所有基础功能
2. **使用标准日志** - log_info/log_warning/log_error
3. **提供main函数** - 支持命令行运行
4. **生成报告** - 自动保存检查结果

---

## 🎨 常用代码片段

### 读取CSV文件

```python
df = self.read_csv_safe(file_path, "文件描述")
if df is not None:
    # 处理数据
    pass
```

### 比较数字

```python
self.compare_numbers(expected, actual, tolerance=0, "项目名称")
```

### 比较基因列表

```python
success, common, only1, only2 = self.compare_gene_lists(
    list1, list2, "列表1名称", "列表2名称"
)
```

### 提取报告文本

```python
text = self.extract_from_docx(report_file)
if text:
    numbers = self.find_numbers_in_report(text, "关键词")
```

---

## 📚 模板示例

### 示例1: DEG检查模板

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DEG分析检查模板
"""

from common.universal_checker import UniversalChecker
from pathlib import Path

class DEGChecker(UniversalChecker):
    """DEG分析检查器"""
    
    def __init__(self, project_path, project_id="Unknown"):
        super().__init__(project_path, project_id)
    
    def check_all(self):
        """执行所有检查"""
        print("=" * 80)
        print("DEG分析检查")
        print("=" * 80)
        
        # 自动查找DEG文件
        deg_files = self.find_files_by_pattern("*DEG*.csv")
        
        if not deg_files:
            self.log_warning("DEG检查", "未找到DEG文件")
            return
        
        # 检查第一个DEG文件
        deg_file = deg_files[0]
        self.log_info("DEG检查", f"检查文件: {deg_file.name}")
        
        # 读取和检查
        df = self.read_csv_safe(deg_file, "DEG文件")
        if df is not None:
            self.check_deg_statistics(df)
    
    def check_deg_statistics(self, df):
        """检查DEG统计"""
        if 'logFC' not in df.columns:
            self.log_error("DEG检查", "缺少logFC列")
            return
        
        total = len(df)
        up = len(df[df['logFC'] > 0])
        down = len(df[df['logFC'] < 0])
        
        self.log_info("DEG统计", f"总数: {total}")
        self.log_info("DEG统计", f"上调: {up}")
        self.log_info("DEG统计", f"下调: {down}")


def main():
    import sys
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    checker = DEGChecker(project_path)
    checker.check_all()


if __name__ == "__main__":
    main()
```

---

## 🔍 模板开发计划

### 待开发模板

- [ ] check_wgcna.py - WGCNA检查
- [ ] check_enrichment.py - 富集分析检查
- [ ] check_network.py - 网络分析检查
- [ ] check_drug.py - 药物预测检查
- [ ] check_docking.py - 分子对接检查
- [ ] check_metabolism.py - 代谢分析检查
- [ ] check_validation.py - 表达验证检查

### 贡献指南

1. 基于UniversalChecker创建新检查器
2. 遵循命名规范：check_[分析类型].py
3. 提供清晰的文档注释
4. 包含使用示例
5. 测试并验证

---

*最后更新: 2026年2月3日*
