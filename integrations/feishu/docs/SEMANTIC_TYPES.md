# 语义类型受控词表

> 本文档定义 Feishu Data Hub 语义层使用的三组受控词表：字段语义类型（semantic_type）、表角色（table role）和实体类型（entity_type）。所有值定义在 `lib/semantic.mjs` 中，以封闭枚举形式管理。

---

## 1. 为什么使用受控词表

### 1.1 封闭枚举的意义

受控词表（controlled vocabulary）是一组封闭的、预定义的值集合。语义层使用受控词表而非自由文本的原因：

1. **AI 可靠解析**：AI 代理可以确定性地解析有限的枚举值，而不需要猜测自由文本的含义。
2. **校验可执行**：`validateSemanticConfig()` 可以检查每个映射值是否在词表内，拒绝非法值。
3. **一致性保证**：不同项目的相同语义概念使用相同的类型标签，便于跨项目路由和比较。
4. **文档可维护**：每个值有明确的含义和用法说明（即本文档），避免含义漂移。

### 1.2 词表的定义位置

三组受控词表均定义在 `lib/semantic.mjs` 中，以 JavaScript `Set` 形式声明：

```javascript
export const SEMANTIC_TYPES = new Set([ ... ]);  // 26 个值
export const TABLE_ROLES = new Set([ ... ]);     // 8 个值
export const ENTITY_TYPES = new Set([ ... ]);    // 7 个值
```

校验函数 `validateSemanticConfig()` 在同步时检查所有语义配置中的值是否在这些 Set 中，不在则产生 error 并中止同步。

---

## 2. semantic_type 完整列表

`SEMANTIC_TYPES` 共包含 26 个值。以下按功能分组说明每个类型的含义和典型用法。

### 2.1 标识类

#### entity_identity_title

**含义：** 实体的身份标识/标题字段，用于唯一识别或展示一条记录的主要名称。

**典型用法：** 标记表中最具辨识度的字段，AI 在展示记录时优先使用此字段作为标题。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `单词` |
| learning-english | `text-library` | `文本标题` |
| learning-english | `lexical-units` | `展示名称` |
| civil-service-exam | `knowledge-points` | `知识点` |
| civil-service-exam | `target-positions` | `岗位名称` |
| civil-service-exam | `past-exam-questions` | `ID` |
| civil-service-exam | `experience-methods` | `ID`、`经验标题` |
| civil-service-exam | `common-traps` | `陷阱名称` |
| civil-service-exam | `exam-patterns` | `考点名称` |

#### project_id

**含义：** 项目级标识符字段。

**典型用法：** 当字段值是项目维度的 ID 时使用。当前项目中暂无实际映射，但保留在词表中以支持未来可能的项目级标识需求。

#### task_id

**含义：** 任务级标识符字段。

**典型用法：** 当字段值是单个任务的唯一 ID 时使用。当前项目中暂无实际映射（任务通过 `task_title` 识别），保留以支持未来需求。

### 2.2 任务类

#### task_title

**含义：** 任务的名称/标题。

**典型用法：** 标记计划任务表中描述任务名称的字段。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `study-tasks` | `任务名称` |

#### task_status

**含义：** 任务或计划的当前状态（如待办、进行中、已完成）。

**典型用法：** 标记任务表和计划表中表示完成状态的字段。AI 据此筛选未完成任务或评估完成率。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `daily-plan` | `完成状态` |
| learning-english | `study-tasks` | `状态` |
| learning-english | `study-sessions` | `完成状态` |
| civil-service-exam | `daily-study-plan` | `完成状态` |

#### task_priority

**含义：** 任务或知识项的优先级/重要程度。

**典型用法：** 标记表示优先级或重要性的字段。AI 据此排序待办事项。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `lexical-units` | `重要性` |
| civil-service-exam | `knowledge-points` | `重要程度` |
| civil-service-exam | `exam-patterns` | `复习优先级` |

### 2.3 日期/时间类

#### planned_date

**含义：** 计划日期，表示某项活动被计划执行的日期。

**典型用法：** 标记计划表中表示计划执行日期的字段。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `daily-plan` | `日期` |
| learning-english | `study-tasks` | `计划日期` |
| civil-service-exam | `daily-study-plan` | `日期` |

#### due_date

**含义：** 截止日期，表示任务必须完成的最后期限。

**典型用法：** 标记任务表中表示截止时间的字段。AI 据此判断任务是否逾期。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `study-tasks` | `截止时间` |

#### event_date

**含义：** 事件日期，表示某事件发生的日期。

**典型用法：** 标记日志表和事件表中表示事件发生时间的字段。也用于标记真题的年份属性。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `learning-log` | `日期` |
| learning-english | `vocabulary` | `上次测验` |
| learning-english | `study-sessions` | `日期`、`开始时间`、`结束时间` |
| learning-english | `competency-state` | `最近测试时间`、`最近通过时间` |
| learning-english | `error-remediation` | `首次出现日期`、`最近出现日期` |
| learning-english | `text-library` | `上次使用日期` |
| civil-service-exam | `practice-records` | `日期` |
| civil-service-exam | `knowledge-points` | `上次复习` |
| civil-service-exam | `past-exam-questions` | `年份` |

#### created_at

**含义：** 记录创建时间。

**典型用法：** 标记记录的创建时间戳。当前项目中暂无实际映射（飞书源表未导出创建时间字段），保留以支持未来需求。

#### updated_at

**含义：** 记录最后更新时间。

**典型用法：** 标记记录的最后修改时间戳。当前项目中暂无实际映射，保留以支持未来需求。

#### review_due_at

**含义：** 下次复习到期时间，表示按照间隔重复算法应在此日期复习。

**典型用法：** 标记词汇/知识点/能力表中表示下次复习日期的字段。AI 据此筛选到期复习项——这是复习调度分析的核心字段。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `下次复习` |
| learning-english | `competency-state` | `下次复习时间` |
| learning-english | `text-library` | `最早复用日期` |
| civil-service-exam | `knowledge-points` | `下次复习` |

### 2.4 度量类

#### duration_minutes

**含义：** 持续时长（分钟或秒）。

**典型用法：** 标记表示时间长短的字段。注意：虽然类型名为 `duration_minutes`，但在公考项目中也用于标记以秒为单位的用时字段（如 `用时(秒)`），AI 在解读时需注意单位。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `study-tasks` | `预计时长分钟`、`实际时长分钟` |
| learning-english | `study-sessions` | `输入分钟`、`输出分钟` |
| learning-english | `competency-state` | `间隔天数` |
| civil-service-exam | `practice-records` | `用时(秒)` |
| civil-service-exam | `past-exam-questions` | `用时(秒)` |
| civil-service-exam | `daily-study-plan` | `计划时长(分钟)`、`实际时长(分钟)` |

#### outcome

**含义：** 事件结果（如正确/错误、通过/未通过）。

**典型用法：** 标记日志和刷题表中表示单次事件结果的字段。AI 据此统计正确率和错误分布。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `learning-log` | `结果` |
| civil-service-exam | `practice-records` | `结果` |
| civil-service-exam | `past-exam-questions` | `结果` |

#### score

**含义：** 分数/计数值，表示某种量化指标。

**典型用法：** 标记表示数量、分数或评级的字段。这是一个通用类型，用于不适合用 `accuracy`、`attempt_count` 等更具体类型描述的数值。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `daily-plan` | `复习词数`、`新词数` |
| civil-service-exam | `target-positions` | `招录人数`、`竞争比`、`历年分数线` |
| civil-service-exam | `experience-methods` | `实用程度` |
| civil-service-exam | `exam-patterns` | `考查频率`、`近5年出现频次` |

#### accuracy

**含义：** 正确率/准确率，表示正确数占总数的比例。

**典型用法：** 标记表示正确率的字段。AI 据此评估学习质量。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `daily-plan` | `正确率` |
| civil-service-exam | `daily-study-plan` | `正确率` |

#### attempt_count

**含义：** 尝试次数/累计计数。

**典型用法：** 标记表示累计学习次数、正确次数、错误重复次数等计数字段。AI 据此评估熟练度和错误频率。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `正确次数`、`学习次数` |
| learning-english | `competency-state` | `连续成功次数`、`连续失败次数` |
| learning-english | `text-library` | `使用次数` |
| learning-english | `error-remediation` | `重复次数` |
| civil-service-exam | `knowledge-points` | `正确次数`、`学习次数` |

### 2.5 错误类

#### error_type

**含义：** 错误类型/分类。

**典型用法：** 标记错误日志和刷题表中表示错误分类的字段。AI 据此识别高频错误模式和归因。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `error-remediation` | `错误类型` |
| civil-service-exam | `practice-records` | `错因分析` |
| civil-service-exam | `past-exam-questions` | `错因分析` |
| civil-service-exam | `exam-analysis` | `常见错误分析` |

### 2.6 知识/内容类

#### knowledge_topic

**含义：** 知识主题/分类/科目。

**典型用法：** 标记表示知识分类、科目、模块、题型的字段。AI 据此按主题/科目聚合分析。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `词性` |
| learning-english | `study-tasks` | `任务类型` |
| learning-english | `competency-state` | `能力维度` |
| civil-service-exam | `knowledge-points` | `所属科目`、`子模块` |
| civil-service-exam | `practice-records` | `题型` |
| civil-service-exam | `past-exam-questions` | `试卷类型`、`所属科目`、`题型` |
| civil-service-exam | `daily-study-plan` | `学习科目` |
| civil-service-exam | `exam-analysis` | `题型`、`思维层次`、`考查知识点` |
| civil-service-exam | `common-traps` | `陷阱类型`、`所属模块` |
| civil-service-exam | `exam-patterns` | `所属模块` |
| civil-service-exam | `experience-methods` | `分类`、`标签` |

#### content_text

**含义：** 内容文本，表示自由文本形式的内容字段。

**典型用法：** 标记存储正文、说明、笔记、答案等文本内容的字段。这类字段通常不适合做结构化筛选，但适合展示和语义理解。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `最简中文` |
| learning-english | `learning-log` | `正确答案`、`你的回答` |
| learning-english | `error-remediation` | `原始错误`、`正确形式` |
| civil-service-exam | `practice-records` | `正确答案`、`你的答案`、`题目内容`、`备注` |
| civil-service-exam | `past-exam-questions` | `题目内容`、`正确答案`、`你的答案`、`备注` |
| civil-service-exam | `target-positions` | `工作地点`、`学历要求`、`专业要求`、`基层经历`、`招录机关`、`备注` |
| civil-service-exam | `experience-methods` | `核心内容`、`适用场景`、`备注` |
| civil-service-exam | `exam-analysis` | `题目摘要`、`出题意图`、`解题思维路径`、`变式训练方向` |
| civil-service-exam | `common-traps` | `陷阱描述`、`错误思路`、`正确思路`、`防范口诀` |
| civil-service-exam | `exam-patterns` | `常见出题方式`、`命题趋势分析` |
| civil-service-exam | `knowledge-points` | `笔记` |

#### source_reference

**含义：** 来源引用，表示数据的出处或来源。

**典型用法：** 标记表示题源、来源、出处等字段。AI 据此追溯数据的原始来源。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| civil-service-exam | `practice-records` | `题源` |
| civil-service-exam | `past-exam-questions` | `题源` |
| civil-service-exam | `experience-methods` | `来源` |

#### relation

**含义：** 关联引用，表示指向其他表/记录的关联字段。

**典型用法：** 标记飞书 Bitable 的关联记录字段。AI 据此进行表间跳转和关联查询。这些字段与 `schema.json` 中的 `relation` 信息对应。

**实际映射示例：**

| 项目 | 表 | 字段 | 关联目标 |
|---|---|---|---|
| learning-english | `vocabulary` | `关联文本` | `text-library` |
| learning-english | `vocabulary` | `学习日志` | `learning-log` |
| learning-english | `learning-log` | `关联单词` | `vocabulary` |
| learning-english | `daily-plan` | `单词列表(link)` | `vocabulary` |
| learning-english | `competency-state` | — | — |
| civil-service-exam | `knowledge-points` | `关联真题` | `past-exam-questions` |
| civil-service-exam | `practice-records` | `关联知识点` | `knowledge-points` |
| civil-service-exam | `past-exam-questions` | `关联知识点` | `knowledge-points` |
| civil-service-exam | `exam-analysis` | `关联真题` | `past-exam-questions` |
| civil-service-exam | `common-traps` | `典型真题` | `past-exam-questions` |
| civil-service-exam | `exam-patterns` | `关联知识点` | `knowledge-points` |

### 2.7 状态/评估类

#### status

**含义：** 通用状态字段，表示记录的当前状态。

**典型用法：** 标记不适合用 `task_status`、`mastery_level` 等更具体类型描述的状态字段。如记忆阶段、使用状态、是否已解决等。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `记忆阶段` |
| learning-english | `study-tasks` | `是否延迟任务`、`是否迁移任务` |
| learning-english | `lexical-units` | `队列状态` |
| learning-english | `text-library` | `使用状态` |
| learning-english | `error-remediation` | `是否已解决` |
| civil-service-exam | `knowledge-points` | `记忆阶段` |

#### confidence

**含义：** 置信度/稳定度，表示对某项评估的信心程度。

**典型用法：** 标记表示稳定度、专注度等置信度指标的字段。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `competency-state` | `稳定度` |
| learning-english | `study-sessions` | `专注度` |

#### difficulty

**含义：** 难度等级。

**典型用法：** 标记表示难度分级的字段。AI 据此匹配适合当前水平的内容。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `难度等级` |
| learning-english | `competency-state` | `难度` |
| learning-english | `study-sessions` | `主观难度` |
| learning-english | `text-library` | `难度等级` |
| civil-service-exam | `exam-analysis` | `难度等级` |

#### mastery_level

**含义：** 掌握程度/等级，表示学习者对某知识点/技能的掌握水平。

**典型用法：** 标记表示掌握状态或当前等级的字段。这是评估学习进度的核心字段。AI 据此识别薄弱项。

**实际映射示例：**

| 项目 | 表 | 字段 |
|---|---|---|
| learning-english | `vocabulary` | `掌握状态` |
| learning-english | `competency-state` | `当前等级` |
| civil-service-exam | `knowledge-points` | `掌握状态` |

---

## 3. 表角色（table role）

`TABLE_ROLES` 共包含 8 个值。每个表在语义配置中被赋予一个角色，描述该表在整个数据模型中的职能。

### 3.1 plan（计划表）

**含义：** 承载学习计划与任务的表，记录"应该做什么"。

**特征：**
- 包含 `planned_date`、`task_status` 等日期和状态字段
- 记录数量通常较少（日级计划）
- AI 据此制定和评估学习计划

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `daily-plan` | `task_collection` |
| learning-english | `study-tasks` | `task` |
| civil-service-exam | `daily-study-plan` | `task_collection` |

### 3.2 event_log（事件日志表）

**含义：** 记录学习事件发生的表，记录"实际做了什么"。

**特征：**
- 包含 `event_date`、`outcome` 等事件字段
- 按时间顺序记录
- AI 据此回顾历史活动和分析表现

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `learning-log` | `learning_event` |
| learning-english | `study-sessions` | `learning_event` |
| civil-service-exam | `practice-records` | `learning_event` |

### 3.3 knowledge（知识库表）

**含义：** 存储知识点/词条/词义等知识实体的表，记录"需要学什么"。

**特征：**
- 包含 `entity_identity_title`、`mastery_level`、`review_due_at` 等字段
- 记录数量通常较大（词汇表 6000 条）
- 支撑间隔重复和复习调度

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `vocabulary` | `knowledge` |
| learning-english | `lexical-units` | `knowledge` |
| civil-service-exam | `knowledge-points` | `knowledge` |

### 3.4 metric（指标表）

**含义：** 存储能力/状态指标的表，记录"学得怎么样"。

**特征：**
- 包含 `mastery_level`、`confidence`、`attempt_count` 等指标字段
- 按维度/指标组织，非按时间流水
- AI 据此诊断能力短板

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `competency-state` | `metric` |

### 3.5 content（内容表）

**含义：** 存储学习材料/内容的表，记录"学什么材料"。

**特征：**
- 包含 `entity_identity_title`、`content_text`、`difficulty` 等字段
- 存储文本、题目等内容实体
- AI 据此推荐学习材料

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `text-library` | `content` |
| civil-service-exam | `past-exam-questions` | `content` |

### 3.6 error_log（错误日志表）

**含义：** 记录错误与改进策略的表，记录"犯了什么错、怎么改"。

**特征：**
- 包含 `error_type`、`content_text`（原始错误/正确形式）、`attempt_count`（重复次数）等字段
- 追踪错误的重复和解决状态
- AI 据此识别顽固错误和改进方向

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| learning-english | `error-remediation` | `learning_event` |

### 3.7 reference（参考表）

**含义：** 存储目标、经验、陷阱等参考信息的表，记录"参考资料"。

**特征：**
- 不直接参与学习流水，但为计划和分析提供参考
- 包含 `entity_identity_title`、`content_text` 等字段
- AI 据此获取参考信息辅助决策

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| civil-service-exam | `target-positions` | `reference` |
| civil-service-exam | `experience-methods` | `reference` |
| civil-service-exam | `common-traps` | `reference` |

### 3.8 analysis（分析表）

**含义：** 存储深度分析结论的表，记录"对数据的分析结果"。

**特征：**
- 包含分析性内容（出题意图、命题趋势、考查频次等）
- 不是原始数据，而是对原始数据的加工分析
- AI 据此提供深度分析支持

**实际使用：**

| 项目 | 表 | entity_type |
|---|---|---|
| civil-service-exam | `exam-analysis` | `content` |
| civil-service-exam | `exam-patterns` | `metric` |

---

## 4. 实体类型（entity_type）

`ENTITY_TYPES` 共包含 7 个值。每个表在语义配置中被赋予一个实体类型，描述该表存储的实体种类。

### 4.1 task

**含义：** 单个任务实体。

**特征：** 表中每条记录代表一个独立的可执行任务。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `study-tasks` |

### 4.2 task_collection

**含义：** 任务集合/计划实体。

**特征：** 表中每条记录代表一组任务或一个计划周期（如一天的计划）。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `daily-plan` |
| civil-service-exam | `daily-study-plan` |

### 4.3 learning_event

**含义：** 学习事件实体。

**特征：** 表中每条记录代表一次学习活动的发生（测验、会话、刷题、错误）。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `learning-log` |
| learning-english | `study-sessions` |
| learning-english | `error-remediation` |
| civil-service-exam | `practice-records` |

### 4.4 knowledge

**含义：** 知识实体。

**特征：** 表中每条记录代表一个知识点/词条/词义等需要掌握的知识单元。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `vocabulary` |
| learning-english | `lexical-units` |
| civil-service-exam | `knowledge-points` |

### 4.5 metric

**含义：** 指标实体。

**特征：** 表中每条记录代表一个可度量的能力/状态指标。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `competency-state` |
| civil-service-exam | `exam-patterns` |

### 4.6 content

**含义：** 内容实体。

**特征：** 表中每条记录代表一个学习内容/材料（文本、题目、解析）。

**实际使用：**

| 项目 | 表 |
|---|---|
| learning-english | `text-library` |
| civil-service-exam | `past-exam-questions` |
| civil-service-exam | `exam-analysis` |

### 4.7 reference

**含义：** 参考实体。

**特征：** 表中每条记录代表一个参考信息（目标岗位、经验方法、陷阱）。

**实际使用：**

| 项目 | 表 |
|---|---|
| civil-service-exam | `target-positions` |
| civil-service-exam | `experience-methods` |
| civil-service-exam | `common-traps` |

---

## 5. 添加新类型的规则

### 5.1 何时需要添加新类型

只有在以下情况才应考虑添加新的受控词表值：

1. **现有类型无法准确描述**：当现有 26 个 `semantic_type` 都无法准确描述某字段的业务含义，且该含义在多个字段中重复出现时。
2. **有实际使用场景**：至少有一个项目的至少一个字段需要使用该新类型。不为"可能将来用到"的类型添加枚举。
3. **AI 解析价值明确**：新类型能为 AI 提供现有类型无法提供的语义信息。

### 5.2 添加步骤

1. **评估必要性**：确认现有类型确实无法满足需求。考虑是否能用现有类型的组合或更宽泛的类型覆盖。

2. **选择类型名称**：使用小写蛇形命名（snake_case），名称应自描述。例如 `completion_rate` 而非 `cr`。

3. **修改代码**：在 `lib/semantic.mjs` 的对应 `Set` 中添加新值：

   ```javascript
   export const SEMANTIC_TYPES = new Set([
     // ... 现有值 ...
     "new_type_name",  // 新增
   ]);
   ```

4. **更新本文档**：在新类型所属分类下添加说明，包括含义、典型用法和实际映射示例。

5. **应用映射**：在需要使用新类型的项目的 `config/semantics/<slug>.yaml` 中应用。

6. **运行校验**：

   ```bash
   node scripts/sync-hub.mjs
   node scripts/validate-semantic.mjs
   node scripts/validate-ai-docs.mjs
   ```

7. **确认无 warning**：校验不应产生与新类型相关的 error 或 warning。

### 5.3 不应添加新类型的情况

| 情况 | 应使用 |
|---|---|
| 字段是自由文本 | `content_text` |
| 字段是数量/分数 | `score` |
| 字段是状态 | `status` 或 `task_status` 或 `mastery_level` |
| 字段是日期 | `event_date` 或 `planned_date` 或 `review_due_at` |
| 字段是关联 | `relation` |
| 字段是分类/科目 | `knowledge_topic` |
| 仅一个字段使用的特殊含义 | 考虑用更通用的类型，不为单一字段添加枚举 |

### 5.4 弃用类型

受控词表中不主动"弃用"类型，因为已有项目的语义配置可能引用它。如果某个类型不再被任何项目使用，可以在本文档中标注为"当前无实际映射"，但保留在 `Set` 中以维持向后兼容。只有在进行主版本升级时才考虑移除无引用的类型。

---

## 6. 语义类型使用统计

以下是当前两个项目中各 `semantic_type` 的使用频次统计（基于实际语义配置）。

| semantic_type | learning-english 使用次数 | civil-service-exam 使用次数 | 合计 |
|---|---|---|---|
| `entity_identity_title` | 4 | 7 | 11 |
| `knowledge_topic` | 3 | 13 | 16 |
| `content_text` | 5 | 19 | 24 |
| `relation` | 5 | 6 | 11 |
| `status` | 5 | 1 | 6 |
| `event_date` | 8 | 3 | 11 |
| `attempt_count` | 5 | 2 | 7 |
| `mastery_level` | 2 | 1 | 3 |
| `review_due_at` | 3 | 1 | 4 |
| `difficulty` | 4 | 1 | 5 |
| `task_status` | 3 | 1 | 4 |
| `planned_date` | 2 | 1 | 3 |
| `duration_minutes` | 5 | 4 | 9 |
| `outcome` | 1 | 2 | 3 |
| `score` | 2 | 5 | 7 |
| `error_type` | 1 | 3 | 4 |
| `task_priority` | 1 | 2 | 3 |
| `accuracy` | 1 | 1 | 2 |
| `confidence` | 2 | 0 | 2 |
| `source_reference` | 0 | 3 | 3 |
| `task_title` | 1 | 0 | 1 |
| `due_date` | 1 | 0 | 1 |
| `project_id` | 0 | 0 | 0 |
| `task_id` | 0 | 0 | 0 |
| `created_at` | 0 | 0 | 0 |
| `updated_at` | 0 | 0 | 0 |

> 注：`project_id`、`task_id`、`created_at`、`updated_at` 当前无实际映射，保留在词表中以支持未来需求。

---

## 7. 相关文档

- `docs/SEMANTIC_LAYER_ARCHITECTURE.md` — 语义层整体架构（受控词表是其中的核心设计原则）
- `docs/AI_ROUTING.md` — AI 路由设计（路由中的 capabilities 与语义配置对应）
- `docs/SEMANTIC_LAYER_BASELINE.md` — 升级前基线
- `docs/SEMANTIC_LAYER_IMPLEMENTATION_REPORT.md` — 实施报告
