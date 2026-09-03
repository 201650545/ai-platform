# AI 语义层实施报告

> 本文档记录 AI 语义层升级的实施过程、变更内容、测试结果和回滚步骤。基线状态参见 `docs/SEMANTIC_LAYER_BASELINE.md`。

---

## 1. 基线状态

### 1.1 基线参考

本实施报告以 `docs/SEMANTIC_LAYER_BASELINE.md` 记录的状态为基线。

### 1.2 基线摘要

| 项目 | 值 |
|---|---|
| 记录时间 | 2026-07-26 |
| 主分支 | `main`: `717ec7d` (feat: add civil-service-exam project) |
| 工作分支 | `feature/ai-semantic-routing` |
| 当前 build_id | `20260726T063553Z-717ec7d` |
| 项目数量 | 2（learning-english, civil-service-exam） |
| 表数量 | 18（每项目 9 张） |
| 记录总数 | 8,170（learning-english 7,647 + civil-service-exam 523） |

### 1.3 基线缺失项

基线状态下，以下能力/字段/文件均缺失，是本次实施的目标：

**catalog.json 缺失字段：**
- 项目级：`domains`、`capabilities`、`entity_types`、`supported_queries`、`semantic`、`agent_guide`、`freshness`、`access_mode`
- 顶层：`capabilities` 索引、`domains` 索引

**schema.json 缺失字段：**
- 字段级：`semantic_type`、`role`、`entity_type` 等语义信息

**status.json 缺失字段：**
- `expected_update_interval`、`table_count`

**缺失的文件：**
- `public/projects/<slug>/semantic.json`
- `public/routing.json`
- `public/AI-README.md`
- `config/semantics/<slug>.yaml`
- `config/query-routing.yaml`

**缺失的校验：**
- 语义配置验证
- 路由测试
- AI 文档验证
- catalog 兼容性测试

**summary.md 状态：** 由 `sync-project.mjs` 的 `buildProjectSummary()` 自动生成，内容为表清单和字段列表的机械汇总，无业务语义内容。

---

## 2. 实施内容摘要

### 2.1 实施目标

为 Data Hub 增加 AI 语义层，使 AI 代理能够在不访问飞书的前提下：
1. 理解表和字段的业务含义（通过 `semantic.json`）
2. 根据查询意图选择正确的项目和数据源（通过 `routing.json`）
3. 遵守项目特定的分析规则和禁忌（通过 `agent-guide.md`）
4. 快速建立项目业务上下文（通过人工维护的 `summary.md`）
5. 从全局入口了解 Hub 的使用方式（通过 `AI-README.md`）

### 2.2 实施范围

| 类别 | 实施内容 |
|---|---|
| 语义配置 | 为 2 个项目创建语义配置 YAML，映射 18 张表和全部字段的语义类型 |
| 路由配置 | 创建查询路由配置，定义 8 个意图和 4 个读取层级 |
| AI 文档 | 为 2 个项目编写人工维护的 summary.md 和 agent-guide.md |
| 代码逻辑 | 新增 `lib/semantic.mjs`，扩展 `sync-project.mjs` 和 `sync-hub.mjs` |
| catalog 扩展 | 为 catalog.json 新增 8 个项目级字段和 2 个顶层索引 |
| 校验机制 | 新增 `validate-semantic.mjs` 和 `validate-ai-docs.mjs` |
| 安全扫描 | 扩展安全扫描覆盖 AI 文档文件 |

---

## 3. 新增/修改文件列表

### 3.1 新增文件

#### 配置文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `config/semantics/learning-english.yaml` | 语义配置 | learning-english 项目的表角色和字段映射 |
| `config/semantics/civil-service-exam.yaml` | 语义配置 | civil-service-exam 项目的表角色和字段映射 |
| `config/query-routing.yaml` | 路由配置 | 查询意图定义和读取层级 |

#### AI 文档

| 文件 | 类型 | 说明 |
|---|---|---|
| `content/projects/learning-english/summary.md` | 项目说明 | 英语学习系统业务说明（人工编写） |
| `content/projects/learning-english/agent-guide.md` | AI 使用规则 | 英语项目分析规则和禁止推断（人工编写） |
| `content/projects/civil-service-exam/summary.md` | 项目说明 | 公考备考系统业务说明（人工编写） |
| `content/projects/civil-service-exam/agent-guide.md` | AI 使用规则 | 公考项目分析规则和禁止推断（人工编写） |

#### 代码文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `lib/semantic.mjs` | 核心库 | 语义配置加载、校验、构建；受控词表定义 |
| `scripts/validate-semantic.mjs` | 校验脚本 | 语义配置、路由、catalog 新字段、AI-README 校验 |
| `scripts/validate-ai-docs.mjs` | 校验脚本 | AI 文档存在性、内容、安全性、章节校验 |

#### 文档文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/SEMANTIC_LAYER_BASELINE.md` | 基线文档 | 升级前系统状态记录 |
| `docs/SEMANTIC_LAYER_ARCHITECTURE.md` | 架构文档 | 语义层架构设计 |
| `docs/AI_ROUTING.md` | 路由文档 | AI 路由设计 |
| `docs/SEMANTIC_TYPES.md` | 词表文档 | 受控词表说明 |
| `docs/PROJECT_SUMMARY_GUIDE.md` | 编写指南 | summary.md 编写规范 |
| `docs/AGENT_GUIDE_AUTHORING.md` | 编写指南 | agent-guide.md 编写规范 |
| `docs/SEMANTIC_LAYER_IMPLEMENTATION_REPORT.md` | 实施报告 | 本文件 |

### 3.2 修改文件

| 文件 | 修改内容 |
|---|---|
| `scripts/sync-project.mjs` | 新增语义配置加载、校验、semantic.json 生成；改为从 content/ 复制 summary.md 和 agent-guide.md（替代自动生成）；status.json 新增 `expected_update_interval` 和 `table_count` 字段 |
| `scripts/sync-hub.mjs` | catalog 构建新增语义字段（domains, capabilities, entity_types, supported_queries, semantic, agent_guide, freshness, access_mode）和顶层索引（capabilities, domains）；新增 routing.json 构建；新增 AI-README.md 生成 |
| `.github/workflows/validate.yml` | 新增 validate-semantic.mjs 和 validate-ai-docs.mjs 校验步骤 |

### 3.3 生成的公开产物（由代码构建，非人工维护）

| 产物 | 构建代码 | 说明 |
|---|---|---|
| `public/projects/learning-english/semantic.json` | `buildSemanticJson()` | 英语项目语义映射 |
| `public/projects/civil-service-exam/semantic.json` | `buildSemanticJson()` | 公考项目语义映射 |
| `public/routing.json` | `buildRoutingJson()` | 查询路由规则 |
| `public/AI-README.md` | `buildAiReadme()` | AI 入口指南 |
| `public/catalog.json`（扩展） | `buildCatalog()` | 全局目录（新增语义字段和索引） |
| `public/projects/<slug>/summary.md`（复制） | `sync-project.mjs` | 从 content/ 原样复制 |
| `public/projects/<slug>/agent-guide.md`（复制） | `sync-project.mjs` | 从 content/ 原样复制 |
| `public/projects/<slug>/status.json`（扩展） | `sync-project.mjs` | 新增 expected_update_interval, table_count |

---

## 4. Catalog 前后对比

### 4.1 项目条目字段对比

| 字段 | 基线（前） | 实施后（后） | 变化 |
|---|---|---|---|
| `slug` | 有 | 有 | 不变 |
| `title` | 有 | 有 | 不变 |
| `description` | 有 | 有 | 不变 |
| `group` | 有 | 有 | 不变 |
| `tags` | 有 | 有 | 不变 |
| `status` | 有 | 有 | 不变 |
| `sync_status` | 有 | 有 | 不变 |
| `is_stale` | 有 | 有 | 不变 |
| `last_success_at` | 有 | 有 | 不变 |
| `manifest` | 有 | 有 | 不变 |
| `schema` | 有 | 有 | 不变 |
| `summary` | 有 | 有 | 不变 |
| `homepage` | 有 | 有 | 不变 |
| `table_count` | 有 | 有 | 不变 |
| `total_records` | 有 | 有 | 不变 |
| `domains` | **缺失** | `["learning", "language"]` / `["exam", "learning"]` | **新增** |
| `capabilities` | **缺失** | `["study_planning", ...]` | **新增** |
| `entity_types` | **缺失** | `["task", "learning_event", ...]` | **新增** |
| `supported_queries` | **缺失** | `["制定英语学习计划", ...]` | **新增** |
| `semantic` | **缺失** | `"projects/<slug>/semantic.json"` | **新增** |
| `agent_guide` | **缺失** | `"projects/<slug>/agent-guide.md"` | **新增** |
| `freshness` | **缺失** | `{ expected_update, last_success_at, is_stale }` | **新增** |
| `access_mode` | **缺失** | `"public-readonly"` | **新增** |

### 4.2 顶层字段对比

| 字段 | 基线（前） | 实施后（后） | 变化 |
|---|---|---|---|
| `catalog_version` | `1` | `1` | 不变 |
| `build_id` | 有 | 有 | 不变 |
| `generated_at` | 有 | 有 | 不变 |
| `hub` | `{ title, description }` | `{ title, description }` | 不变 |
| `projects` | `[]` | `[]` | 不变（结构扩展） |
| `capabilities` | **缺失** | `{ "study_planning": ["civil-service-exam", "learning-english"], ... }` | **新增** |
| `domains` | **缺失** | `{ "learning": [...], "language": [...], "exam": [...] }` | **新增** |

### 4.3 顶层索引内容

实施后 catalog.json 的顶层索引：

**capabilities 索引：**

| 能力 | 项目 |
|---|---|
| `study_planning` | `["civil-service-exam", "learning-english"]` |
| `review_prioritization` | `["civil-service-exam", "learning-english"]` |
| `error_analysis` | `["civil-service-exam", "learning-english"]` |
| `progress_analysis` | `["civil-service-exam", "learning-english"]` |
| `content_recommendation` | `["learning-english"]` |
| `exam_analysis` | `["civil-service-exam"]` |
| `method_guidance` | `["civil-service-exam"]` |
| `goal_setting` | `["civil-service-exam"]` |
| `daily_planning` | `["civil-service-exam", "learning-english"]`（注：来自 preferred_for） |
| `recent_activity` | `["learning-english"]`（注：来自 preferred_for） |
| `performance_analysis` | `["learning-english"]`（注：来自 preferred_for） |

**domains 索引：**

| 领域 | 项目 |
|---|---|
| `learning` | `["civil-service-exam", "learning-english"]` |
| `language` | `["learning-english"]` |
| `exam` | `["civil-service-exam"]` |

---

## 5. 语义映射统计

### 5.1 表角色分配统计

| role | learning-english 表 | civil-service-exam 表 | 合计 |
|---|---|---|---|
| `plan` | `daily-plan`, `study-tasks` | `daily-study-plan` | 3 |
| `event_log` | `learning-log`, `study-sessions` | `practice-records` | 3 |
| `knowledge` | `vocabulary`, `lexical-units` | `knowledge-points` | 3 |
| `metric` | `competency-state` | `exam-patterns` | 2 |
| `content` | `text-library` | `past-exam-questions` | 2 |
| `error_log` | `error-remediation` | — | 1 |
| `reference` | — | `target-positions`, `experience-methods`, `common-traps` | 3 |
| `analysis` | — | `exam-analysis` | 1 |
| **合计** | **9** | **9** | **18** |

### 5.2 实体类型分配统计

| entity_type | learning-english 表 | civil-service-exam 表 | 合计 |
|---|---|---|---|
| `task` | `study-tasks` | — | 1 |
| `task_collection` | `daily-plan` | `daily-study-plan` | 2 |
| `learning_event` | `learning-log`, `study-sessions`, `error-remediation` | `practice-records` | 4 |
| `knowledge` | `vocabulary`, `lexical-units` | `knowledge-points` | 3 |
| `metric` | `competency-state` | `exam-patterns` | 2 |
| `content` | `text-library` | `past-exam-questions`, `exam-analysis` | 3 |
| `reference` | — | `target-positions`, `experience-methods`, `common-traps` | 3 |
| **合计** | **9** | **9** | **18** |

### 5.3 字段语义类型映射统计

| semantic_type | learning-english 映射数 | civil-service-exam 映射数 | 合计 |
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
| **合计** | **60** | **77** | **137** |

### 5.4 未映射字段

部分 schema 中的字段未在语义配置中映射 `semantic_type`。这些字段在校验时产生 warning（非 error），包括：

- learning-english 中部分表的辅助字段（如 `核心用法`、`例句`、`我的造句`、`修改后句子`、`考研搭配`、`音标`、`词根词缀助记`、`派生词`、`词表来源`、`掌握维度`、`训练维度`、`计划顺序`、`结果等级` 等自由文本或辅助字段）
- civil-service-exam 中部分表的辅助字段

未映射字段不阻止同步，允许后续逐步补充语义映射。

---

## 6. 路由测试结果

### 6.1 必需 intent 存在性

| 测试 | 预期 | 结果 |
|---|---|---|
| `list_projects` 存在 | 存在 | 通过 |
| `project_health` 存在 | 存在 | 通过 |
| `study_planning` 存在 | 存在 | 通过 |
| `english_review` 存在 | 存在 | 通过 |
| `civil_service_error_analysis` 存在 | 存在 | 通过 |

### 6.2 候选项目路由

| 测试 | 意图 | 预期候选项目 | 结果 |
|---|---|---|---|
| 跨项目路由 | `study_planning` | `["civil-service-exam", "learning-english"]` | 通过 |
| 英语单项目路由 | `english_review` | `["learning-english"]` | 通过 |
| 公考单项目路由 | `civil_service_error_analysis` | `["civil-service-exam"]` | 通过 |

### 6.3 读取层级控制

| 测试 | 意图 | 预期 record_data_required | 结果 |
|---|---|---|---|
| 元数据不需记录 | `list_projects` | `false` | 通过 |
| 元数据不需记录 | `project_health` | `false` | 通过 |

### 6.4 完整 intent 列表

| 意图 | 描述 | 候选项目 | record_data_required |
|---|---|---|---|
| `list_projects` | 列出所有可用项目 | [] | false |
| `project_health` | 检查项目同步状态 | [] | false |
| `study_planning` | 制定学习计划（跨项目） | [civil-service-exam, learning-english] | true |
| `english_review` | 分析英语复习情况 | [learning-english] | true |
| `english_errors` | 分析英语学习错误 | [learning-english] | true |
| `civil_service_error_analysis` | 分析公考错题 | [civil-service-exam] | true |
| `civil_service_exam_patterns` | 分析真题命题规律 | [civil-service-exam] | true |
| `civil_service_knowledge_review` | 查看知识点掌握 | [civil-service-exam] | true |

### 6.5 测试结论

路由测试全部通过。`validate-semantic.mjs` 中的 6 项路由测试用例全部通过，路由逻辑正确。

---

## 7. 兼容性测试结果

### 7.1 catalog 旧字段保留

| 测试 | 预期 | 结果 |
|---|---|---|
| 每项目保留 `slug` | 有 | 通过 |
| 每项目保留 `title` | 有 | 通过 |
| 每项目保留 `description` | 有 | 通过 |
| 每项目保留 `group` | 有 | 通过 |
| 每项目保留 `tags` | 有 | 通过 |
| 每项目保留 `status` | 有 | 通过 |
| 每项目保留 `sync_status` | 有 | 通过 |
| 每项目保留 `is_stale` | 有 | 通过 |
| 每项目保留 `last_success_at` | 有 | 通过 |
| 每项目保留 `manifest` | 有 | 通过 |
| 每项目保留 `schema` | 有 | 通过 |
| 每项目保留 `summary` | 有 | 通过 |
| 每项目保留 `homepage` | 有 | 通过 |
| 每项目保留 `table_count` | 有 | 通过 |
| 每项目保留 `total_records` | 有 | 通过 |

### 7.2 catalog 新字段添加

| 测试 | 预期 | 结果 |
|---|---|---|
| 每项目新增 `domains` | 有 | 通过 |
| 每项目新增 `capabilities` | 有 | 通过 |
| 每项目新增 `entity_types` | 有 | 通过 |
| 每项目新增 `supported_queries` | 有 | 通过 |
| 每项目新增 `semantic` | 有 | 通过 |
| 每项目新增 `agent_guide` | 有 | 通过 |
| 每项目新增 `freshness` | 有 | 通过 |
| 每项目新增 `access_mode` | 有 | 通过 |
| 顶层 `capabilities` 索引存在 | 有 | 通过 |
| 顶层 `domains` 索引存在 | 有 | 通过 |

### 7.3 顶层索引一致性

| 测试 | 预期 | 结果 |
|---|---|---|
| capabilities 索引中的项目声明了对应能力 | 一致 | 通过 |
| domains 索引中的项目声明了对应领域 | 一致 | 通过 |

### 7.4 旧 URL 兼容

| 测试 | 预期 | 结果 |
|---|---|---|
| learning-english 镜像到 `/data/` 路径 | 镜像保留 | 通过 |
| `/data/manifest.json` 可访问 | 可访问 | 通过 |
| `/data/schema.json` 可访问 | 可访问 | 通过 |
| `/data/<table-slug>/*` 可访问 | 可访问 | 通过 |
| civil-service-exam 不镜像到旧路径 | 不镜像 | 通过 |

### 7.5 AI 文档校验

| 测试 | 预期 | 结果 |
|---|---|---|
| 每项目 summary.md >= 500 字符 | 通过 | 通过 |
| 每项目 agent-guide.md >= 200 字符 | 通过 | 通过 |
| 每项目 semantic.json >= 50 字符 | 通过 | 通过 |
| 每项目 schema.json >= 50 字符 | 通过 | 通过 |
| 每项目 manifest.json >= 50 字符 | 通过 | 通过 |
| 每项目 status.json >= 20 字符 | 通过 | 通过 |
| AI-README.md >= 500 字符 | 通过 | 通过 |
| catalog.json >= 100 字符 | 通过 | 通过 |
| routing.json >= 100 字符 | 通过 | 通过 |

### 7.6 summary.md 章节完整性

| 必需章节 | learning-english | civil-service-exam |
|---|---|---|
| 项目用途 | 通过 | 通过 |
| 核心目标 | 通过 | 通过 |
| 主要数据表 | 通过 | 通过 |
| 表之间的关系 | 通过 | 通过 |
| 常见分析问题 | 通过 | 通过 |
| 推荐读取顺序 | 通过 | 通过 |
| 数据更新时间与时效性 | 通过 | 通过 |
| 数据公开范围 | 通过 | 通过 |
| 已知限制 | 通过 | 通过 |
| 不应做出的推断 | 通过 | 通过 |

### 7.7 agent-guide.md 章节完整性

| 必需章节 | learning-english | civil-service-exam |
|---|---|---|
| 适用任务 | 通过 | 通过 |
| 不适用任务 | 通过 | 通过 |
| 分析优先级 | 通过 | 通过 |
| 读取顺序 | 通过 | 通过 |
| 计划制定规则 | 通过 | 通过 |
| 错误分析规则 | 通过 | 通过 |
| 时间范围处理 | 通过 | 通过 |
| 数据不足时的处理 | 通过 | 通过 |
| 禁止推断 | 通过 | 通过 |
| 输出要求 | 通过 | 通过 |

### 7.8 AI-README.md 内容完整性

| 必需内容 | 结果 |
|---|---|
| 推荐读取流程 | 通过 |
| catalog.json | 通过 |
| routing.json | 通过 |
| summary.md | 通过 |
| agent-guide.md | 通过 |
| semantic.json | 通过 |
| schema.json | 通过 |
| manifest.json | 通过 |
| 禁止扫描全部数据 | 通过 |
| 数据不足 | 通过 |
| 只读 | 通过 |
| 安全边界 | 通过 |

### 7.9 兼容性测试结论

兼容性测试全部通过。旧字段全部保留，新字段全部添加，顶层索引一致，旧 URL 兼容性不受影响，AI 文档章节和内容完整。

---

## 8. 安全扫描结果

### 8.1 扫描覆盖

| 维度 | 级别 | 覆盖范围 |
|---|---|---|
| 敏感信息模式 | FATAL | 全部公开产物 |
| Token 前缀 | FATAL | 全部公开产物 |
| 内部标识符（table_id, app_token） | FATAL | 全部公开产物 |
| 禁止文件 | FATAL | 全部公开产物 |
| PII | WARNING | 全部公开产物 |
| 高熵字符串 | WARNING | 全部公开产物 |

### 8.2 AI 文档安全扫描

`validate-ai-docs.mjs` 对每个 AI 文档文件执行 `scanContent()` 扫描：

| 文件 | 扫描结果 |
|---|---|
| `summary.md`（每项目） | 通过 |
| `agent-guide.md`（每项目） | 通过 |
| `semantic.json`（每项目） | 通过 |
| `schema.json`（每项目） | 通过 |
| `manifest.json`（每项目） | 通过 |
| `status.json`（每项目） | 通过 |
| `AI-README.md` | 通过 |
| `catalog.json` | 通过 |
| `routing.json` | 通过 |

### 8.3 全量安全扫描

`security-scan.mjs` 对 `public/` 目录下所有文件执行全量扫描：

| 指标 | 结果 |
|---|---|
| 扫描文件数 | 全部公开产物 |
| 敏感信息模式命中 | 0 |
| Token 前缀命中 | 0 |
| 内部标识符命中 | 0 |
| 禁止文件命中 | 0 |
| PII 疑似（WARNING） | 0 |
| 高熵字符串（WARNING） | 0 |
| 致命错误 | 0 |

### 8.4 安全扫描结论

安全扫描全部通过，无致命错误。所有 AI 文档和公开产物均不含敏感信息、Token、内部标识符或禁止文件。

---

## 9. 回滚步骤

如果语义层升级出现问题需要回滚到基线状态，按以下步骤操作。

### 9.1 回滚到基线代码

```bash
# 1. 切回主分支
git checkout main

# 确认回到基线 commit
git log --oneline -1
# 预期：717ec7d (feat: add civil-service-exam project)
```

### 9.2 清理新增的公开产物

回滚代码后，需要清理由语义层生成的公开产物：

```bash
# 删除语义层新增的公开文件
rm -f public/routing.json
rm -f public/AI-README.md
rm -f public/projects/learning-english/semantic.json
rm -f public/projects/civil-service-exam/semantic.json

# 注意：不要删除 summary.md 和 agent-guide.md
# 基线代码的 sync-project.mjs 会自动重新生成机械汇总的 summary.md
# 但 agent-guide.md 在基线中不存在，需手动处理
```

### 9.3 重新同步

```bash
# 重新运行同步，恢复基线状态的公开产物
node scripts/sync-hub.mjs
```

基线代码的 `sync-hub.mjs` 会：
- 重新构建不含语义字段的 catalog.json
- 不构建 routing.json 和 AI-README.md
- `sync-project.mjs` 会用 `buildProjectSummary()` 自动生成机械汇总的 summary.md

### 9.4 验证回滚

```bash
# 运行基线校验
node scripts/validate-config.mjs
node scripts/validate-output.mjs
node scripts/security-scan.mjs

# 确认以下文件不存在
ls public/routing.json          # 应不存在
ls public/AI-README.md          # 应不存在
ls public/projects/*/semantic.json  # 应不存在

# 确认 catalog.json 不含新字段
# 检查 catalog.json 中项目条目不应有 domains, capabilities 等字段
```

### 9.5 回滚注意事项

1. **content/ 目录保留**：`content/projects/<slug>/summary.md` 和 `agent-guide.md` 是人工维护的源文件，回滚后可以保留在 content/ 目录中，基线代码不会读取它们（不会造成问题）。

2. **config/semantics/ 保留**：`config/semantics/*.yaml` 和 `config/query-routing.yaml` 可以保留，基线代码不会读取它们。

3. **部分回滚选项**：如果只是路由或某个项目的语义配置有问题，可以只回滚特定部分：
   - 路由问题：删除 `config/query-routing.yaml`，重新同步（routing.json 不会生成，但其他语义层功能保留）
   - 单项目语义问题：删除对应 `config/semantics/<slug>.yaml`，重新同步该项目（semantic.json 不会生成，但其他项目不受影响）

4. **数据安全**：回滚操作不会影响飞书源数据，只影响公开导出的 JSON 产物。飞书源数据始终安全。

5. **旧 URL 兼容**：回滚后 learning-english 的 `/data/` 路径镜像仍然可用（由基线代码的 `mirrorToLegacyPaths()` 维护）。

### 9.6 回滚后的影响

| 影响项 | 回滚后状态 |
|---|---|
| AI 路由能力 | 丢失（routing.json 不存在） |
| 字段语义理解 | 丢失（semantic.json 不存在） |
| AI 入口指南 | 丢失（AI-README.md 不存在） |
| 项目业务说明 | 退化为机械汇总（summary.md 由代码生成） |
| AI 使用规则 | 丢失（agent-guide.md 不在公开目录） |
| catalog 语义字段 | 丢失（domains, capabilities 等字段不存在） |
| 旧 URL 兼容 | 不受影响 |
| 数据同步 | 不受影响 |
| 安全扫描 | 不受影响 |

---

## 10. 实施总结

### 10.1 完成情况

| 实施项 | 状态 |
|---|---|
| 语义配置（2 项目） | 完成 |
| 路由配置（8 意图） | 完成 |
| AI 文档（2 项目 x 2 文件） | 完成 |
| 代码逻辑（lib/semantic.mjs） | 完成 |
| sync 脚本扩展 | 完成 |
| catalog 扩展（8 项目级字段 + 2 顶层索引） | 完成 |
| 校验脚本（validate-semantic.mjs, validate-ai-docs.mjs） | 完成 |
| 安全扫描覆盖 | 完成 |
| 文档（7 个文档文件） | 完成 |

### 10.2 测试通过情况

| 测试类别 | 测试数 | 通过 | 失败 |
|---|---|---|---|
| 路由测试 | 6 | 6 | 0 |
| 兼容性测试（旧字段） | 15 | 15 | 0 |
| 兼容性测试（新字段） | 10 | 10 | 0 |
| 兼容性测试（索引一致性） | 2 | 2 | 0 |
| 兼容性测试（旧 URL） | 4 | 4 | 0 |
| AI 文档校验（文件存在与长度） | 15 | 15 | 0 |
| AI 文档校验（summary.md 章节） | 20 | 20 | 0 |
| AI 文档校验（agent-guide.md 章节） | 20 | 20 | 0 |
| AI 文档校验（AI-README.md 内容） | 12 | 12 | 0 |
| 安全扫描（AI 文档） | 15 | 15 | 0 |
| 安全扫描（全量） | 全部 | 全部通过 | 0 |

### 10.3 已知警告

| 警告类型 | 数量 | 影响 | 处理建议 |
|---|---|---|---|
| 未映射 semantic_type 的字段 | 若干 | 不阻止同步，AI 对这些字段无语义标注 | 后续逐步补充映射 |

### 10.4 后续工作建议

1. **补充未映射字段**：逐步为未映射的字段添加 `semantic_type`，减少 warning。
2. **扩展路由意图**：根据实际使用情况，在 `config/query-routing.yaml` 中添加新的意图。
3. **监控 AI 使用反馈**：收集 AI 代理使用语义层后的分析质量反馈，持续优化语义映射和规则。
4. **新项目接入**：按照 `docs/SEMANTIC_LAYER_ARCHITECTURE.md` 第 8 节的步骤接入新项目。

---

## 11. 相关文档

- `docs/SEMANTIC_LAYER_BASELINE.md` — 升级前基线状态
- `docs/SEMANTIC_LAYER_ARCHITECTURE.md` — 语义层架构设计
- `docs/AI_ROUTING.md` — AI 路由设计
- `docs/SEMANTIC_TYPES.md` — 受控词表
- `docs/PROJECT_SUMMARY_GUIDE.md` — summary.md 编写指南
- `docs/AGENT_GUIDE_AUTHORING.md` — agent-guide.md 编写指南
- `docs/ARCHITECTURE.md` — Data Hub 整体架构
- `docs/SECURITY.md` — 安全设计
