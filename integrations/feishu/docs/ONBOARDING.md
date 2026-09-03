# 新项目接入指南

> **迁移说明（2026-09-03）**
> 本模块已由独立仓 `feishu-data-hub` 迁入 AI 平台主仓 `ai-platform`，位于 `integrations/feishu/`。
> 下文中的站点 URL 已按新仓 Pages 根 `https://201650545.github.io/ai-platform/` 更新；若集成时 Pages 源配置为子路径或
> 自定义域名，请同步替换。旧站点 `https://201650545.github.io/feishu-data-hub/` 已失效。
> 详见 [MIGRATION-NOTE.md](../MIGRATION-NOTE.md)。


本文档提供将一个新的飞书 Base 接入 Feishu Data Hub 的完整步骤，以及 AI 代理（Agent）协作时的修改权限边界。

---

## 1. 接入工作流概览

将一个新的飞书 Base 接入 Data Hub 需要以下 10 个步骤：

```
① 接入 Base（创建视图 + 授权 + 注册 Secret）
② 配置表和字段导出
③ 编写 summary（content/projects/<slug>/summary.md）
④ 编写 agent-guide（content/projects/<slug>/agent-guide.md）
⑤ 添加 semantic 映射（config/semantics/<slug>.yaml）
⑥ 声明 domains 和 capabilities
⑦ 运行项目同步
⑧ 运行语义校验（node scripts/validate-semantic.mjs）
⑨ 运行路由测试（检查 routing.json 中的 intents）
⑩ 发布并验证
```

---

## 2. 详细步骤

### 步骤 1：接入 Base

接入 Base 包含三个子步骤：创建 `AI 公开导出` 视图、给飞书应用授权、以及注册 Base 到 GitHub Secret。

#### 1.1 创建 "AI 公开导出" 视图

在飞书 Base 中，为每张需要公开导出的数据表创建一个名为 `AI 公开导出` 的表格视图。

1. 打开目标飞书 Base
2. 导航到需要导出的数据表
3. 点击视图标签栏最后的 `+` 按钮
4. 选择 **表格视图**（Grid View）
5. 名称必须精确为 `AI 公开导出`（含中间的空格，区分大小写）
6. 该视图默认继承所有字段——字段级别的过滤由项目 YAML 中的 `fields` 白名单控制

**注意事项**：
- 视图名称必须精确匹配 `AI 公开导出`，其他名称不会被识别
- 没有此视图的表不会被导出（除非在 YAML 中显式配置且 `require_export_view: false`）
- 建议在视图中按需隐藏不需要公开的列（额外安全层，但主要过滤仍依赖字段白名单）

#### 1.2 给统一飞书应用授予只读权限

将 Data Hub 使用的飞书应用添加为目标 Base 的协作者，授予只读权限。

1. 在飞书 Base 中打开 **设置** → **协作者管理**（或 **添加协作者**）
2. 搜索并添加 Data Hub 使用的飞书应用
3. 权限设为 **只读**（可查看）
4. 确认应用可以看到所有需要导出的表

**安全要求**：
- 只授予只读权限，绝不授予编辑权限
- 应用权限范围已在 `credential-profiles.yaml` 中定义为 `bitable:app:readonly` 和 `bitable:app`
- 多个 Base 共用同一个飞书应用，通过 `FEISHU_BASE_REGISTRY_JSON` 中的 `app_token` 区分

#### 1.3 更新 FEISHU_BASE_REGISTRY_JSON Secret

在 GitHub 仓库的 Settings → Secrets and variables → Actions 中，编辑 `FEISHU_BASE_REGISTRY_JSON` Secret，添加新项目的 Base 条目。

`FEISHU_BASE_REGISTRY_JSON` 的格式是一个 JSON 对象，key 为 base_key，value 为包含 app_token 的对象：

```json
{
  "learning-english": {
    "app_token": "REDACTED_APP_TOKEN_1"
  },
  "new-project-slug": {
    "app_token": "REDACTED_APP_TOKEN_2"
  }
}
```

**操作步骤**：
1. 获取新 Base 的 app_token（飞书 Base URL 中 `/base/` 后面的部分，或通过 API 获取）
2. 在 GitHub Secrets 中编辑 `FEISHU_BASE_REGISTRY_JSON`
3. 添加新的 key-value 条目，key 为项目 YAML 中 `source.base_key` 的值
4. 保存 Secret

**注意**：`app_token` 是敏感信息，只存在于 GitHub Secrets 中，绝不写入代码或配置文件。

### 步骤 2：配置表和字段导出

使用脚手架命令创建项目配置文件：

```bash
npm run project:add -- --slug <slug> --title "项目标题" --base-key <base-key> [options]
```

**必填参数**：
- `--slug`：项目 slug（小写字母、数字、连字符，如 `reading-notes`）
- `--title`：项目标题（如 `阅读笔记`）
- `--base-key`：飞书 Base 在注册表中的 key（与步骤 3 中的 key 一致）

**可选参数**：
- `--group`：项目分组（默认 `general`）
- `--schedule`：同步频率，`hourly` 或 `daily`（默认 `hourly`）
- `--description`：项目描述

**示例**：

```bash
npm run project:add -- \
  --slug reading-notes \
  --title "阅读笔记" \
  --base-key reading-notes \
  --group knowledge \
  --schedule daily \
  --description "阅读记录与笔记导出"
```

该命令会：
1. 创建 `config/projects/<slug>.yaml`（基于 `templates/project.example.yaml`）
2. 创建 `config/projects/<slug>.summary.md`（基于 `templates/summary.example.md`）
3. 输出后续步骤说明

**编辑项目配置**：

创建后，需要编辑 `config/projects/<slug>.yaml`，添加需要导出的表和字段白名单：

```yaml
tables:
  - table_name: "书单"
    table_slug: book-list
    view_name: "AI 公开导出"
    enabled: true
    fields:
      - "书名"
      - "作者"
      - "分类"
      - "评分"
      - "阅读状态"
```

**字段白名单规则**：
- 必须显式列出每个要导出的字段名
- **禁止使用通配符 `*`**
- **禁止空数组**
- **禁止包含敏感字段名**：`app_secret`、`tenant_access_token`、`user_access_token`、`authorization`、`client_secret`、`github_token`、`cookie`
- 字段名不能重复

也可以不配置 `tables`，改为自动发现模式（导出所有带 `AI 公开导出` 视图的表及其全部字段）。但出于安全考虑，**强烈建议显式配置表和字段白名单**。

### 步骤 3：编写 summary（content/projects/<slug>/summary.md）

项目摘要文件是 AI 代理理解项目数据的关键入口。该文件位于 `content/projects/<slug>/summary.md`，由人工维护，同步时复制到公开输出目录。

`npm run project:add` 脚手架命令会基于 `templates/summary.example.md` 创建初始模板，但必须编辑为真实内容。

**必须包含以下章节**（`validate-ai-docs.mjs` 会检查）：

1. **项目用途** — 说明数据的来源和用途
2. **核心目标** — 列出数据系统要解决的核心问题
3. **主要数据表** — 每张表的 slug、记录数、字段数和用途
4. **表之间的关系** — 说明表间关联字段和关联方向
5. **常见分析问题** — 列出该数据适合回答的典型问题
6. **推荐读取顺序** — AI 代理读取数据的优先级顺序
7. **数据更新时间与时效性** — 同步频率和数据时效说明
8. **数据公开范围** — 说明哪些数据被导出、哪些被过滤
9. **已知限制** — 数据的已知不足和不支持的场景
10. **不应做出的推断** — 明确禁止 AI 基于该数据做出的推断

**要求**：
- 内容长度不少于 500 字符（`validate-semantic.mjs` 检查）
- 不得包含敏感信息（`validate-output.mjs` 安全扫描）
- 章节标题必须精确匹配上述名称

### 步骤 4：编写 agent-guide（content/projects/<slug>/agent-guide.md）

AI 使用规则文件规定 AI 代理在分析项目数据时必须遵守的规则。该文件位于 `content/projects/<slug>/agent-guide.md`，由人工维护，同步时复制到公开输出目录。

**必须包含以下章节**（`validate-ai-docs.mjs` 会检查）：

1. **适用任务** — 列出该数据适合的 AI 任务
2. **不适用任务** — 列出该数据不适合的任务，AI 应拒绝或说明限制
3. **分析优先级** — AI 处理请求时的优先级排序
4. **读取顺序** — AI 读取数据表的推荐顺序
5. **计划制定规则** — 如何基于数据制定计划
6. **错误分析规则** — 如何分析错误数据
7. **时间范围处理** — 如何处理时间范围相关查询
8. **数据不足时的处理** — 当数据不足时 AI 应如何响应
9. **禁止推断** — 明确禁止的推断类型
10. **输出要求** — AI 输出格式和内容要求

**要求**：
- 内容长度不少于 200 字符（`validate-ai-docs.mjs` 检查）
- 所有规则必须基于真实 schema 和 manifest 数据，不依赖虚构字段
- 不得包含敏感信息（`validate-output.mjs` 安全扫描）

### 步骤 5：添加 semantic 映射（config/semantics/<slug>.yaml）

语义映射配置将数据表的字段映射到受控语义类型，使 AI 代理能理解每个字段的语义角色。该文件位于 `config/semantics/<slug>.yaml`，由人工维护，**不可自动生成**。

**文件结构**：

```yaml
semantic_version: 1

project:
  slug: <slug>
  domains:          # 见步骤 6
    - <domain>
  entity_types:     # 项目中出现的实体类型
    - task
    - knowledge
  capabilities:     # 见步骤 6
    - <capability>
  supported_queries: # 项目支持的自然语言查询示例
    - "示例查询"

tables:
  <table-slug>:           # 与 manifest 中的 table slug 一致
    role: content          # 受控角色：content / knowledge / event_log / plan / metric / error_log
    entity_type: content   # 受控实体类型
    preferred_for:         # 该表优先支持的能力
      - content_recommendation
    primary_display_field: "字段名"  # 主显示字段
    date_field: "字段名"             # 日期字段（可为 null）
    status_field: "字段名"           # 状态字段

fields:
  <table-slug>:
    "飞书字段名":
      semantic_type: entity_identity_title  # 受控语义类型
```

**受控词汇表**（定义在 `lib/semantic.mjs` 中，`validate-semantic.mjs` 会校验）：
- **TABLE_ROLES**：`content`、`knowledge`、`event_log`、`plan`、`metric`、`error_log` 等
- **ENTITY_TYPES**：`task`、`learning_event`、`knowledge`、`metric`、`content`、`task_collection` 等
- **SEMANTIC_TYPES**：`entity_identity_title`、`content_text`、`event_date`、`review_due_at`、`mastery_level`、`status`、`difficulty`、`relation`、`accuracy`、`score`、`task_status`、`planned_date`、`due_date`、`task_title`、`knowledge_topic`、`attempt_count`、`duration_minutes`、`confidence`、`task_priority`、`error_type`、`outcome` 等

**要求**：
- 每张在 manifest 中启用的表都必须在 `tables` 中声明 role 和 entity_type
- `tables` 中的 slug 必须与 manifest/schema 中的 table slug 完全一致
- `fields` 中的字段名必须与 schema.json 中的 field_name 完全一致
- `semantic_type` 必须使用受控词汇表中的值

### 步骤 6：声明 domains 和 capabilities

在 `config/semantics/<slug>.yaml` 的 `project` 段中声明项目的领域（domains）和能力（capabilities）。这些声明会被同步到 `catalog.json` 的顶层索引中，并用于 `routing.json` 的意图路由。

**domains（领域）**：
- 描述项目所属的知识领域
- 例如：`learning`、`language`、`exam`、`knowledge` 等
- 用于 `catalog.json` 顶层 `domains` 索引和首页筛选

**capabilities（能力）**：
- 描述项目数据支持的 AI 任务能力
- 例如：`study_planning`、`review_prioritization`、`error_analysis`、`progress_analysis`、`content_recommendation` 等
- 用于 `catalog.json` 顶层 `capabilities` 索引和 `routing.json` 路由匹配

**entity_types（实体类型）**：
- 描述项目中出现的实体类型
- 例如：`task`、`learning_event`、`knowledge`、`metric`、`content` 等

**supported_queries（支持的查询）**：
- 列出项目支持的自然语言查询示例
- 帮助 AI 代理理解项目数据的适用场景

**示例**（参考 `config/semantics/learning-english.yaml`）：

```yaml
project:
  slug: learning-english
  domains:
    - learning
    - language
  entity_types:
    - task
    - learning_event
    - knowledge
    - metric
    - content
  capabilities:
    - study_planning
    - review_prioritization
    - error_analysis
    - progress_analysis
    - content_recommendation
  supported_queries:
    - "制定英语学习计划"
    - "分析需要复习的内容"
    - "分析学习错误"
```

同步后，`catalog.json` 中每个项目条目会新增 `domains`、`capabilities`、`entity_types`、`supported_queries`、`semantic`、`agent_guide`、`freshness`、`access_mode` 字段，顶层会生成 `domains` 和 `capabilities` 反向索引。

### 步骤 7：运行项目同步

在本地或通过 GitHub Actions 进行 dry-run 同步，验证配置正确性。

**本地 dry-run**：

```bash
# 设置环境变量（使用真实的飞书凭据）
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_REGISTRY_JSON='{"new-project-slug": {"app_token": "xxxx"}, "learning-english": {"app_token": "xxxx"}}'

# 单项目 dry-run
node scripts/sync-hub.mjs --project new-project-slug --dry-run
```

**通过 GitHub Actions dry-run**：

1. 在 GitHub 仓库的 Actions 页面选择 **Manual Sync** 工作流
2. 点击 **Run workflow**
3. 设置 `project_slug` 为新项目 slug
4. 勾选 `dry_run`
5. 运行并查看日志

Dry-run 模式下：
- 同步代码会执行，但不会写入 `public/` 目录
- 不会触发部署
- 用于验证飞书 API 连接、表发现、字段匹配是否正常

#### 7.1 安全扫描

在 dry-run 确认无误后，进行实际同步并运行安全扫描。

**通过 GitHub Actions 实际同步**：

1. 在 Actions 页面选择 **Manual Sync** 工作流
2. 设置 `project_slug` 为新项目 slug
3. **不勾选** `dry_run`
4. 运行

工作流会自动执行：
- `npm run validate`（配置验证 + 输出验证）
- `npm run security:scan`（安全扫描）

**本地安全扫描**（需要先本地同步）：

```bash
npm run validate
npm run security:scan
```

安全扫描检查项：
- 禁止文件（`.env`、`debug-response.json` 等）
- 敏感信息模式（`app_secret`、`tenant_access_token`、`bearer` 等）
- Token 前缀（`cli_`、`t-`、`u-`、`ghp_` 等）
- 内部 Feishu 标识符（`table_id`、`app_token`）
- PII 疑似（手机号、身份证、邮箱、银行卡）—— 警告
- 高熵字符串 —— 警告

任何致命错误都会中止部署。详见 [安全策略](./SECURITY.md)。

### 步骤 8：运行语义校验（node scripts/validate-semantic.mjs）

同步完成后，运行语义配置校验脚本，确保语义映射、AI 文档和路由配置全部正确。

```bash
node scripts/validate-semantic.mjs
# 或
npm run validate:semantic
```

该脚本检查以下内容：

1. **语义配置文件**：每个项目的 `config/semantics/<slug>.yaml` 是否存在且有效
2. **semantic.json**：公开输出中 `semantic.json` 是否已生成
3. **agent-guide.md**：是否存在且内容充分（≥ 100 字符）
4. **summary.md**：是否存在且内容充分（≥ 500 字符）
5. **routing.json**：必填 intents 是否存在且路由逻辑正确
6. **catalog.json**：新增字段（`domains`、`capabilities`、`entity_types`、`supported_queries`、`semantic`、`agent_guide`、`freshness`、`access_mode`）是否齐全，顶层 `domains` 和 `capabilities` 索引是否与项目声明一致
7. **AI-README.md**：是否存在且内容充分（≥ 500 字符）

也可以运行 AI 文档校验脚本，对 summary.md、agent-guide.md、semantic.json、routing.json、AI-README.md 进行更详细的章节完整性和安全扫描：

```bash
node scripts/validate-ai-docs.mjs
# 或
npm run validate:ai-docs
```

或一次性运行全部验证：

```bash
npm run validate:all
```

### 步骤 9：运行路由测试（检查 routing.json 中的 intents）

确认 `routing.json` 中的意图路由配置正确，确保 AI 代理能正确将用户意图路由到候选项目。

**检查方式一：通过语义校验脚本自动检查**

`validate-semantic.mjs` 已包含 routing.json 的校验（见步骤 8），会自动检查以下必填 intents：

| Intent | 说明 | 候选项目 |
|---|---|---|
| `list_projects` | 列出所有项目 | 不需要记录数据 |
| `project_health` | 查看项目健康状态 | 不需要记录数据 |
| `study_planning` | 学习计划制定 | 跨项目（如 `civil-service-exam` + `learning-english`） |
| `english_review` | 英语复习 | 仅 `learning-english` |
| `civil_service_error_analysis` | 公考错误分析 | 仅 `civil-service-exam` |

**检查方式二：手动检查 routing.json**

访问以下 URL 查看 routing.json：

```
https://201650545.github.io/ai-platform/routing.json
```

确认：
- 所有必填 intents 都存在
- 每个 intent 的 `candidate_projects` 列表正确
- `list_projects` 和 `project_health` 的 `record_data_required` 为 `false`
- 新项目的 capabilities 已被至少一个 intent 引用（否则该项目不会被任何路由命中）

**检查方式三：本地检查**

```bash
# 同步后查看本地输出
cat public/routing.json | node -e "const r=JSON.parse(require('fs').readFileSync(0,'utf8')); console.log(JSON.stringify(r.intents, null, 2))"
```

### 步骤 10：发布并验证

同步成功后，验证部署结果。

1. 等待 GitHub Actions 运行完成（build + deploy 两个 job 均为绿色）
2. 访问以下 URL 确认新项目已出现：

```
https://201650545.github.io/ai-platform/catalog.json
```

确认 `projects` 数组中包含新项目条目，且 `sync_status: "ok"`、`is_stale: false`。

3. 访问项目级入口确认数据正确：

```
https://201650545.github.io/ai-platform/projects/<slug>/manifest.json
https://201650545.github.io/ai-platform/projects/<slug>/index.html
https://201650545.github.io/ai-platform/projects/<slug>/status.json
```

4. 检查各表的 `record_count` 和 `field_count` 是否符合预期
5. 检查 `status.json` 中的 `sync_status` 是否为 `ok`

#### 10.1 启用定时同步

确认手动同步无误后，项目将自动参与定时同步。

- 若 `schedule.tier: hourly`：每小时第 17 分钟由 `sync-hourly.yml` 自动同步
- 若 `schedule.tier: daily`：每天 03:17 UTC 由 `sync-daily.yml` 自动同步

无需额外配置，定时工作流会自动发现并同步所有 enabled 的项目。

---

## 3. 接入检查清单

完成接入后，逐项确认：

**基础接入**：
- [ ] 飞书 Base 中每张需要导出的表都有 `AI 公开导出` 视图
- [ ] 飞书应用已添加为 Base 协作者，权限为只读
- [ ] `FEISHU_BASE_REGISTRY_JSON` 中已添加新项目的 `app_token` 条目
- [ ] `config/projects/<slug>.yaml` 已创建，slug、title、base_key 配置正确
- [ ] `config/projects/<slug>.yaml` 中 `tables` 已显式配置字段白名单（非自动发现）
- [ ] `schedule.tier` 设置为合适的同步频率

**AI 语义层**：
- [ ] `content/projects/<slug>/summary.md` 已编写，包含全部 10 个必须章节（≥ 500 字符）
- [ ] `content/projects/<slug>/agent-guide.md` 已编写，包含全部 10 个必须章节（≥ 200 字符）
- [ ] `config/semantics/<slug>.yaml` 已创建，每张表都声明了 role 和 entity_type
- [ ] `config/semantics/<slug>.yaml` 中字段映射使用了受控词汇表中的 semantic_type
- [ ] `project.domains` 和 `project.capabilities` 已声明
- [ ] `project.entity_types` 和 `project.supported_queries` 已声明

**同步与验证**：
- [ ] Dry-run 同步通过，无报错
- [ ] 实际同步通过，安全扫描无致命错误
- [ ] `node scripts/validate-semantic.mjs` 通过（语义校验）
- [ ] `node scripts/validate-ai-docs.mjs` 通过（AI 文档校验）
- [ ] `routing.json` 中必填 intents 存在且路由逻辑正确

**部署验证**：
- [ ] `catalog.json` 中新项目 `sync_status: "ok"`，且包含 `domains`、`capabilities`、`semantic`、`agent_guide` 等新字段
- [ ] 项目级 `manifest.json`、`schema.json`、`status.json`、`semantic.json`、`agent-guide.md` 可正常访问
- [ ] 各表 `record_count` 和 `field_count` 符合预期
- [ ] `AI-README.md` 存在且内容充分

---

## 4. AI 代理协作权限边界

当使用 AI 代理（Agent）协助接入新项目时，必须遵守以下权限边界。

### 4.1 代理可以修改的文件

| 文件/目录 | 说明 |
|---|---|
| `config/projects/<own-slug>.yaml` | 仅限代理正在接入的自身项目的配置文件 |
| `content/projects/<own-slug>/summary.md` | 仅限自身项目的摘要文件 |
| `content/projects/<own-slug>/agent-guide.md` | 仅限自身项目的 AI 使用规则文件 |
| `config/semantics/<own-slug>.yaml` | 仅限自身项目的语义映射配置 |
| 项目相关的测试/固定数据 | 仅限自身项目的测试文件和测试数据 |
| 项目接入报告 | 代理自身项目的接入报告文档 |

### 4.2 代理不可修改的文件

| 文件/目录 | 说明 | 原因 |
|---|---|---|
| `scripts/sync-hub.mjs` | 同步核心编排脚本 | 影响所有项目 |
| `scripts/sync-project.mjs` | 单项目同步脚本 | 影响所有项目 |
| `scripts/security-scan.mjs` | 安全扫描脚本 | 安全核心 |
| `scripts/validate-config.mjs` | 配置验证脚本 | 影响所有项目 |
| `scripts/validate-output.mjs` | 输出验证脚本 | 影响所有项目 |
| `scripts/validate-semantic.mjs` | 语义校验脚本 | 影响所有项目 |
| `scripts/validate-ai-docs.mjs` | AI 文档校验脚本 | 影响所有项目 |
| `scripts/hydrate-existing-project.mjs` | 故障恢复脚本 | 影响所有项目 |
| `scripts/add-project.mjs` | 脚手架脚本 | 影响所有项目 |
| `lib/*.mjs` | 所有共享库模块（含 `semantic.mjs`） | 影响所有项目 |
| `public/` 相关的工作流 | `.github/workflows/sync-*.yml` | 部署核心 |
| `config/hub.yaml` | Hub 全局配置 | 影响所有项目 |
| `config/credential-profiles.yaml` | 凭据配置 | 安全核心 |
| `config/query-routing.yaml` | 路由配置 | 影响所有项目 |
| `config/projects/learning-english.yaml` | 英语学习项目配置 | 其他项目 |
| `config/projects/<other-slug>.yaml` | 其他项目的配置 | 其他项目 |
| `config/semantics/<other-slug>.yaml` | 其他项目的语义映射配置 | 其他项目 |
| `content/projects/<other-slug>/` | 其他项目的内容文件（summary/agent-guide） | 其他项目 |
| `templates/` | 模板文件 | 影响所有新项目 |

### 4.3 如果需要修改核心代码

如果代理在接入过程中发现需要修改同步核心脚本、安全扫描、构建 catalog、公开工作流、Hub 配置等共享基础设施，**必须**：

1. **停止修改**，不要直接修改共享文件
2. **撰写公开变更描述**（Public Change Description），包含：
   - 变更目标：需要解决什么问题
   - 变更范围：涉及哪些文件
   - 变更内容：具体的修改方案
   - 影响评估：对现有项目的影响
   - 安全评估：对安全策略的影响
3. **提交给主维护者审核**
4. 等待主维护者审核通过后再由主维护者执行修改

代理不应绕过此流程自行修改共享基础设施。

---

## 5. 常见问题

### Q: 自动发现模式和显式配置模式有什么区别？

- **自动发现模式**（`tables: []`）：同步时自动查找所有带 `AI 公开导出` 视图的表，导出这些表的全部字段。简单但安全性较低。
- **显式配置模式**（`tables: [...]`）：在 YAML 中逐表列出 table_name、table_slug、view_name 和 fields 白名单。安全但需要维护。

**建议**：始终使用显式配置模式，确保只导出经过审核的字段。

### Q: 新项目需要单独的飞书应用吗？

不需要。Data Hub 使用统一的飞书应用（通过 `credential-profiles.yaml` 中的 `public-personal` 配置），多个 Base 通过 `FEISHU_BASE_REGISTRY_JSON` 中的不同 `app_token` 区分。只需确保该应用被添加为每个 Base 的只读协作者。

### Q: 如何处理字段名变更？

如果飞书 Base 中的字段名发生变更：
1. 更新 `config/projects/<slug>.yaml` 中对应表的 `fields` 白名单
2. 提交并推送
3. 下次定时同步会自动应用新配置
4. 旧的 `fields.json` 和 `records-*.json` 会被新输出替换

### Q: 新项目可以使用遗留兼容路径吗？

默认不启用。只有 `learning-english` 项目配置了 `compatibility.mirror_to_legacy_root: true`，因为它是迁移前的唯一项目，需要保持旧 URL 可用。新项目不需要此配置。

### Q: 新项目必须配置语义层（semantic.yaml、summary.md、agent-guide.md）吗？

是的。语义层是 AI 代理理解项目数据的基础。从 AI 语义层升级后，每个项目必须提供：
- `config/semantics/<slug>.yaml` — 语义映射配置
- `content/projects/<slug>/summary.md` — 项目摘要（≥ 500 字符，10 个必须章节）
- `content/projects/<slug>/agent-guide.md` — AI 使用规则（≥ 200 字符，10 个必须章节）

`validate-semantic.mjs` 和 `validate-ai-docs.mjs` 会检查这些文件是否存在且内容充分，缺失会导致校验失败。

### Q: 如何知道有哪些受控语义类型可以使用？

受控词汇表定义在 `lib/semantic.mjs` 中，包括：
- `TABLE_ROLES` — 表角色（content、knowledge、event_log、plan、metric、error_log 等）
- `ENTITY_TYPES` — 实体类型（task、learning_event、knowledge、metric、content 等）
- `SEMANTIC_TYPES` — 字段语义类型（entity_identity_title、event_date、review_due_at、mastery_level 等）

参考 `config/semantics/learning-english.yaml` 或 `config/semantics/civil-service-exam.yaml` 了解实际用法。`validate-semantic.mjs` 会校验所有值是否在受控词汇表内。

---

## 相关文档

- [架构概览](./ARCHITECTURE.md) — 系统整体架构
- [运维手册](./OPERATIONS.md) — 日常运维操作
- [安全策略](./SECURITY.md) — 公开数据安全策略
- [语义层基线](./SEMANTIC_LAYER_BASELINE.md) — AI 语义层升级前的系统基线状态
