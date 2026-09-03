# AI 语义层架构

> 本文档描述 Feishu Data Hub 的 AI 语义层架构，包括核心组件、数据流、解耦原则、受控词表、校验机制、安全边界以及新增 Base 的接入步骤。

---

## 1. 语义层架构概述

### 1.1 为什么需要语义层

Feishu Data Hub 从飞书多维表格（Bitable）导出数据，以静态 JSON 部署在 GitHub Pages 上。在语义层引入之前，公开产物只有 `catalog.json`、`manifest.json`、`schema.json`、`status.json` 和机械汇总的 `summary.md`。这些产物能告诉 AI"有哪些表、有哪些字段"，但无法告诉 AI"这些字段在业务上是什么含义、这张表扮演什么角色、不同项目之间如何选择"。

语义层要解决的核心问题是：**让 AI 在不访问飞书、不接触源表结构的前提下，能够正确理解数据模型的业务语义，并据此做出路由决策和分析判断。**

具体来说，语义层填补了以下空白：

| 空白点 | 语义层之前的现状 | 语义层提供的解决 |
|---|---|---|
| 表的业务角色 | schema.json 只有字段名和类型 | `semantic.json` 为每张表标注 `role`（plan / event_log / knowledge 等） |
| 字段的业务含义 | 字段名是中文，AI 需猜含义 | `field_mappings` 将字段映射到受控 `semantic_type`（如 `review_due_at`、`mastery_level`） |
| 项目能力与领域 | catalog.json 只有 group 和 tags | 新增 `domains`、`capabilities`、`entity_types`、`supported_queries` |
| AI 路由决策 | AI 需扫描全部项目判断相关性 | `routing.json` 将意图（intent）映射到候选项目和推荐表 |
| AI 使用规则 | 无 | `agent-guide.md` 规定适用任务、分析优先级、禁止推断 |
| 项目业务摘要 | 机械汇总的字段列表 | 人工维护的 `summary.md` 含项目用途、表关系、限制说明 |

### 1.2 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      人工维护层（源文件）                        │
│  config/semantics/<slug>.yaml    config/query-routing.yaml   │
│  content/projects/<slug>/        content/projects/<slug>/    │
│    summary.md                       agent-guide.md            │
└──────────┬──────────────────────────────┬────────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     构建层（代码逻辑）                          │
│  lib/semantic.mjs                                              │
│    loadSemanticConfig()  validateSemanticConfig()             │
│    buildSemanticJson()   loadRoutingConfig()                  │
│    buildRoutingJson()                                          │
│  scripts/sync-project.mjs  scripts/sync-hub.mjs               │
└──────────┬────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│                   公开产物层（GitHub Pages）                    │
│  public/projects/<slug>/semantic.json                         │
│  public/routing.json                                          │
│  public/catalog.json（扩展 fields）                            │
│  public/AI-README.md                                          │
│  public/projects/<slug>/summary.md                            │
│  public/projects/<slug>/agent-guide.md                        │
└──────────┬────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│                     校验层（CI/本地）                           │
│  scripts/validate-semantic.mjs                                │
│  scripts/validate-ai-docs.mjs                                 │
│  scripts/security-scan.mjs                                    │
└─────────────────────────────────────────────────────────────┘
```

语义层遵循"人工维护配置 → 代码构建产物 → 校验保护一致性"的三段式流水线。人工维护的文件（YAML 配置和 Markdown 文档）是单一事实来源，代码只负责转换、校验和复制，不会反向修改人工内容。

### 1.3 设计原则

1. **语义配置与数据同步解耦**：语义配置的变更不需要重新从飞书拉取数据，数据同步的变更也不需要修改语义配置（详见第 4 节）。
2. **受控词表**：`semantic_type`、`table role`、`entity_type` 均使用封闭枚举，禁止自由填值，确保 AI 能可靠解析（详见第 5 节）。
3. **人工内容不被自动覆盖**：`summary.md` 和 `agent-guide.md` 是人工维护的，构建时只复制不生成。
4. **只读安全边界**：语义层不引入任何写入能力，不暴露凭据，所有产物经过安全扫描。
5. **渐进增强**：语义层在原有 catalog/schema/manifest 之上新增字段，不破坏旧消费者。

---

## 2. 核心组件

语义层由四个核心公开产物和对应的源文件组成。

### 2.1 semantic.json

**源文件：** `config/semantics/<slug>.yaml`（人工维护）

**生成代码：** `lib/semantic.mjs` → `buildSemanticJson()`

**调用位置：** `scripts/sync-project.mjs`

**公开路径：** `public/projects/<slug>/semantic.json`

**职责：** 为单个项目的所有表和字段提供业务语义映射，包括表角色、实体类型、首选能力、字段语义类型。

**结构示例（learning-english）：**

```json
{
  "semantic_version": 1,
  "project_slug": "learning-english",
  "domains": ["learning", "language"],
  "entity_types": ["task", "learning_event", "knowledge", "metric", "content"],
  "capabilities": ["study_planning", "review_prioritization", "error_analysis", "progress_analysis", "content_recommendation"],
  "supported_queries": ["制定英语学习计划", "分析需要复习的内容", ...],
  "tables": {
    "vocabulary": {
      "role": "knowledge",
      "entity_type": "knowledge",
      "preferred_for": ["review_prioritization", "progress_analysis"],
      "primary_display_field": "单词",
      "date_field": "下次复习",
      "status_field": "掌握状态"
    },
    ...
  },
  "field_mappings": {
    "vocabulary": {
      "单词": { "semantic_type": "entity_identity_title" },
      "掌握状态": { "semantic_type": "mastery_level" },
      "下次复习": { "semantic_type": "review_due_at" },
      ...
    },
    ...
  },
  "generated_at": "2026-07-26T06:35:53Z",
  "build_id": "20260726T063553Z-717ec7d"
}
```

**关键字段说明：**

| 字段 | 含义 |
|---|---|
| `semantic_version` | 语义配置版本，当前固定为 `1` |
| `project_slug` | 项目 slug，与项目配置一致 |
| `domains` | 项目所属领域（受控，如 `learning`、`language`、`exam`） |
| `entity_types` | 项目涉及的实体类型（受控枚举子集） |
| `capabilities` | 项目支持的分析能力（如 `study_planning`、`error_analysis`） |
| `supported_queries` | 项目支持的自然语言查询示例 |
| `tables` | 每张表的语义元数据：`role`、`entity_type`、`preferred_for`、`primary_display_field`、`date_field`、`status_field` |
| `field_mappings` | 字段到 `semantic_type` 的映射，按表分组 |

### 2.2 routing.json

**源文件：** `config/query-routing.yaml`（人工维护）

**生成代码：** `lib/semantic.mjs` → `buildRoutingJson()`

**调用位置：** `scripts/sync-hub.mjs`

**公开路径：** `public/routing.json`

**职责：** 将查询意图（intent）映射到候选项目和推荐数据源，提供读取层级指南。这是 AI 选择"读哪个项目、读哪些文件"的路由依据。

**结构示例：**

```json
{
  "routing_version": 1,
  "generated_at": "2026-07-26T06:35:53Z",
  "build_id": "20260726T063553Z-717ec7d",
  "status_vocab": ["ok", "stale", "failed", "unavailable", "security_blocked", "disabled"],
  "intents": {
    "study_planning": {
      "description": "制定学习计划（跨项目）",
      "matching_capabilities": ["study_planning"],
      "candidate_projects": ["civil-service-exam", "learning-english"],
      "recommended_first_files": ["catalog.json", "projects/<slug>/summary.md", ...],
      "recommended_tables": ["daily-plan", "study-tasks", "daily-study-plan", ...],
      "record_data_required": true
    },
    "english_review": {
      "description": "分析英语复习情况",
      "candidate_projects": ["learning-english"],
      "recommended_tables": ["vocabulary", "learning-log", "competency-state", ...],
      "record_data_required": true
    },
    ...
  },
  "reading_depth": {
    "discovery": { ... },
    "understanding": { ... },
    "structure": { ... },
    "business_query": { ... }
  },
  "capability_index": { "study_planning": ["civil-service-exam", "learning-english"], ... },
  "domain_index": { "learning": ["civil-service-exam", "learning-english"], "language": ["learning-english"], ... }
}
```

> 路由的详细设计见 `docs/AI_ROUTING.md`。

### 2.3 catalog.json 扩展

**源文件：** `config/semantics/<slug>.yaml` + `config/projects/<slug>.yaml`

**生成代码：** `scripts/sync-hub.mjs` → `buildCatalog()`

**公开路径：** `public/catalog.json`

**职责：** 全局项目目录。语义层为其扩展了项目级语义字段和顶层索引。

**扩展前（基线）的项目条目字段：**

```
slug, title, description, group, tags, status,
sync_status, is_stale, last_success_at,
manifest, schema, summary, homepage,
table_count, total_records
```

**扩展后新增的项目级字段：**

| 字段 | 含义 | 来源 |
|---|---|---|
| `domains` | 项目所属领域 | `semantic.yaml` → `project.domains` |
| `capabilities` | 项目支持的分析能力 | `semantic.yaml` → `project.capabilities` |
| `entity_types` | 项目涉及的实体类型 | `semantic.yaml` → `project.entity_types` |
| `supported_queries` | 支持的自然语言查询 | `semantic.yaml` → `project.supported_queries` |
| `semantic` | semantic.json 的相对路径 | 固定 `projects/<slug>/semantic.json` |
| `agent_guide` | agent-guide.md 的相对路径 | 固定 `projects/<slug>/agent-guide.md` |
| `freshness` | 数据新鲜度信息 | `{ expected_update, last_success_at, is_stale }` |
| `access_mode` | 访问模式 | 固定 `public-readonly` |

**扩展后新增的顶层字段：**

| 字段 | 含义 |
|---|---|
| `capabilities` | 能力 → 项目 slug 列表的全局索引 |
| `domains` | 领域 → 项目 slug 列表的全局索引 |

这两个顶层索引允许 AI 通过能力或领域快速定位候选项目，无需遍历所有项目条目。

### 2.4 AI-README.md

**生成代码：** `scripts/sync-hub.mjs` → `buildAiReadme()`

**公开路径：** `public/AI-README.md`

**职责：** AI 代理的入口指南，说明 Hub 是什么、如何发现项目、如何选择项目、如何判断 stale、文件职责、禁止扫描全部数据的规则、数据不足的处理方式、只读安全边界。

AI-README.md 是由代码从 catalog.json 自动生成的，包含当前所有项目的列表（含 domains、capabilities、表数、记录数、同步状态）。它不是人工维护的文件，但其内容由 catalog 的真实数据驱动。

**校验要求（由 `validate-ai-docs.mjs` 强制）：**

AI-README.md 必须包含以下关键内容：
- "推荐读取流程"
- "catalog.json"、"routing.json"、"summary.md"、"agent-guide.md"、"semantic.json"、"schema.json"、"manifest.json"
- "禁止扫描全部数据"
- "数据不足"
- "只读"
- "安全边界"

---

## 3. 数据流

### 3.1 语义配置数据流

```
config/semantics/<slug>.yaml
        │
        │  loadSemanticConfig(slug)       ← lib/semantic.mjs
        ▼
  Parsed semantic config (object)
        │
        │  validateSemanticConfig()       ← lib/semantic.mjs
        │  （对照 schema.json 和项目 YAML 校验）
        ▼
  Validated config
        │
        │  buildSemanticJson()            ← lib/semantic.mjs
        ▼
  semantic.json (object)
        │
        │  writeJson(tempDir, "semantic.json", ...)  ← sync-project.mjs
        ▼
  public/projects/<slug>/semantic.json
```

**触发时机：** 每次 `sync-project.mjs` 同步项目时执行。语义配置在同步过程中被读取、校验并写入公开目录。

**关键代码路径（`scripts/sync-project.mjs`）：**

```javascript
// 1. 加载语义配置
const semanticConfig = await loadSemanticConfig(slug);

// 2. 校验语义配置（对照已构建的 schema）
const { errors: semErrors, warnings: semWarnings } = validateSemanticConfig(
  semanticConfig, schema, projectConfig
);
if (semErrors.length > 0) {
  throw new Error(`语义配置校验失败：\n  ${semErrors.join("\n  ")}`);
}

// 3. 构建 semantic.json
const semanticJson = buildSemanticJson(semanticConfig, buildId, generatedAt);
await writeJson(tempDir, "semantic.json", semanticJson, secretValues);
```

### 3.2 路由配置数据流

```
config/query-routing.yaml
        │
        │  loadRoutingConfig()            ← lib/semantic.mjs
        ▼
  Parsed routing config (object)
        │
        │  buildRoutingJson(routingConfig, catalog)  ← lib/semantic.mjs
        │  （依赖已构建的 catalog.json 提供能力/领域索引）
        ▼
  routing.json (object)
        │
        │  writeJson(outputDir, "routing.json", ...)  ← sync-hub.mjs
        ▼
  public/routing.json
```

**触发时机：** 在 `sync-hub.mjs` 中，所有项目同步完成、catalog.json 构建完成后执行。routing.json 的构建依赖 catalog.json 中的 `capabilities` 和 `domains` 索引来解析候选项目。

### 3.3 AI 文档数据流

```
content/projects/<slug>/summary.md
        │
        │  fs.readFile() + assertNoSecrets()  ← sync-project.mjs
        ▼
  public/projects/<slug>/summary.md  （直接复制，不修改内容）

content/projects/<slug>/agent-guide.md
        │
        │  fs.readFile() + assertNoSecrets()  ← sync-project.mjs
        ▼
  public/projects/<slug>/agent-guide.md  （直接复制，不修改内容）
```

**关键点：** `summary.md` 和 `agent-guide.md` 在构建时被原样复制到公开目录，代码不会修改其内容。如果源文件不存在，同步会抛出错误中止（`"content/projects/<slug>/summary.md 不存在 — 必须提供人工维护的项目说明"`）。复制前会执行 `assertNoSecrets()` 安全扫描。

### 3.4 catalog 扩展数据流

```
config/semantics/<slug>.yaml  ──┐
config/projects/<slug>.yaml   ──┤
public/projects/<slug>/status.json ─┤
public/projects/<slug>/manifest.json ─┤
                                │
                                ▼
                    buildCatalog()  ← sync-hub.mjs
                                │
                                ▼
                    public/catalog.json
```

catalog 的构建整合了项目配置（标题、描述、分组）、语义配置（domains、capabilities、entity_types）、同步状态（sync_status、is_stale、last_success_at）和 manifest（table_count、total_records），形成一个全局可路由的项目目录。

---

## 4. 语义配置与数据同步解耦原则

### 4.1 为什么要解耦

数据同步（从飞书拉取记录）和语义配置（标注字段含义）是两个独立的关注点：

- **数据同步**关注"从飞书获取哪些记录、以什么格式存储"——这取决于飞书源表结构和导出视图。
- **语义配置**关注"这些字段在业务上是什么意思"——这取决于学习者的业务模型。

如果两者耦合，每次飞书表结构变化都需要同步修改语义配置，反之亦然。解耦后，两者可以独立演进。

### 4.2 解耦的实现机制

1. **独立的配置文件**：语义配置在 `config/semantics/<slug>.yaml`，项目数据配置在 `config/projects/<slug>.yaml`，两者物理分离。

2. **校验时桥接**：`validateSemanticConfig()` 在同步时将语义配置与当前 schema 对照，检查：
   - 语义配置中的表 slug 是否存在于 schema
   - 语义配置中的字段名是否存在于 schema 的字段列表
   - `primary_display_field`、`date_field`、`status_field` 是否指向真实字段
   - `semantic_type`、`role`、`entity_type` 是否在受控词表内

3. **字段未映射只警告不报错**：如果 schema 中有字段未在语义配置中映射，`validateSemanticConfig()` 只产生 warning（`字段 "xxx" 未映射 semantic_type`），不会阻止同步。这允许新字段先出现在数据中，后续再补充语义映射。

4. **schema 变化的容错**：
   - 飞书新增字段且已加入项目 YAML 的字段白名单 → 字段出现在 schema → 语义配置未映射 → 产生 warning，同步继续
   - 飞书删除字段 → 字段从 schema 消失 → 语义配置仍引用该字段 → 产生 error，同步中止，需人工修正语义配置

### 4.3 解耦的边界

解耦不意味着完全无关联。以下情况需要人工同步修改两侧：

| 变化场景 | 需要修改 |
|---|---|
| 飞书表新增字段并加入导出 | `config/projects/<slug>.yaml`（字段白名单）+ `config/semantics/<slug>.yaml`（字段映射，可后补） |
| 飞书表删除字段 | `config/projects/<slug>.yaml`（移除字段）+ `config/semantics/<slug>.yaml`（移除映射） |
| 飞书表重命名 | `config/projects/<slug>.yaml`（更新表名/字段名）+ `config/semantics/<slug>.yaml`（更新映射） |
| 仅调整语义分类 | 只改 `config/semantics/<slug>.yaml`，不需要重新同步数据 |
| 新增项目能力 | 只改 `config/semantics/<slug>.yaml` 的 `capabilities`，不需要重新同步数据 |

---

## 5. 受控词表

语义层使用三组受控词表，定义在 `lib/semantic.mjs` 中，以 `Set` 形式封闭枚举。任何不在词表中的值都会在校验阶段被拒绝。

### 5.1 semantic_type（字段语义类型）

定义在 `SEMANTIC_TYPES` 常量中，共 26 个值：

```
entity_identity_title, project_id, task_id, task_title, task_status, task_priority,
planned_date, due_date, event_date, created_at, updated_at, duration_minutes,
outcome, score, accuracy, attempt_count, error_type, knowledge_topic,
content_text, source_reference, relation, status, confidence, difficulty,
review_due_at, mastery_level
```

每个字段的含义和典型用法详见 `docs/SEMANTIC_TYPES.md`。

### 5.2 table role（表角色）

定义在 `TABLE_ROLES` 常量中，共 8 个值：

| role | 含义 | 典型表 |
|---|---|---|
| `plan` | 计划表，承载学习计划与任务 | `daily-plan`、`study-tasks`、`daily-study-plan` |
| `event_log` | 事件日志表，记录学习事件 | `learning-log`、`study-sessions`、`practice-records` |
| `knowledge` | 知识库表，存储知识点/词条 | `vocabulary`、`knowledge-points`、`lexical-units` |
| `metric` | 指标表，存储能力/状态指标 | `competency-state` |
| `content` | 内容表，存储学习材料 | `text-library`、`past-exam-questions` |
| `error_log` | 错误日志表，记录错误与改进 | `error-remediation` |
| `reference` | 参考表，存储目标/经验/陷阱等参考信息 | `target-positions`、`experience-methods`、`common-traps` |
| `analysis` | 分析表，存储深度分析结论 | `exam-analysis`、`exam-patterns` |

### 5.3 entity_type（实体类型）

定义在 `ENTITY_TYPES` 常量中，共 7 个值：

| entity_type | 含义 | 典型表 |
|---|---|---|
| `task` | 单个任务 | `study-tasks` |
| `task_collection` | 任务集合/计划 | `daily-plan`、`daily-study-plan` |
| `learning_event` | 学习事件 | `learning-log`、`study-sessions`、`practice-records`、`error-remediation` |
| `knowledge` | 知识实体 | `vocabulary`、`knowledge-points`、`lexical-units` |
| `metric` | 指标实体 | `competency-state`、`exam-patterns` |
| `content` | 内容实体 | `text-library`、`past-exam-questions`、`exam-analysis` |
| `reference` | 参考实体 | `target-positions`、`experience-methods`、`common-traps` |

### 5.4 添加新类型的规则

受控词表是封闭的。添加新类型需要：

1. 在 `lib/semantic.mjs` 的对应 `Set` 中添加新值。
2. 更新 `docs/SEMANTIC_TYPES.md` 文档，说明新类型的含义和典型用法。
3. 确认至少有一个项目的语义配置实际使用了新类型（"不为未使用的类型添加枚举"）。
4. 运行 `validate-semantic.mjs` 确认所有项目校验通过。

---

## 6. 校验机制

语义层引入了两个新的校验脚本，与原有的 `validate-config.mjs`、`validate-output.mjs`、`security-scan.mjs` 共同构成完整校验链。

### 6.1 validate-semantic.mjs

**路径：** `scripts/validate-semantic.mjs`

**职责：** 校验语义配置的正确性、路由逻辑的正确性、catalog 新字段的完整性、AI-README.md 的存在性。

**校验内容：**

1. **语义配置校验（每项目）：**
   - `config/semantics/<slug>.yaml` 存在
   - `semantic_version` 为 1
   - `project.slug` 与项目配置一致
   - `domains`、`entity_types`、`capabilities` 为非空数组
   - 语义配置中的表 slug 存在于 schema
   - `role`、`entity_type` 在受控词表内
   - `primary_display_field`、`date_field`、`status_field` 指向真实字段
   - 字段映射中的字段名存在于 schema
   - `semantic_type` 在受控词表内
   - `semantic.json` 已生成到公开输出
   - `agent-guide.md` 存在且内容 >= 100 字符
   - `summary.md` 存在且内容 >= 500 字符

2. **路由校验（全局）：**
   - `routing.json` 存在且可解析
   - 必需的 intent 存在：`list_projects`、`project_health`、`study_planning`、`english_review`、`civil_service_error_analysis`
   - `study_planning` 的候选项目为 `["civil-service-exam", "learning-english"]`（跨项目路由正确）
   - `english_review` 的候选项目仅 `["learning-english"]`（单项目路由正确）
   - `civil_service_error_analysis` 的候选项目仅 `["civil-service-exam"]`
   - `list_projects` 和 `project_health` 的 `record_data_required` 为 `false`

3. **catalog 新字段校验（全局）：**
   - 顶层 `capabilities` 索引存在
   - 顶层 `domains` 索引存在
   - 每个项目包含新字段：`domains`、`capabilities`、`entity_types`、`supported_queries`、`semantic`、`agent_guide`、`freshness`、`access_mode`
   - 每个项目保留旧字段：`slug`、`title`、`description`、`group`、`tags`、`status`、`sync_status`、`is_stale`、`last_success_at`、`manifest`、`schema`、`summary`、`homepage`、`table_count`、`total_records`
   - 顶层索引与项目声明一致（索引中包含的项目必须声明对应能力/领域）

4. **AI-README.md 校验（全局）：**
   - 文件存在且内容 >= 500 字符

### 6.2 validate-ai-docs.mjs

**路径：** `scripts/validate-ai-docs.mjs`

**职责：** 校验 AI 文档文件的存在性、内容充分性、安全性和章节完整性。

**校验内容：**

1. **每项目必需文件（含最小内容要求）：**

   | 文件 | 最小内容 | 说明 |
   |---|---|---|
   | `summary.md` | 500 字符 | 项目说明 |
   | `agent-guide.md` | 200 字符 | AI 使用规则 |
   | `semantic.json` | 50 字符 | 语义映射 |
   | `schema.json` | 50 字符 | 数据结构 |
   | `manifest.json` | 50 字符 | 数据清单 |
   | `status.json` | 20 字符 | 同步状态 |

2. **安全性扫描：** 每个文件经过 `scanContent()` 扫描，检查敏感信息模式、Token 前缀、高熵字符串。

3. **summary.md 必需章节：**
   `项目用途`、`核心目标`、`主要数据表`、`表之间的关系`、`常见分析问题`、`推荐读取顺序`、`数据更新时间与时效性`、`数据公开范围`、`已知限制`、`不应做出的推断`

4. **agent-guide.md 必需章节：**
   `适用任务`、`不适用任务`、`分析优先级`、`读取顺序`、`计划制定规则`、`错误分析规则`、`时间范围处理`、`数据不足时的处理`、`禁止推断`、`输出要求`

5. **Hub 级文件：**
   - `AI-README.md`（>= 500 字符，含安全扫描）
   - `catalog.json`（>= 100 字符，含安全扫描）
   - `routing.json`（>= 100 字符，含安全扫描）

6. **AI-README.md 必需内容：** 包含"推荐读取流程"、"catalog.json"、"routing.json"、"summary.md"、"agent-guide.md"、"semantic.json"、"schema.json"、"manifest.json"、"禁止扫描全部数据"、"数据不足"、"只读"、"安全边界"。

7. **routing.json 必需 intents：** `list_projects`、`project_health`、`study_planning`、`english_review`、`civil_service_error_analysis`。

### 6.3 校验执行顺序

在 CI（`.github/workflows/validate.yml`）中，校验按以下顺序执行：

```
1. validate-config.mjs      ← 配置结构校验
2. sync-hub.mjs (dry-run)   ← 构建产物
3. validate-output.mjs      ← 产物完整性校验（catalog/manifest/schema/status/checksums）
4. validate-semantic.mjs    ← 语义配置与路由校验
5. validate-ai-docs.mjs     ← AI 文档校验
6. security-scan.mjs        ← 安全扫描
```

任何一步失败都会中止流程并阻止部署。

---

## 7. 安全边界

### 7.1 只读原则

语义层严格遵循只读原则：

- **不存在写入接口**：Hub 是纯静态 JSON 部署在 GitHub Pages 上，没有任何 API 端点可以修改数据。
- **不暴露飞书凭据**：`app_id`、`app_secret`、`tenant_access_token`、`app_token` 仅在同步时使用，不会出现在任何公开产物中。
- **不暴露 GitHub Token**：GitHub Token 仅在 CI 环境中使用，不暴露给浏览器端。
- **AI 无法修改飞书数据**：AI 代理只能读取公开 JSON，不能写回飞书源表。

### 7.2 无凭据原则

公开产物中不包含任何凭据相关信息：

- 语义配置文件 `config/semantics/*.yaml` 只包含字段映射和表元数据，不包含任何连接信息。
- `semantic.json`、`routing.json`、`catalog.json` 只包含业务元数据，不包含任何凭据。
- `summary.md` 和 `agent-guide.md` 在复制到公开目录前经过 `assertNoSecrets()` 扫描。

### 7.3 安全扫描覆盖

安全扫描（`scripts/security-scan.mjs` + `lib/security.mjs`）覆盖以下维度：

| 维度 | 级别 | 检测内容 |
|---|---|---|
| 敏感信息模式 | FATAL | `app_secret`、`tenant_access_token`、`user_access_token`、`authorization`、`client_secret`、`github_token`、`Bearer`、PEM 私钥 |
| Token 前缀 | FATAL | `cli_`、`Bearer `、`ghp_`、`gho_`、`ghs_`、`ghr_`（严格）；`t-`、`u-`（歧义，需含数字且 >= 15 字符） |
| 内部标识符 | FATAL | 飞书 `table_id`（`tbl` 前缀 + 6+ 字符）、`app_token`（JSON 键值对） |
| 禁止文件 | FATAL | `.env*`、`debug-response.json`、`api-cache.json`、`raw-response.json`、`.npmrc`、`.netrc` |
| PII | WARNING | 手机号、身份证号、邮箱、银行卡号 |
| 高熵字符串 | WARNING | Shannon 熵 > 4.0 的长字符串（可能是编码的密钥） |

FATAL 级别的发现会中止整个部署（`process.exit(1)`）。WARNING 级别的发现会打印但不阻止部署。

### 7.4 AI 文档的安全扫描

`validate-ai-docs.mjs` 对每个 AI 文档文件（`summary.md`、`agent-guide.md`、`semantic.json`、`schema.json`、`manifest.json`、`status.json`、`AI-README.md`、`catalog.json`、`routing.json`）单独执行 `scanContent()` 扫描，确保 AI 消费的所有文件都不含敏感信息。

### 7.5 访问模式声明

catalog.json 中每个项目条目包含 `access_mode: "public-readonly"` 字段，显式声明数据的访问模式，供 AI 和其他消费者参考。

---

## 8. 新增 Base 的接入步骤

当需要将一个新的飞书 Base 接入 Data Hub 并纳入语义层时，按以下步骤操作。

### 步骤 1：创建项目配置

在 `config/projects/` 下创建 `<new-slug>.yaml`：

```yaml
config_version: 1

project:
  slug: <new-slug>
  title: "项目标题"
  description: "项目描述"
  group: <group>
  tags: [<tag1>, <tag2>]
  enabled: true
  status: active

source:
  provider: feishu-bitable
  credential_profile: public-personal
  base_key: <base-key>           # 对应 credential-profiles.yaml 中的 key
  export_view_name: "AI 公开导出"

table_discovery:
  mode: view-name
  require_export_view: true

export:
  chunk_size: 500
  include_schema: true
  include_summary: true
  include_record_id: true
  stable_sort: true

privacy:
  require_public_flag: false
  scan_free_text: true
  scan_urls: true
  fail_on_sensitive_content: true

schedule:
  tier: hourly

compatibility:
  mirror_to_legacy_root: false

tables:
  - table_name: "表名"
    table_slug: table-slug
    view_name: "AI 公开导出"
    enabled: true
    fields:
      - "字段1"
      - "字段2"
      ...
```

### 步骤 2：创建语义配置

在 `config/semantics/` 下创建 `<new-slug>.yaml`：

```yaml
semantic_version: 1

project:
  slug: <new-slug>
  domains:
    - <domain1>           # 如 learning, exam, language
    - <domain2>
  entity_types:
    - <entity_type>       # 从 ENTITY_TYPES 中选择
    - ...
  capabilities:
    - <capability>        # 如 study_planning, error_analysis
    - ...
  supported_queries:
    - "支持的查询1"
    - "支持的查询2"

tables:
  table-slug:
    role: <role>                    # 从 TABLE_ROLES 中选择
    entity_type: <entity_type>      # 从 ENTITY_TYPES 中选择
    preferred_for:
      - <capability>
    primary_display_field: "字段名"
    date_field: "日期字段名"         # 或 null
    status_field: "状态字段名"       # 或 null

fields:
  table-slug:
    "字段名":
      semantic_type: <semantic_type>   # 从 SEMANTIC_TYPES 中选择
    ...
```

### 步骤 3：创建 AI 文档

在 `content/projects/<new-slug>/` 下创建两个文件：

**summary.md** — 必须包含以下章节（详见 `docs/PROJECT_SUMMARY_GUIDE.md`）：
- 项目用途
- 核心目标
- 主要数据表
- 表之间的关系
- 关键状态和指标
- 常见分析问题
- 推荐读取顺序
- 数据更新时间与时效性
- 数据公开范围
- 已知限制
- 不应做出的推断

**agent-guide.md** — 必须包含以下章节（详见 `docs/AGENT_GUIDE_AUTHORING.md`）：
- 适用任务
- 不适用任务
- 分析优先级
- 读取顺序
- 计划制定规则
- 错误分析规则
- 时间范围处理
- 数据不足时的处理
- 禁止推断
- 输出要求

### 步骤 4：更新路由配置（可选）

如果新项目需要被特定意图路由到，在 `config/query-routing.yaml` 的 `intents` 中添加或修改意图：

```yaml
intents:
  new_project_query:
    description: "描述新项目的查询意图"
    projects:
      - <new-slug>
    record_data_required: true
    recommended_first_files:
      - "projects/<new-slug>/summary.md"
      - "projects/<new-slug>/agent-guide.md"
      - "projects/<new-slug>/semantic.json"
    recommended_tables:
      - <table-slug-1>
      - <table-slug-2>
```

如果新项目支持已有能力（如 `study_planning`），且该能力的 intent 使用 `selection: all_active_matching`，则新项目会自动被纳入候选，无需修改路由配置。

### 步骤 5：配置凭据

在 `config/credential-profiles.yaml` 中确保 `base_key` 对应的凭据已配置（或通过环境变量提供）。

### 步骤 6：本地验证

```bash
# 1. 配置校验
node scripts/validate-config.mjs

# 2. 同步新项目（需要飞书凭据环境变量）
node scripts/sync-project.mjs <new-slug>

# 3. 同步 Hub（构建 catalog、routing、AI-README）
node scripts/sync-hub.mjs

# 4. 语义校验
node scripts/validate-semantic.mjs

# 5. AI 文档校验
node scripts/validate-ai-docs.mjs

# 6. 安全扫描
node scripts/security-scan.mjs
```

### 步骤 7：确认产物

检查以下公开产物已正确生成：

- `public/projects/<new-slug>/semantic.json` — 语义映射
- `public/projects/<new-slug>/summary.md` — 项目说明
- `public/projects/<new-slug>/agent-guide.md` — AI 使用规则
- `public/catalog.json` — 包含新项目条目和索引
- `public/routing.json` — 包含新项目的路由（如适用）
- `public/AI-README.md` — 项目列表包含新项目

---

## 9. 文件索引

### 9.1 源文件（人工维护）

| 文件 | 职责 |
|---|---|
| `config/semantics/<slug>.yaml` | 项目语义配置（表角色、字段映射、能力声明） |
| `config/query-routing.yaml` | 查询路由配置（意图定义、读取层级） |
| `content/projects/<slug>/summary.md` | 项目业务说明 |
| `content/projects/<slug>/agent-guide.md` | AI 使用规则 |

### 9.2 代码文件

| 文件 | 职责 |
|---|---|
| `lib/semantic.mjs` | 语义配置加载、校验、semantic.json/routing.json 构建、受控词表定义 |
| `scripts/sync-project.mjs` | 项目同步，生成 semantic.json，复制 summary.md/agent-guide.md |
| `scripts/sync-hub.mjs` | Hub 编排，构建 catalog.json、routing.json、AI-README.md |
| `scripts/validate-semantic.mjs` | 语义配置与路由校验 |
| `scripts/validate-ai-docs.mjs` | AI 文档校验 |
| `scripts/security-scan.mjs` | 安全扫描 |
| `lib/security.mjs` | 安全扫描工具函数 |

### 9.3 公开产物

| 文件 | 职责 |
|---|---|
| `public/projects/<slug>/semantic.json` | 项目语义映射 |
| `public/routing.json` | 查询路由规则 |
| `public/catalog.json` | 全局项目目录（含语义扩展字段） |
| `public/AI-README.md` | AI 入口指南 |
| `public/projects/<slug>/summary.md` | 项目说明 |
| `public/projects/<slug>/agent-guide.md` | AI 使用规则 |

---

## 10. 相关文档

- `docs/SEMANTIC_LAYER_BASELINE.md` — 语义层升级前的基线状态
- `docs/AI_ROUTING.md` — AI 路由详细设计
- `docs/SEMANTIC_TYPES.md` — 受控词表完整说明
- `docs/PROJECT_SUMMARY_GUIDE.md` — summary.md 编写指南
- `docs/AGENT_GUIDE_AUTHORING.md` — agent-guide.md 编写指南
- `docs/SEMANTIC_LAYER_IMPLEMENTATION_REPORT.md` — 实施报告
- `docs/ARCHITECTURE.md` — Data Hub 整体架构
- `docs/SECURITY.md` — 安全设计
