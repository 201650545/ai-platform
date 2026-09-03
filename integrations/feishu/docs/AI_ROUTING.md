# AI 路由设计

> 本文档描述 Feishu Data Hub 的 AI 查询路由机制，包括路由配置文件、公开路由文件、意图定义与选择逻辑、读取层级、路由测试用例以及禁止扫描全部数据的规则。

---

## 1. 路由概述

### 1.1 为什么需要路由

Data Hub 包含多个项目（当前为 `learning-english` 和 `civil-service-exam`），每个项目有多张表、多个分片文件。当 AI 代理收到一个用户查询时，如果不了解应该读取哪个项目、哪些文件，就会面临两个问题：

1. **过度读取**：扫描所有项目的全部记录，消耗大量 token 和时间，且可能引入不相关数据导致分析偏差。
2. **路由错误**：将英语学习的问题路由到公考项目，或反之，导致回答错误。

路由层（`routing.json`）通过定义**意图（intent）**来解决这个问题：每个意图描述一类查询，并指定候选项目、推荐优先读取的文件和推荐表。AI 代理在收到查询后，先匹配意图，再按意图的指引读取数据。

### 1.2 路由的定位

路由层提供的是**候选项目选择**（candidate project selection），不是完整的自然语言理解（NLU）。它不解析用户的自然语言语句，而是提供一个结构化的映射表，供 AI 代理（或其上层编排逻辑）根据查询类型选择数据源。

```
用户查询
   │
   ▼
AI 代理判断查询类型 → 匹配 routing.json 中的 intent
   │
   ├── intent.list_projects       → 只读 catalog.json
   ├── intent.project_health      → 只读 catalog.json + status.json
   ├── intent.study_planning      → 读 catalog + summary + agent-guide + semantic + 记录
   ├── intent.english_review      → 读 learning-english 的 summary + agent-guide + semantic + 记录
   ├── intent.civil_service_*     → 读 civil-service-exam 的 summary + agent-guide + semantic + 记录
   └── ...
```

### 1.3 路由与读取层级的关系

路由告诉 AI"读哪个项目、哪些文件"，读取层级（reading_depth）告诉 AI"读到什么深度就够了"。两者配合使用：

- 元数据查询（如"有哪些项目"）→ discovery 层级 → 只读 catalog.json
- 理解查询（如"英语项目是做什么的"）→ understanding 层级 → 读 summary.md + agent-guide.md + semantic.json
- 结构查询（如"英语项目有哪些字段"）→ structure 层级 → 读 schema.json + manifest.json
- 业务查询（如"哪些词需要复习"）→ business_query 层级 → 读取具体表的记录分片

---

## 2. 路由配置文件

### 2.1 文件位置

**源文件：** `config/query-routing.yaml`（人工维护）

**生成代码：** `lib/semantic.mjs` → `buildRoutingJson()`

**公开产物：** `public/routing.json`

### 2.2 配置结构

`config/query-routing.yaml` 包含以下顶层部分：

```yaml
routing_version: 1

# 受控状态词表
status_vocab:
  - ok
  - stale
  - failed
  - unavailable
  - security_blocked
  - disabled

# 意图定义
intents:
  <intent_name>:
    description: "意图描述"
    # 方式一：显式指定项目
    projects:
      - <slug>
    # 方式二：按能力匹配（二选一）
    capabilities:
      - <capability>
    selection: all_active_matching
    record_data_required: true/false
    recommended_first_files:
      - <file_path>
    recommended_tables:
      - <table_slug>

# 读取层级
reading_depth:
  discovery: { ... }
  understanding: { ... }
  structure: { ... }
  business_query: { ... }
```

### 2.3 受控状态词表（status_vocab）

路由配置定义了一组受控状态词表，用于描述项目和同步状态：

| 状态 | 含义 |
|---|---|
| `ok` | 同步正常，数据为最新 |
| `stale` | 展示的是上一次成功同步的版本，最近一次同步尝试失败 |
| `failed` | 同步失败 |
| `unavailable` | 项目不可用（如已禁用） |
| `security_blocked` | 因安全扫描失败而被阻止 |
| `disabled` | 项目已被人工禁用 |

这些状态值与 `catalog.json` 和 `status.json` 中的 `sync_status` 字段对应。AI 代理应使用这些受控值判断数据可用性。

---

## 3. 公开路由文件 routing.json

### 3.1 生成过程

`routing.json` 由 `buildRoutingJson()` 函数从 `config/query-routing.yaml` 和 `catalog.json` 共同构建：

```
config/query-routing.yaml  +  catalog.json
              │
              ▼
      buildRoutingJson(routingConfig, catalog)
              │
              ├── 从 catalog 构建能力索引（capability_index）
              ├── 从 catalog 构建领域索引（domain_index）
              ├── 遍历 intents，解析候选项目
              │     ├── 如果 intent 有 projects → 直接使用
              │     └── 如果 intent 有 capabilities → 从能力索引查找匹配项目
              └── 输出 routing.json
```

### 3.2 routing.json 结构

```json
{
  "routing_version": 1,
  "generated_at": "<ISO timestamp>",
  "build_id": "<build_id>",
  "status_vocab": ["ok", "stale", "failed", "unavailable", "security_blocked", "disabled"],
  "intents": {
    "<intent_name>": {
      "description": "意图描述",
      "matching_domains": ["<domain>", ...],
      "matching_capabilities": ["<capability>", ...],
      "candidate_projects": ["<slug>", ...],
      "recommended_first_files": ["<path>", ...],
      "recommended_tables": ["<table_slug>", ...],
      "record_data_required": true
    }
  },
  "reading_depth": {
    "discovery": { "description": "...", "files": [...] },
    "understanding": { "description": "...", "files": [...] },
    "structure": { "description": "...", "files": [...] },
    "business_query": { "description": "...", "files": [...], "rule": "..." }
  },
  "capability_index": {
    "study_planning": ["civil-service-exam", "learning-english"],
    "error_analysis": ["civil-service-exam", "learning-english"],
    ...
  },
  "domain_index": {
    "learning": ["civil-service-exam", "learning-english"],
    "language": ["learning-english"],
    "exam": ["civil-service-exam"]
  }
}
```

### 3.3 候选项目解析逻辑

`buildRoutingJson()` 中候选项目的解析逻辑：

1. **显式项目列表优先**：如果 intent 定义了 `projects` 字段且非空，直接使用该列表作为 `candidate_projects`。
2. **能力匹配**：如果 intent 没有 `projects` 但有 `capabilities`，则从 `capability_index` 中查找所有声明了这些能力的项目，取并集后排序。
3. **匹配领域**：`matching_domains` 字段记录该意图涉及的领域。如果使用显式项目列表，则取这些项目的领域；如果使用能力匹配，则取所有领域。

**实际示例：**

- `study_planning` intent 定义了 `capabilities: [study_planning]`，两个项目都声明了 `study_planning` 能力，因此 `candidate_projects` 为 `["civil-service-exam", "learning-english"]`。
- `english_review` intent 定义了 `projects: [learning-english]`，因此 `candidate_projects` 为 `["learning-english"]`。
- `list_projects` intent 没有指定项目也不需要能力匹配，`candidate_projects` 为空数组 `[]`，因为该意图只需读取 `catalog.json`。

---

## 4. 意图（intent）定义和选择逻辑

### 4.1 当前定义的意图

Data Hub 当前定义了 8 个意图：

| 意图 | 描述 | 候选项目 | 需要记录数据 |
|---|---|---|---|
| `list_projects` | 列出所有可用项目 | 无（只读 catalog） | 否 |
| `project_health` | 检查项目同步状态和数据新鲜度 | 无（只读 catalog + status） | 否 |
| `study_planning` | 制定学习计划（跨项目） | civil-service-exam, learning-english | 是 |
| `english_review` | 分析英语复习情况 | learning-english | 是 |
| `english_errors` | 分析英语学习错误 | learning-english | 是 |
| `civil_service_error_analysis` | 分析公考错题 | civil-service-exam | 是 |
| `civil_service_exam_patterns` | 分析真题命题规律 | civil-service-exam | 是 |
| `civil_service_knowledge_review` | 查看公考知识点掌握情况 | civil-service-exam | 是 |

### 4.2 各意图详细定义

#### list_projects

```yaml
list_projects:
  description: "列出所有可用项目"
  required_sources:
    - catalog
  projects: []
  record_data_required: false
  recommended_first_files:
    - catalog.json
```

**用途：** 当用户问"有哪些项目"、"Hub 里有什么数据"时使用。只需读取 `catalog.json`，不读取任何记录数据。

#### project_health

```yaml
project_health:
  description: "检查项目同步状态和数据新鲜度"
  required_sources:
    - catalog
    - status
  projects: []
  record_data_required: false
  recommended_first_files:
    - catalog.json
    - "projects/<slug>/status.json"
```

**用途：** 当用户问"数据是最新的吗"、"哪个项目同步失败了"时使用。读取 `catalog.json` 获取全局状态概览，读取各项目的 `status.json` 获取详细同步状态。

#### study_planning

```yaml
study_planning:
  description: "制定学习计划（跨项目）"
  capabilities:
    - study_planning
  selection: all_active_matching
  record_data_required: true
  recommended_first_files:
    - catalog.json
    - "projects/<slug>/summary.md"
    - "projects/<slug>/agent-guide.md"
    - "projects/<slug>/semantic.json"
  recommended_tables:
    - daily-plan
    - study-tasks
    - daily-study-plan
    - competency-state
    - knowledge-points
    - vocabulary
```

**用途：** 当用户问"帮我制定今天的学习计划"时使用。这是跨项目意图，因为两个项目都声明了 `study_planning` 能力。AI 需要先读取两个项目的 summary、agent-guide 和 semantic，再读取计划相关的表。

**推荐表说明：**
- `daily-plan`、`study-tasks`（learning-english 的计划表）
- `daily-study-plan`（civil-service-exam 的计划表）
- `competency-state`（learning-english 的能力指标）
- `knowledge-points`（civil-service-exam 的知识主干）
- `vocabulary`（learning-english 的词汇核心）

#### english_review

```yaml
english_review:
  description: "分析英语复习情况"
  projects:
    - learning-english
  record_data_required: true
  recommended_first_files:
    - "projects/learning-english/summary.md"
    - "projects/learning-english/agent-guide.md"
    - "projects/learning-english/semantic.json"
  recommended_tables:
    - vocabulary
    - learning-log
    - competency-state
    - error-remediation
    - study-tasks
```

**用途：** 当用户问"哪些英语词需要复习"、"最近英语学得怎么样"时使用。仅路由到 `learning-english` 项目。

#### english_errors

```yaml
english_errors:
  description: "分析英语学习错误"
  projects:
    - learning-english
  record_data_required: true
  recommended_first_files:
    - "projects/learning-english/agent-guide.md"
    - "projects/learning-english/semantic.json"
  recommended_tables:
    - error-remediation
    - learning-log
    - competency-state
```

**用途：** 当用户问"英语哪类错误最多"、"英语错误模式是什么"时使用。推荐优先读取 `error-remediation` 表（注意该表仅 8 条记录，分析结论需标注样本量限制）。

#### civil_service_error_analysis

```yaml
civil_service_error_analysis:
  description: "分析公考错题"
  projects:
    - civil-service-exam
  record_data_required: true
  recommended_first_files:
    - "projects/civil-service-exam/summary.md"
    - "projects/civil-service-exam/agent-guide.md"
    - "projects/civil-service-exam/semantic.json"
  recommended_tables:
    - practice-records
    - past-exam-questions
    - knowledge-points
    - common-traps
    - exam-analysis
```

**用途：** 当用户问"公考哪类题错最多"、"公考错题归因"时使用。注意 `practice-records` 当前仅 1 条记录，错题分析应以 `past-exam-questions`（128 条）为主体。

#### civil_service_exam_patterns

```yaml
civil_service_exam_patterns:
  description: "分析真题命题规律"
  projects:
    - civil-service-exam
  record_data_required: true
  recommended_first_files:
    - "projects/civil-service-exam/semantic.json"
    - "projects/civil-service-exam/schema.json"
  recommended_tables:
    - exam-patterns
    - past-exam-questions
    - exam-analysis
    - common-traps
```

**用途：** 当用户问"公考命题规律是什么"、"哪些考点出现频率高"时使用。以 `exam-patterns` 表为主，联合 `past-exam-questions`、`exam-analysis` 和 `common-traps`。

#### civil_service_knowledge_review

```yaml
civil_service_knowledge_review:
  description: "查看公考知识点掌握情况"
  projects:
    - civil-service-exam
  record_data_required: true
  recommended_first_files:
    - "projects/civil-service-exam/agent-guide.md"
    - "projects/civil-service-exam/semantic.json"
  recommended_tables:
    - knowledge-points
    - exam-patterns
```

**用途：** 当用户问"公考哪些知识点需要加强"、"知识点掌握怎么样"时使用。以 `knowledge-points` 为主，联合 `exam-patterns` 查看考点频次和复习优先级。

### 4.3 意图选择逻辑

AI 代理在选择意图时，应遵循以下逻辑：

1. **元数据查询优先判断**：如果查询是关于"有哪些项目"、"数据是否最新"、"有多少张表"等元数据问题，匹配 `list_projects` 或 `project_health`，不需要读取记录。

2. **按领域/能力匹配**：如果查询涉及具体业务，先看查询涉及哪个领域：
   - 涉及英语学习 → 匹配 `english_review`、`english_errors` 或 `study_planning`
   - 涉及公考备考 → 匹配 `civil_service_*` 系列或 `study_planning`
   - 涉及跨项目学习计划 → 匹配 `study_planning`

3. **按推荐表匹配**：如果查询提到具体数据内容，参考 `recommended_tables`：
   - 提到"词汇/单词/复习" → `vocabulary` 表 → `english_review`
   - 提到"错题/错误" + 英语 → `error-remediation` → `english_errors`
   - 提到"错题" + 公考 → `past-exam-questions` → `civil_service_error_analysis`
   - 提到"命题/规律/考点频次" → `exam-patterns` → `civil_service_exam_patterns`
   - 提到"知识点掌握" + 公考 → `knowledge-points` → `civil_service_knowledge_review`

4. **兜底策略**：如果无法明确匹配意图，从 `catalog.json` 的 `domains` 和 `capabilities` 字段判断候选项目，再读取对应项目的 `summary.md` 和 `agent-guide.md` 获取更具体的指引。

---

## 5. 读取层级

路由配置定义了四个读取层级，指导 AI 在不同深度下应该读取哪些文件。

### 5.1 discovery（发现项目）

```yaml
discovery:
  description: "仅发现项目"
  files:
    - catalog.json
```

**适用场景：** 用户问"有哪些项目"、"Hub 能做什么"。

**读取内容：** 只读 `catalog.json`，获取项目列表、各项目的 domains/capabilities/table_count/records/sync_status。

**不应读取：** 任何项目的具体文件或记录。

### 5.2 understanding（理解项目）

```yaml
understanding:
  description: "理解项目"
  files:
    - "projects/<slug>/summary.md"
    - "projects/<slug>/agent-guide.md"
    - "projects/<slug>/semantic.json"
```

**适用场景：** 用户问"英语项目是做什么的"、"公考项目有哪些分析规则"。

**读取内容：** 项目的 `summary.md`（业务说明）、`agent-guide.md`（AI 使用规则）、`semantic.json`（语义映射）。

**不应读取：** `schema.json`、`manifest.json` 的字段级细节，或任何记录数据。

### 5.3 structure（理解数据结构）

```yaml
structure:
  description: "理解数据结构"
  files:
    - "projects/<slug>/schema.json"
    - "projects/<slug>/manifest.json"
```

**适用场景：** 用户问"英语项目有哪些字段"、"词汇表有哪些选项值"、"表之间有什么关联"。

**读取内容：** 项目的 `schema.json`（字段类型、选项、关联）和 `manifest.json`（表列表、记录数、校验和、分片文件路径）。

**不应读取：** 具体记录数据。结构信息足以回答字段和关系问题。

### 5.4 business_query（回答业务问题）

```yaml
business_query:
  description: "回答业务问题"
  files:
    - "只读取所需表的 records 分片"
  rule: "不得扫描所有项目全部记录作为默认策略"
```

**适用场景：** 用户问"哪些词需要复习"、"公考哪类题错最多"、"帮我制定今天的学习计划"。

**读取内容：** 只读取回答该问题所需的表的记录分片（`tables/<slug>/records-XXXX.json`）。

**核心规则：** 不得扫描所有项目全部记录作为默认策略。必须根据具体问题筛选所需的表和分片。

### 5.5 层级递进原则

读取层级是递进的关系——高层级的读取可以跳过低层级，但不应反过来：

```
discovery（catalog.json）
    ↓ 可选
understanding（summary + agent-guide + semantic）
    ↓ 可选
structure（schema + manifest）
    ↓ 可选
business_query（记录分片）
```

- 业务查询通常需要先经过 understanding（理解项目语义）再到 business_query（读记录）。
- 元数据查询止步于 discovery 或 structure，不应下探到 business_query。
- 每一层级只读取该层级所需的文件，不"顺便"读取更深层级的数据。

---

## 6. 路由测试用例

`scripts/validate-semantic.mjs` 中包含对路由逻辑的自动化测试。以下测试用例必须在每次校验中通过。

### 6.1 必需 intent 存在性测试

**测试：** routing.json 必须包含以下 intent：

- `list_projects`
- `project_health`
- `study_planning`
- `english_review`
- `civil_service_error_analysis`

**测试代码：**

```javascript
const requiredIntents = ["list_projects", "project_health", "study_planning",
                          "english_review", "civil_service_error_analysis"];
for (const intent of requiredIntents) {
  if (!routing.intents?.[intent]) {
    console.error(`  ✗ routing.json 缺少 intent: ${intent}`);
    totalErrors++;
  }
}
```

### 6.2 跨项目路由测试

**测试：** `study_planning` 意图应路由到两个项目。

**预期：** `candidate_projects` 为 `["civil-service-exam", "learning-english"]`（按字母序排列）。

**测试代码：**

```javascript
const studyPlanning = routing.intents?.study_planning;
if (studyPlanning) {
  const expected = ["civil-service-exam", "learning-english"];
  if (JSON.stringify(studyPlanning.candidate_projects) !== JSON.stringify(expected)) {
    console.error(`  ✗ study_planning 候选项目不正确`);
    totalErrors++;
  }
}
```

**验证逻辑：** 两个项目都声明了 `study_planning` 能力，因此通过能力匹配应同时命中两个项目。

### 6.3 单项目路由测试

**测试：** `english_review` 意图应仅路由到 `learning-english`。

**预期：** `candidate_projects` 为 `["learning-english"]`（长度为 1）。

**测试代码：**

```javascript
const englishReview = routing.intents?.english_review;
if (englishReview) {
  if (englishReview.candidate_projects.length !== 1 ||
      englishReview.candidate_projects[0] !== "learning-english") {
    console.error(`  ✗ english_review 候选项目不正确`);
    totalErrors++;
  }
}
```

### 6.4 公考项目路由测试

**测试：** `civil_service_error_analysis` 意图应仅路由到 `civil-service-exam`。

**预期：** `candidate_projects` 为 `["civil-service-exam"]`（长度为 1）。

**测试代码：**

```javascript
const civilServiceError = routing.intents?.civil_service_error_analysis;
if (civilServiceError) {
  if (civilServiceError.candidate_projects.length !== 1 ||
      civilServiceError.candidate_projects[0] !== "civil-service-exam") {
    console.error(`  ✗ civil_service_error_analysis 候选项目不正确`);
    totalErrors++;
  }
}
```

### 6.5 元数据意图不需要记录测试

**测试：** `list_projects` 和 `project_health` 意图的 `record_data_required` 必须为 `false`。

**预期：** 这两个意图不需要读取业务记录。

**测试代码：**

```javascript
for (const intent of ["list_projects", "project_health"]) {
  const intentDef = routing.intents?.[intent];
  if (intentDef && intentDef.record_data_required !== false) {
    console.error(`  ✗ ${intent} 不应需要记录数据`);
    totalErrors++;
  }
}
```

### 6.6 测试用例汇总

| 测试用例 | 意图 | 预期结果 | 验证点 |
|---|---|---|---|
| 必需 intent 存在 | 5 个必需 intent | 全部存在 | intent 定义完整性 |
| 跨项目路由 | study_planning | 2 个候选项目 | 能力匹配逻辑 |
| 英语单项目路由 | english_review | 1 个候选项目 | 显式项目列表 |
| 公考单项目路由 | civil_service_error_analysis | 1 个候选项目 | 显式项目列表 |
| 元数据不需记录 | list_projects | record_data_required=false | 读取层级控制 |
| 元数据不需记录 | project_health | record_data_required=false | 读取层级控制 |

---

## 7. 禁止扫描全部数据的规则

### 7.1 核心规则

`routing.json` 的 `reading_depth.business_query` 中明确定义了这条规则：

```yaml
business_query:
  description: "回答业务问题"
  files:
    - "只读取所需表的 records 分片"
  rule: "不得扫描所有项目全部记录作为默认策略"
```

### 7.2 规则的具体含义

"禁止扫描全部数据"意味着：

1. **不默认全量加载**：收到业务查询时，不应先加载所有项目的所有表的所有记录，再从中筛选。
2. **按需读取分片**：应根据查询意图，只读取所需表的记录分片（`tables/<slug>/records-XXXX.json`）。
3. **利用筛选条件**：对于大表（如 `vocabulary` 有 6000 条记录），应使用语义配置中的 `date_field`、`status_field` 等信息设计筛选条件，避免全量遍历。
4. **利用分片机制**：记录按 `chunk_size: 500` 分片存储，每个分片是独立的 JSON 文件。AI 可以只读取需要的分片。

### 7.3 不应读取记录的情况

以下查询**不应**读取业务记录：

| 查询 | 应读取的文件 | 不应读取 |
|---|---|---|
| "列出所有项目" | `catalog.json` | 任何项目的记录 |
| "哪个项目数据过期了" | `catalog.json` + 各项目 `status.json` | 任何项目的记录 |
| "项目有多少张表" | `manifest.json` | 记录分片 |
| "词汇表有哪些字段" | `schema.json` | 记录分片 |
| "单词和文本库是什么关系" | `schema.json`（关联字段）+ `semantic.json`（语义类型） | 记录分片 |
| "AI 应该怎么分析英语数据" | `agent-guide.md` | 记录分片 |

### 7.4 应读取记录的情况

以下查询**应该**读取记录分片，但只读所需表：

| 查询 | 应读取的表 | 不应读取 |
|---|---|---|
| "哪些词需要复习" | `vocabulary`（筛选 `下次复习` 到期） | 其他表 |
| "最近学了什么" | `learning-log`（按日期倒序） | 全部 9 张表 |
| "公考哪类题错最多" | `past-exam-questions`（筛选 `结果` 为错） | `target-positions`、`experience-methods` 等 |
| "帮我制定今天的学习计划" | `vocabulary` + `study-tasks` + `competency-state` + `error-remediation` | 不相关的表 |

### 7.5 AI-README.md 中的声明

`AI-README.md`（由 `buildAiReadme()` 生成）中明确声明了这一规则：

```
## 禁止扫描全部数据的情况

以下情况**不应**读取业务记录：
- "列出所有项目" — 只读 `catalog.json`
- "哪个项目数据过期了" — 只读 `catalog.json` 和 `status.json`
- "项目有多少张表" — 只读 `manifest.json`

只有在回答具体业务问题（如"哪些词需要复习"）时才读取记录分片。
```

### 7.6 validate-ai-docs.mjs 的强制校验

`validate-ai-docs.mjs` 校验 `AI-README.md` 必须包含"禁止扫描全部数据"这一内容，确保该规则在每次构建后都显式存在于 AI 入口指南中：

```javascript
const requiredContent = [
  "推荐读取流程",
  "catalog.json",
  "routing.json",
  // ...
  "禁止扫描全部数据",
  "数据不足",
  "只读",
  "安全边界"
];
```

---

## 8. 路由文件维护规则

### 8.1 何时修改路由配置

| 场景 | 是否需要修改 `query-routing.yaml` |
|---|---|
| 新增项目，且新项目支持已有能力 | 不需要（自动通过能力匹配纳入） |
| 新增项目，且需要新的查询意图 | 需要（添加新 intent） |
| 新增项目，需要被特定意图显式路由 | 需要（在 intent 的 projects 中添加） |
| 调整已有意图的推荐表 | 需要（修改 recommended_tables） |
| 调整读取层级定义 | 需要（修改 reading_depth） |

### 8.2 修改后的验证

修改 `config/query-routing.yaml` 后，必须运行：

```bash
node scripts/sync-hub.mjs        # 重新构建 routing.json
node scripts/validate-semantic.mjs  # 校验路由逻辑
node scripts/validate-ai-docs.mjs   # 校验 AI 文档
```

### 8.3 路由配置不自动生成

`config/query-routing.yaml` 是人工维护的文件，不会被代码自动生成或修改。文件头部明确标注：

```yaml
# Query routing configuration for the Data Hub.
# Defines how AI should select projects and data sources for different query types.
# This file provides "candidate project selection" only — not full NLU.
```

---

## 9. 相关文档

- `docs/SEMANTIC_LAYER_ARCHITECTURE.md` — 语义层整体架构（路由是其中的核心组件之一）
- `docs/SEMANTIC_TYPES.md` — 受控词表（路由中的 capabilities 和 domains 与语义配置对应）
- `docs/SEMANTIC_LAYER_BASELINE.md` — 升级前基线（路由层是新增的）
- `docs/ARCHITECTURE.md` — Data Hub 整体架构
