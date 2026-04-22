# GitHub 借鉴基准（2026-04）

> 目的：把外部成熟仓库中真正值得借鉴的机制，转成报告审核框架的可执行门禁，而不是只停留在参考链接。

---

## 借鉴对象

### 1. reviewdog
- 仓库：`reviewdog/reviewdog`
- 借鉴点：
  - 把检查结果标准化成统一 issue 流
  - 支持把“检测结果”直接挂到具体上下文，而不是只给总评
- 落地到本框架：
  - 强化 `mechanical_check_result.json` 的结构化问题输出
  - 新增 `MC-015` ~ `MC-018`，让问题更靠近具体失败模式

### 2. reviewdog/action-suggester
- 仓库：`reviewdog/action-suggester`
- 借鉴点：
  - 对“可自动修”的问题给出建议修复，而不是只报错
- 后续可继续落地：
  - 给图号错位、文档模板残留、缺少固定章节这些格式问题做自动修复建议

### 3. policy-bot
- 仓库：`palantir/policy-bot`
- 借鉴点：
  - 规则配置化
  - 共享策略源
  - 用状态检查阻断而不是口头建议
- 落地到本框架：
  - 继续强化 `audit_policy.json` 作为唯一机器策略源
  - 把高风险模块规则继续往“策略即代码”方向推进

### 4. conftest
- 仓库：`open-policy-agent/conftest`
- 借鉴点：
  - 对结构化配置做可执行测试
- 落地到本框架：
  - 当前新增的 `delivery_layout`、`result_roots`、`code_roots` 等元信息，就是朝着“结构化断言”迈的一步
  - 后续可以继续把审核规则写成更显式的 policy tests

### 5. markdownlint-cli2 / markdownlint-github
- 仓库：`DavidAnson/markdownlint-cli2`
- 仓库：`github/markdownlint-github`
- 借鉴点：
  - 文档问题应独立成 lint 层
  - 规则可配置、可复用、可组织级共享
- 落地到本框架：
  - 继续强化最终报告和审核交付件的结构 lint
  - 后续可把 Markdown 规范、标题层级、表格规范继续独立出来

### 6. lychee
- 仓库：`lycheeverse/lychee`
- 借鉴点：
  - 链接检查应该作为独立门禁，而不是人工顺手看
- 后续可继续落地：
  - 检查报告中的数据库链接、参考文献链接、外链是否失效

### 7. super-linter
- 仓库：`super-linter/super-linter`
- 借鉴点：
  - 聚合多个检查器
  - 并行运行
  - 输出统一化
- 落地到本框架：
  - 当前审核框架已经有预检、视觉、收敛、lint 多层结构
  - 后续可以把“文档 lint / 链接检查 / 规则校验”继续做成更多并行层

---

## 已经直接落地的强化项

### 1. 非标准交付结构识别

借鉴了 policy-as-code / config testing 的思路，当前 `parse_project_structure.py` 已新增：
- `delivery_layout`
- `delivery_result_roots`
- `delivery_code_roots`
- `delivery_attachment_roots`

并支持在 `分析结果/`、`结果文件/` 等根目录下继续扫描模块，而不是只看顶层。

### 2. 高风险模块正文-文件-图件断链检查

借鉴了 reviewdog 这种“问题直接落到具体失败点”的模式，当前 `mechanical_checks.py` 已新增：
- `MC-016`

会自动抓：
- 正文写了 MD，但结果目录为空
- 正文写了高风险模块，但没有代码
- 正文出现高风险模块结论，但没有图件支撑

### 3. DEG 文件类型识别

借鉴了结构化配置断言的思路，当前 `mechanical_checks.py` 已新增：
- `MC-015`

不再因为文件位于 `DEG` 目录里，就默认把它当成正式 DEG 结果表。

### 4. docking -> MD 对象一致性检查

借鉴了“规则声明必须可执行校验”的思路，当前 `mechanical_checks.py` 已新增：
- `MC-017`

会自动对照：
- 得分表最低对象
- 正文实际选择对象

### 5. 图号范围连续性检查

借鉴了文档 lint 的思路，当前 `mechanical_checks.py` 已新增：
- `MC-018`

专门抓正文这种：
- `Fig.x-1 ~ Fig.x-3`

但实际中间缺号的情况。

---

## 下一步还值得继续借的方向

1. 借 `action-suggester` 思路，为图号错位、模板残留、固定章节缺失生成自动修复建议。  
2. 借 `lychee` 思路，加外链有效性检查。  
3. 借 `markdownlint-github` 思路，把审核 Markdown 文档规范独立成一层。  
4. 借 `conftest` 思路，把一部分审核规则写成更正式的 policy tests。  
5. 借 `super-linter` 思路，把更多检查器做成可并行层。
