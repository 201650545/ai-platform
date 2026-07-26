# 公考备考系统

**Slug:** `civil-service-exam`
**Group:** `exam`
**Tags:** 公考、备考
**状态:** active

本文件是 `civil-service-exam` 项目的人工编写语义摘要，与 `public/projects/civil-service-exam/` 下由 `sync-project.mjs` 自动生成的机械汇总（`summary.md`）互补。所有表名、字段名、记录数均来源于项目配置 `config/projects/civil-service-exam.yaml` 与同步产出的 `manifest.json` / `schema.json`，未做虚构。

---

## 项目用途

公考备考系统是一个围绕公务员考试（行测、申论等）备考全流程的个人数据中台，把分散在飞书多维表格中的目标管理、知识管理、刷题、真题、经验、解析、陷阱和命题规律统一组织起来，供 AI 工具在无飞书访问权限的情况下读取数据模型、记录和表间关联，进而提供错题归因、薄弱点诊断、当日计划制定和命题趋势研判等分析能力。

它解决的核心问题是：备考数据天然分散在“目标—知识—刷题—真题—经验—规律”多条线索上，单看任何一张表都无法回答“我该重点复习什么”这类问题。本项目通过显式的关联字段把这些线索串成一张可遍历的图。

---

## 核心目标

1. **目标导向**：以 `target-positions` 中的目标岗位为锚点，把竞争比、历年分数线、招录人数等约束转化为复习强度和优先级。
2. **知识可追踪**：以 `knowledge-points` 为知识主干，记录每个知识点的掌握状态、记忆阶段、复习节奏（上次/下次复习、正确次数、学习次数），支撑间隔复习。
3. **刷题可归因**：通过 `practice-records` 与 `past-exam-questions` 的 `关联知识点`，把每一道错题落回具体知识点，避免“错完就忘”。
4. **真题可深挖**：以 `past-exam-questions` 为题源中心，向外连接 `exam-analysis`（深度解析）、`common-traps`（易错陷阱）、`exam-patterns`（命题规律），形成“题—解析—陷阱—规律”的闭环。
5. **计划可执行**：`daily-study-plan` 承载每日计划与实际完成情况，闭环“计划—执行—复盘”。
6. **经验可复用**：`experience-methods` 沉淀方法、口诀与适用场景，供后续计划与错题改进调用。

---

## 主要数据表

本项目共 9 张表，合计 523 条记录。下表中“字段数”与“记录数”以同步产出的 `manifest.json` 为准。

| # | 飞书表名 | Slug | 字段数 | 记录数 | 用途 |
|---|---|---|---|---|---|
| 1 | 目标岗位库 | `target-positions` | 11 | 10 | 维护拟报考岗位及其竞争约束（招录人数、竞争比、历年分数线、考试类型、专业/学历/基层经历要求、工作地点、招录机关），是复习优先级的外部锚点。 |
| 2 | 知识点库 | `knowledge-points` | 12 | 205 | 知识主干表，记录知识点及其所属科目/子模块、重要程度、掌握状态、记忆阶段、学习次数、正确次数、上次/下次复习、笔记，并通过 `关联真题` 反向链接题库。 |
| 3 | 每日学习计划 | `daily-study-plan` | 8 | 40 | 每日计划与执行回填表，包含日期、学习科目、学习内容、计划/实际时长（分钟）、正确率、完成状态、备注。 |
| 4 | 刷题记录 | `practice-records` | 11 | 1 | 日常刷题流水，记录题源、题型、题目内容、你的答案/正确答案、结果、用时（秒）、关联知识点、错因分析、备注。**当前仅 1 条记录，样本极小。** |
| 5 | 真题题库 | `past-exam-questions` | 14 | 128 | 真题主库，含试卷类型、年份、所属科目、题型、题源、题目内容、你的答案/正确答案、结果、用时（秒）、错因分析、关联知识点、ID、备注。是题源中心。 |
| 6 | 经验方法库 | `experience-methods` | 9 | 45 | 方法论沉淀，含经验标题、核心内容、分类、适用场景、标签、来源、实用程度、ID、备注。 |
| 7 | 真题深度解析库 | `exam-analysis` | 10 | 14 | 对部分真题的深度拆解，含题目摘要、题型、考查知识点、出题意图、思维层次、解题思维路径、常见错误分析、变式训练方向、难度等级、关联真题。 |
| 8 | 易错陷阱库 | `common-traps` | 8 | 40 | 易错点与防范方法，含陷阱名称、陷阱类型、所属模块、陷阱描述、错误思路、正确思路、防范口诀、典型真题。 |
| 9 | 命题规律与考点频次 | `exam-patterns` | 8 | 40 | 考点频次与趋势，含考点名称、所属模块、考查频率、近 5 年出现频次、常见出题方式、命题趋势分析、复习优先级、关联知识点。 |

各表完整字段清单见 `public/projects/civil-service-exam/schema.json` 与各表的 `tables/<slug>/fields.json`。

---

## 表之间的关系

关系来自 `schema.json` 中的关联字段解析，均通过飞书多维表格的“关联记录”字段实现。下列关系是本项目分析能力的骨架。

```
                       ┌───────────────────────┐
                       │  knowledge-points     │  (知识主干, 205)
                       │  关联真题 ───────────────────┐
                       └─────────┬─────────────┘     │
                                 │                   │
        ┌────────────────────────┼───────────────────┤
        │                        │                   │
  practice-records        exam-patterns        past-exam-questions  (题源中心, 128)
  关联知识点                关联知识点            ▲   ▲   ▲
  (1 条)                   (40 条)              │   │   │
                                               │   │   │
                                  ┌────────────┘   │   └────────────┐
                                  │                │                │
                          exam-analysis       common-traps     knowledge-points
                          关联真题             典型真题         关联真题 (反向)
                          (14 条)              (40 条)
```

**显式关联（6 条）：**

| 来源表.字段 | 目标表 | 说明 |
|---|---|---|
| `practice-records.关联知识点` | `knowledge-points` | 把每条刷题记录归因到知识点 |
| `past-exam-questions.关联知识点` | `knowledge-points` | 把真题归因到知识点 |
| `exam-analysis.关联真题` | `past-exam-questions` | 深度解析绑定到具体真题 |
| `common-traps.典型真题` | `past-exam-questions` | 陷阱绑定到典型真题 |
| `exam-patterns.关联知识点` | `knowledge-points` | 命题规律/频次绑定到知识点 |
| `knowledge-points.关联真题` | `past-exam-questions` | 知识点反向链接相关真题 |

**隐含的语义关联（非外键，需通过字段值匹配）：**

- `target-positions.考试类型` ↔ `knowledge-points.所属科目` / `past-exam-questions.所属科目`：通过考试科目把岗位与知识/真题对齐。
- `*.所属科目` / `*.所属模块` / `*.子模块`：跨表的科目/模块口径用于聚合，但各表的取值集合未经统一治理，匹配时需注意口径差异。
- `daily-study-plan.学习科目` ↔ `knowledge-points.所属科目`：计划科目与知识科目的对齐。

> 注意：`target-positions` 没有任何外键指向其他表，它与知识/真题体系之间只存在基于“考试类型/科目”取值的弱关联，不能当作强外键使用。

---

## 关键状态和指标

### 状态字段

| 维度 | 字段 | 所在表 | 取值含义 |
|---|---|---|---|
| 知识掌握 | `掌握状态` | `knowledge-points` | 知识点当前的掌握程度（如已掌握/部分掌握/未掌握等，具体取值见 `fields.json` 选项） |
| 记忆阶段 | `记忆阶段` | `knowledge-points` | 间隔复习所处的阶段 |
| 知识重要度 | `重要程度` | `knowledge-points` | 知识点的重要级别 |
| 刷题结果 | `结果` | `practice-records` / `past-exam-questions` | 单题对/错等结果 |
| 计划完成 | `完成状态` | `daily-study-plan` | 当日计划是否完成 |
| 经验实用度 | `实用程度` | `experience-methods` | 方法论的实用级别 |
| 复习优先级 | `复习优先级` | `exam-patterns` | 考点的复习优先级别 |
| 解析难度 | `难度等级` | `exam-analysis` | 真题深度解析的难度级别 |

### 指标字段

| 指标 | 字段 | 所在表 | 用途 |
|---|---|---|---|
| 知识正确次数 | `正确次数` | `knowledge-points` | 知识点累计答对次数，衡量熟练度 |
| 知识学习次数 | `学习次数` | `knowledge-points` | 知识点累计学习次数 |
| 上次/下次复习 | `上次复习` / `下次复习` | `knowledge-points` | 间隔复习节奏判断 |
| 单题用时 | `用时(秒)` | `practice-records` / `past-exam-questions` | 答题速度 |
| 当日正确率 | `正确率` | `daily-study-plan` | 当日学习正确率 |
| 计划/实际时长 | `计划时长(分钟)` / `实际时长(分钟)` | `daily-study-plan` | 时间预算与执行偏差 |
| 考点频次 | `近5年出现频次` / `考查频率` | `exam-patterns` | 命题热度 |
| 岗位竞争 | `竞争比` / `历年分数线` / `招录人数` | `target-positions` | 目标岗位的竞争约束 |

---

## 常见分析问题

下列问题均可仅凭本项目的公开数据回答，并给出推荐的数据遍历路径。

### 1. 哪类题目错误最多？

以 `past-exam-questions` 为主（128 条，样本充足），按 `题型` 和 `所属科目` 聚合 `结果` 为错误的记录，再读取 `错因分析` 与 `关联知识点` 做归因。可进一步沿 `关联知识点` 跳到 `knowledge-points` 查看该知识点的 `掌握状态` / `正确次数`，沿 `knowledge-points.关联真题` 反向查看是否同类题反复错。

`practice-records` 当前仅 1 条，**不能**作为“错误最多”类统计的主体样本，详见“已知限制”。

### 2. 最近刷题表现如何？

分两个口径：

- **逐题表现**：`practice-records`（仅 1 条）+ `past-exam-questions` 中最近 `日期` 的记录，看 `结果`、`用时(秒)`、`错因分析`。
- **每日表现**：`daily-study-plan` 按 `日期` 倒序，看 `正确率`、`完成状态`、`计划时长(分钟)` 与 `实际时长(分钟)` 的偏差、`学习科目` 与 `学习内容`。

由于 `practice-records` 样本极小，“最近刷题表现”应以 `daily-study-plan` 的日级正确率与完成度为主、`past-exam-questions` 的近期记录为辅，并明确标注样本量。

### 3. 哪些知识点需要加强？

按以下优先级合并筛选 `knowledge-points`：

1. `掌握状态` 为薄弱/未掌握，或 `正确次数` 偏低；
2. `下次复习` 已过期（早于今天）或临近；
3. `重要程度` 高；
4. 通过 `关联知识点` 反查 `exam-patterns`，命中 `复习优先级` 高、`近5年出现频次` / `考查频率` 高的考点；
5. 通过 `关联真题` 反查 `past-exam-questions`，确认该知识点是否在真题中反复出现且常错。

最终“需要加强”的知识点 = 掌握弱 ∧ 复习到期/重要 ∧ 命题高频，三者重叠度越高越优先。

### 4. 如何制定当天公考计划？

以 `daily-study-plan` 为计划载体（字段：`日期`、`学习科目`、`学习内容`、`计划时长(分钟)`、`实际时长(分钟)`、`正确率`、`完成状态`、`备注`），按以下顺序排定当日内容：

1. **到期复习**：`knowledge-points` 中 `下次复习` ≤ 今天的知识点；
2. **高频考点**：`exam-patterns` 中 `复习优先级` 高、`考查频率` / `近5年出现频次` 高的考点（经 `关联知识点` 落到具体知识点）；
3. **薄弱补漏**：`掌握状态` 弱、`正确次数` 低、且真题中常错的知识点；
4. **新增推进**：按 `所属科目` / `子模块` 推进未学知识点；
5. **时长预算**：参考目标岗位 `竞争比` / `历年分数线`（来自 `target-positions`）调整当日总时长与科目配比。

执行后回填 `实际时长(分钟)`、`正确率`、`完成状态`。

### 5. 目标岗位与复习重点的关系？

`target-positions` 提供外部约束，**仅用于辅助优先级**，不替代正式招录信息核验：

- `考试类型` 决定需要覆盖的科目范围，与 `knowledge-points.所属科目` / `past-exam-questions.所属科目` 对齐，过滤出与目标岗位相关的知识与真题；
- `竞争比` 与 `历年分数线` 反映上岸难度，用于抬升薄弱科目和高频考点的复习强度与时长预算；
- `招录人数` 影响容错空间（招录人数少则对薄弱项容错更低）；
- `专业要求` / `学历要求` / `基层经历` / `工作地点` / `招录机关` 用于岗位匹配判断，不直接驱动复习内容。

注意：`target-positions` 与其他表之间**没有外键**，上述关联只能基于“考试类型/科目”取值弱匹配，存在口径不一致风险。

### 6. 真题/规律/陷阱和经验应如何联合使用？

四张表围绕 `past-exam-questions` 形成闭环，建议按“做—析—防—练—法”的顺序联合使用：

1. **做**：从 `past-exam-questions` 取题，记录 `你的答案` / `结果` / `用时(秒)` / `错因分析`，并通过 `关联知识点` 落到 `knowledge-points`。
2. **析**：若该题在 `exam-analysis` 中有深度解析（经 `exam-analysis.关联真题` 匹配），读取 `出题意图` / `思维层次` / `解题思维路径` / `常见错误分析` / `变式训练方向` 做归因。
3. **防**：经 `common-traps.典型真题` 找到该题对应的陷阱，读取 `陷阱类型` / `错误思路` / `正确思路` / `防范口诀`，建立防范意识。
4. **练**：按 `exam-patterns`（经 `关联知识点`）的 `常见出题方式` 与 `变式训练方向`（来自 `exam-analysis`）做变式训练。
5. **法**：从 `experience-methods` 按 `分类` / `适用场景` / `标签` 检索可复用的方法与口诀，结合 `实用程度` 判断是否采纳，回写进 `knowledge-points.笔记` 或当日计划 `备注`。

四者关系：`past-exam-questions`（题）→ `exam-analysis`（为什么这么出）→ `common-traps`（为什么会错）→ `exam-patterns`（还会怎么出）→ `experience-methods`（怎么稳）。

---

## 推荐读取顺序

针对首次接入本项目的 AI 工具，推荐按以下顺序读取，逐步建立上下文：

1. `public/projects/civil-service-exam/manifest.json` — 确认表清单、记录数、校验和与 `build_id`，判断数据是否 stale。
2. `public/projects/civil-service-exam/schema.json` — 读取字段类型、选项取值与关联解析，建立数据模型。
3. `public/projects/civil-service-exam/status.json` — 读取 `sync_status` / `is_stale` / `last_success_at`，判断数据时效。
4. 本文件（`summary.md`）— 建立业务语义与表关系认知。
5. `agent-guide.md` — 加载分析规则与禁止推断。
6. 按任务需要读取具体表数据（`tables/<slug>/records-XXXX.json`）。一般分析任务的读取优先级：
   - 诊断类：`knowledge-points` → `past-exam-questions` → `exam-patterns` → `common-traps` → `exam-analysis`；
   - 计划类：`exam-patterns` → `knowledge-points` → `daily-study-plan` → `target-positions`；
   - 错题类：`practice-records` → `past-exam-questions` → `exam-analysis` → `common-traps` → `knowledge-points`。

---

## 数据更新时间与时效性

- **同步层级**：`schedule.tier: hourly`，由 GitHub Actions `sync-hourly.yml`（cron `17 * * * *`）每小时同步一次。
- **时间戳来源**：以 `status.json` 的 `last_success_at` 为准；`build_id`（`manifest.json` / `status.json` / `catalog.json`）反映本次构建版本。
- **staleness 判断**：当 `status.json.sync_status` 为 `failed` 或 `stale`、`is_stale: true` 时，展示的是上一次成功版本，最近一次同步尝试失败。分析前应先检查 `is_stale`。
- **字段级时效**：`knowledge-points.上次复习` / `下次复习` 与 `daily-study-plan.日期` / `practice-records.日期` / `past-exam-questions.年份` 是时间敏感字段；“最近”“到期”等判断必须基于读取时的实际日期，不能基于固定假设。
- **真题年份**：`past-exam-questions.年份` 与 `exam-patterns.近5年出现频次` 中的“5 年”是相对统计口径，使用时应结合数据中的实际年份范围判断覆盖区间。

---

## 数据公开范围

本项目公开数据遵循 Feishu Data Hub 的三层防护：

1. **视图级**：仅导出各表的 `AI 公开导出` 视图（`source.export_view_name`），视图之外的记录与字段不导出。
2. **字段级**：每张表配置显式字段白名单（见 `config/projects/civil-service-exam.yaml` 的 `tables[].fields`），禁止通配符，禁止敏感字段名（由 `lib/config.mjs` 的 `FORBIDDEN_FIELD_NAMES` 强制）。
3. **内容级**：导出时与部署前双重扫描（`lib/security.mjs`），扫描凭证/Token 模式、PII（手机号、身份证、邮箱、银行卡）、高熵字符串、Token 前缀与禁止文件；命中即中止整个部署（`privacy.fail_on_sensitive_content: true`）。

其他公开约束：

- `privacy.require_public_flag: false`：不依赖记录级“是否公开”开关，公开边界完全由视图 + 字段白名单 + 内容扫描决定。
- `privacy.scan_free_text: true` / `privacy.scan_urls: true`：自由文本与 URL 均纳入扫描。
- `compatibility.mirror_to_legacy_root: false`：本项目**不**镜像到旧路径 `/data/`，所有数据仅在 `/projects/civil-service-exam/` 下提供。
- 记录 ID 导出已启用（`export.include_record_id: true`），关联字段以记录 ID 引用，便于 AI 工具做表间跳转。

---

## 已知限制

1. **`practice-records` 样本极小**：当前仅 1 条记录。任何基于该表的统计（错误类型分布、近期正确率、用时分布等）都缺乏统计意义，不能代表总体刷题水平。
2. **`exam-analysis` 覆盖有限**：仅 14 条深度解析，相对 128 条真题覆盖率较低，多数真题没有对应的深度解析。
3. **`target-positions` 无外键**：与知识/真题体系之间只能基于“考试类型/科目”取值弱匹配，且各表科目取值口径未经统一治理，匹配可能遗漏或不一致。
4. **科目/模块口径分散**：`所属科目` / `所属模块` / `子模块` / `学习科目` 分布在不同表中，取值集合未统一，跨表聚合存在口径风险。
5. **状态字段取值依赖选项配置**：`掌握状态` / `记忆阶段` / `重要程度` / `结果` / `完成状态` / `实用程度` / `复习优先级` / `难度等级` 等为选择字段，具体可选取值以各表 `fields.json` 的 `options` 为准，本文件不假定固定枚举。
6. **历史分数线与竞争比为快照**：`target-positions.历年分数线` / `竞争比` 是录入时的快照，不随招录公告自动更新，可能与最新招录情况不符。
7. **自动生成摘要的局限**：`public/projects/civil-service-exam/summary.md` 由代码机械生成，仅含表清单与字段列表，不含业务语义；语义内容以本文件为准。
8. **关联完整性依赖源数据**：关联字段是否填写、是否指向有效记录，取决于飞书源表的录入质量，存在空值或失效引用的可能。

---

## 不应做出的推断

1. **不应以 `practice-records` 推断总体水平**：仅 1 条记录，不足以得出“擅长/不擅长某题型”“近期正确率 X%”等总体结论。
2. **不应把 `target-positions` 当作正式招录信息**：竞争比、分数线、招录人数、专业/学历要求等仅为备考参考，正式报考必须以官方招录公告为准；本数据**不**用于资格核验。
3. **不应假定关联字段必然有值**：`关联知识点` / `关联真题` / `典型真题` 可能为空，未填关联的记录不能强行归因。
4. **不应假定跨表科目取值完全一致**：`所属科目` / `学习科目` / `所属模块` / `子模块` 在不同表中口径可能不同，跨表匹配前应先比对实际取值集合。
5. **不应把 `exam-patterns.近5年出现频次` 当作精确预测**：频次反映历史出现情况，不等于未来命题概率，不能用作“今年必考”的依据。
6. **不应把 `knowledge-points.下次复习` 等间隔复习字段当作硬性日程**：它是个人的复习节奏建议，不是必须执行的合约。
7. **不应在不检查 `status.json.is_stale` 的情况下假定数据为最新**：stale 状态下展示的是旧版本数据。
8. **不应从公开数据反推飞书源表结构**：公开数据受视图与字段白名单裁剪，不代表飞书 Base 的完整结构。
