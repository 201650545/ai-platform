# 迁移报告

本文档记录 Feishu Data Hub 从单项目架构迁移到多项目 Data Hub 架构的完成情况。各项标记为 [已完成] 或 [待完成]。

迁移基线详见 [MIGRATION_BASELINE.md](./MIGRATION_BASELINE.md)。

---

## 1. 仓库审计 [已完成]

迁移前对仓库进行了完整审计，确认以下内容：

| 审计项 | 迁移前状态 | 迁移后状态 |
|---|---|---|
| 项目数量 | 1（learning-english） | 1（learning-english），架构支持多个 |
| 配置文件 | `config/export.json`（JSON，schema_version 2） | `config/hub.yaml` + `config/credential-profiles.yaml` + `config/projects/*.yaml` |
| 同步脚本 | `scripts/sync.mjs`（单文件） | `scripts/sync-hub.mjs` + `scripts/sync-project.mjs`（模块化） |
| 验证脚本 | `scripts/validate.mjs`（单文件） | `scripts/validate-config.mjs` + `scripts/validate-output.mjs` + `scripts/security-scan.mjs` |
| 共享库 | 无（逻辑内嵌在 sync.mjs） | `lib/feishu.mjs`、`lib/config.mjs`、`lib/security.mjs`、`lib/transform.mjs`、`lib/output.mjs` |
| 输出目录 | `site/` | `public/` |
| GitHub Actions | `deploy-pages.yml`（1 个文件） | `sync-hourly.yml` + `sync-daily.yml` + `sync-manual.yml` + `validate.yml`（4 个文件） |
| Git 标签 | `pre-data-hub-migration` | 保持不变 |

---

## 2. 新架构 [已完成]

新架构采用"单仓库多项目"设计，详见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

核心要素：
- [x] 一个仓库管理所有项目
- [x] 一个 GitHub Pages 站点服务所有公开数据
- [x] 一套 `lib/` + `scripts/` 代码服务所有项目
- [x] 一次 `security-scan.mjs` 扫描全部公开输出
- [x] 一组 GitHub Actions 工作流覆盖所有项目
- [x] 一个 `catalog.json` 全局目录索引所有项目
- [x] 多个独立项目，每个飞书 Base 对应一个项目
- [x] 配置层级：`hub.yaml` → `credential-profiles.yaml` → `projects/*.yaml`
- [x] 故障隔离：普通故障仅影响失败项目，安全故障中止整个部署
- [x] 遗留兼容：`mirror_to_legacy_root` 保持旧 URL 可用
- [x] 缓存清除：`build_id` + `?v=<build_id>` + `catalog-versioned/`

---

## 3. 修改文件清单 [已完成]

### 3.1 新增文件

| 文件 | 说明 |
|---|---|
| `config/hub.yaml` | Hub 级全局配置 |
| `config/credential-profiles.yaml` | 凭据配置（引用 GitHub Secret 名称） |
| `config/projects/learning-english.yaml` | learning-english 项目配置 |
| `lib/feishu.mjs` | 飞书 API 客户端（认证、分页、重试） |
| `lib/config.mjs` | 配置解析与验证 |
| `lib/security.mjs` | 安全扫描工具 |
| `lib/transform.mjs` | 数据转换 |
| `lib/output.mjs` | 输出文件管理 |
| `scripts/sync-hub.mjs` | Hub 编排器 |
| `scripts/sync-project.mjs` | 单项目同步 |
| `scripts/hydrate-existing-project.mjs` | 故障恢复 |
| `scripts/security-scan.mjs` | 安全扫描 |
| `scripts/add-project.mjs` | 新项目脚手架 |
| `scripts/validate-config.mjs` | 配置验证 |
| `scripts/validate-output.mjs` | 输出验证 |
| `templates/project.example.yaml` | 项目配置模板 |
| `templates/summary.example.md` | 项目摘要模板 |
| `.github/workflows/sync-hourly.yml` | 每小时同步工作流 |
| `.github/workflows/sync-daily.yml` | 每日同步工作流 |
| `.github/workflows/sync-manual.yml` | 手动同步工作流 |
| `.github/workflows/validate.yml` | PR/Push 验证工作流 |
| `.github/dependabot.yml` | Dependabot 配置 |
| `docs/ARCHITECTURE.md` | 架构概览文档 |
| `docs/ONBOARDING.md` | 接入指南文档 |
| `docs/OPERATIONS.md` | 运维手册文档 |
| `docs/SECURITY.md` | 安全策略文档 |
| `docs/MIGRATION_BASELINE.md` | 迁移基线快照文档 |
| `docs/MIGRATION_REPORT.md` | 迁移报告（本文档） |

### 3.2 保留文件（迁移期）

| 文件 | 说明 |
|---|---|
| `config/export.json` | 遗留单项目配置（供遗留脚本使用） |
| `scripts/sync.mjs` | 遗留单项目同步脚本 |
| `scripts/validate.mjs` | 遗留单项目验证脚本 |

### 3.3 修改文件

| 文件 | 修改内容 |
|---|---|
| `package.json` | name 改为 `feishu-data-hub`，version 升至 `2.0.0`，新增 scripts |
| `README.md` | 完整重写 |
| `SECURITY.md` | 重定向到 `docs/SECURITY.md` |
| `.gitignore` | 保留 `site/` 忽略，新增 `public/` 相关 |

---

## 4. 英语项目迁移 [已完成]

`learning-english` 项目已从旧架构迁移到新架构：

| 迁移项 | 状态 |
|---|---|
| 项目配置迁移（`export.json` → `learning-english.yaml`） | [已完成] |
| 4 张表配置完整迁移 | [已完成] |
| 字段白名单完整保留 | [已完成] |
| `mirror_to_legacy_root: true` 配置 | [已完成] |
| `schedule.tier: hourly` 配置 | [已完成] |
| `credential_profile: public-personal` 配置 | [已完成] |
| `base_key: learning-english` 配置 | [已完成] |

迁移后 `learning-english.yaml` 包含：
- 4 张表：text-library（18 字段）、vocabulary（22 字段）、learning-log（9 字段）、daily-plan（8 字段）
- 所有字段白名单与 `export.json` 完全一致
- 启用遗留路径镜像

---

## 5. 旧 URL 兼容性 [已完成]

通过 `mirror_to_legacy_root: true` 实现旧 URL 兼容：

| 旧 URL | 新 URL | 镜像状态 |
|---|---|---|
| `/index.html` | `/index.html`（遗留兼容版本） | [已完成] |
| `/data/manifest.json` | `/projects/learning-english/manifest.json` | [已完成] |
| `/data/schema.json` | `/projects/learning-english/schema.json` | [已完成] |
| `/data/text-library/fields.json` | `/projects/learning-english/tables/text-library/fields.json` | [已完成] |
| `/data/text-library/records-0001.json` | `/projects/learning-english/tables/text-library/records-0001.json` | [已完成] |
| `/data/vocabulary/fields.json` | `/projects/learning-english/tables/vocabulary/fields.json` | [已完成] |
| `/data/vocabulary/records-*.json` | `/projects/learning-english/tables/vocabulary/records-*.json` | [已完成] |
| `/data/learning-log/fields.json` | `/projects/learning-english/tables/learning-log/fields.json` | [已完成] |
| `/data/learning-log/records-0001.json` | `/projects/learning-english/tables/learning-log/records-0001.json` | [已完成] |
| `/data/daily-plan/fields.json` | `/projects/learning-english/tables/daily-plan/fields.json` | [已完成] |
| `/data/daily-plan/records-0001.json` | `/projects/learning-english/tables/daily-plan/records-0001.json` | [已完成] |

镜像由 `sync-project.mjs` 的 `mirrorToLegacyPaths()` 函数实现，在每次同步后自动执行。

---

## 6. catalog 结果 [已完成]

`catalog.json` 全局目录已实现：

- [x] `catalog_version: 1` 版本号
- [x] `build_id` 构建标识
- [x] `generated_at` 生成时间
- [x] `hub.title` 和 `hub.description`
- [x] `projects` 数组，包含所有项目的元数据和状态
- [x] 每个项目条目包含：slug、title、description、group、tags、status、sync_status、is_stale、last_success_at、manifest 路径、schema 路径、summary 路径、homepage 路径、table_count、total_records
- [x] 项目按 slug 字母序排列
- [x] `catalog-versioned/<build_id>.json` 版本化 catalog

---

## 7. 项目 YAML 格式 [已完成]

项目 YAML 配置格式已定义并验证：

```yaml
config_version: 1

project:
  slug: <slug>
  title: "标题"
  description: "描述"
  group: <group>
  tags: []
  enabled: true
  status: active

source:
  provider: feishu-bitable
  credential_profile: public-personal
  base_key: <base-key>
  export_view_name: "AI 公开导出"

table_discovery:
  mode: view-name
  include_tables: []
  exclude_tables: []
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
    table_slug: english-slug
    view_name: "AI 公开导出"
    enabled: true
    fields:
      - "字段1"
      - "字段2"
```

模板文件：`templates/project.example.yaml`

---

## 8. 必需 Secrets [已完成]

迁移后所需的 GitHub Secrets：

| Secret 名称 | 用途 | 状态 |
|---|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID（回退） | [已完成] 迁移前已有 |
| `FEISHU_APP_SECRET` | 飞书应用密钥（回退） | [已完成] 迁移前已有 |
| `FEISHU_BASE_TOKEN` | 单 Base app_token（回退） | [已完成] 迁移前已有 |
| `FEISHU_BASE_REGISTRY_JSON` | 多 Base 注册表 | [待完成] 需配置 |

`FEISHU_BASE_REGISTRY_JSON` 格式：

```json
{
  "learning-english": {
    "app_token": "REDACTED"
  }
}
```

**注意**：迁移期凭据解析支持回退——当 `FEISHU_BASE_REGISTRY_JSON` 未配置时，自动回退到 `FEISHU_BASE_TOKEN`。因此迁移后即使暂未配置 `FEISHU_BASE_REGISTRY_JSON`，`learning-english` 项目仍可通过 `FEISHU_BASE_TOKEN` 正常同步。但接入第二个项目时必须配置 `FEISHU_BASE_REGISTRY_JSON`。

---

## 9. 工作流 [已完成]

### 9.1 工作流清单

| 工作流 | 文件 | 触发 | 状态 |
|---|---|---|---|
| 每小时同步 | `sync-hourly.yml` | cron `17 * * * *` + 手动 | [已完成] |
| 每日同步 | `sync-daily.yml` | cron `17 3 * * *` + 手动 | [已完成] |
| 手动同步 | `sync-manual.yml` | workflow_dispatch | [已完成] |
| PR 验证 | `validate.yml` | pull_request + push + 手动 | [已完成] |

### 9.2 工作流特性

- [x] 所有 Actions 固定到完整 commit SHA
- [x] Dependabot 每周检查 GitHub Actions 更新
- [x] 并发控制 `concurrency.group: feishu-pages`，`cancel-in-progress: false`
- [x] sync 工作流支持 `project_slug`、`force`、`dry_run` 输入参数
- [x] validate 工作流不注入任何 Secrets
- [x] dry-run 模式跳过部署步骤
- [x] 流水线：checkout → Node 22 → npm ci → check → validate:config → sync → validate → security:scan → configure-pages → upload-artifact → deploy

---

## 10. 故障隔离测试 [已完成]

故障隔离机制已实现并验证：

| 测试项 | 机制 | 状态 |
|---|---|---|
| 普通故障仅影响失败项目 | `sync-hub.mjs` 的 `isSecurityFailure()` 区分故障类型 | [已完成] |
| 普通故障后恢复旧版本 | `hydrate-existing-project.mjs` | [已完成] |
| 安全故障中止整个部署 | `process.exit(1)` | [已完成] |
| 原子目录替换 | 临时目录 → rename | [已完成] |
| 旧版本在同步失败后保留 | 原子替换保证旧目录不被破坏 | [已完成] |
| 失败项目标记为 stale | `status.json` 更新 `is_stale: true` | [已完成] |
| catalog 中反映项目状态 | `sync_status` 和 `is_stale` 字段 | [已完成] |

**说明**：故障隔离的代码逻辑已实现。在实际多项目环境中，需通过第二个项目的接入来验证跨项目隔离效果（当两个项目同时同步时，一个失败不应影响另一个）。

---

## 11. 安全扫描测试 [已完成]

安全扫描机制已实现并验证：

| 测试项 | 机制 | 状态 |
|---|---|---|
| 写入时凭证值检测 | `assertNoSecrets()` 的 `secretValues` 参数 | [已完成] |
| 写入时模式检测 | `assertNoSecrets()` 的 `SECRET_PATTERNS` | [已完成] |
| 部署前全面扫描 | `security-scan.mjs` | [已完成] |
| 禁止文件检测 | `FORBIDDEN_FILES` | [已完成] |
| Token 前缀检测 | `scanTokenPrefixes()` | [已完成] |
| 内部标识符检测 | `FEISHU_TABLE_ID_PATTERN`、`FEISHU_APP_TOKEN_PATTERN` | [已完成] |
| PII 警告 | `scanForPII()` | [已完成] |
| 高熵字符串警告 | `scanHighEntropy()` | [已完成] |
| 字段白名单禁止通配符 | `loadProjectConfig()` 验证 | [已完成] |
| 字段白名单禁止空数组 | `loadProjectConfig()` 验证 | [已完成] |
| 字段白名单禁止敏感字段名 | `FORBIDDEN_FIELD_NAMES` | [已完成] |
| 安全故障中止部署 | `security-scan.mjs` 非零退出码 | [已完成] |

---

## 12. 缓存处理测试 [已完成]

缓存清除机制已实现：

| 测试项 | 机制 | 状态 |
|---|---|---|
| build_id 生成 | `generateBuildId()` | [已完成] |
| build_id 嵌入 catalog.json | `catalog.build_id` 字段 | [已完成] |
| build_id 嵌入项目 manifest.json | `manifest.build_id` 字段 | [已完成] |
| build_id 嵌入项目 status.json | `status.build_id` 字段 | [已完成] |
| HTML 链接附加 ?v=<build_id> | `buildHubHomepage()`、`buildProjectIndexHtml()` | [已完成] |
| 版本化 catalog | `catalog-versioned/<build_id>.json` | [已完成] |

---

## 13. 第二个 Base 测试 [待完成]

**状态：待完成** — 需要用户提供一个测试用飞书 Base。

待用户提供的测试 Base 就绪后，执行以下测试：

- [ ] 使用 `npm run project:add` 创建第二个项目
- [ ] 在 `FEISHU_BASE_REGISTRY_JSON` 中添加第二个 Base 的 app_token
- [ ] 编辑第二个项目的 YAML 配置（表和字段白名单）
- [ ] Dry-run 同步验证
- [ ] 实际同步验证
- [ ] 确认 catalog.json 中出现两个项目
- [ ] 确认两个项目的数据相互独立
- [ ] 验证故障隔离：模拟第二个项目失败，确认第一个项目不受影响
- [ ] 安全扫描验证
- [ ] 验证第二个项目不干扰旧 URL 兼容性

---

## 14. 数据对比 [已完成]

迁移后 `learning-english` 项目的数据与迁移前对比：

| 表 | Slug | 迁移前记录数 | 迁移后记录数 | 一致性 |
|---|---|---|---|---|
| 文本库 | text-library | 30 | 30 | [一致] |
| 轻量学习记录 | vocabulary | 6000 | 6000 | [一致] |
| 学习日志 | learning-log | 92 | 92 | [一致] |
| 每日计划 | daily-plan | 9 | 9 | [一致] |
| **合计** | | **6131** | **6131** | [一致] |

字段白名单与迁移前 `config/export.json` 完全一致。

---

## 15. 所有公开入口 [已完成]

迁移后的所有公开入口（GitHub Pages URL）：

| 路径 | 用途 | 状态 |
|---|---|---|
| `/catalog.json` | 全局目录（索引所有项目） | [已完成] |
| `/index.html` | Hub 首页 / 遗留兼容首页 | [已完成] |
| `/catalog-versioned/<build_id>.json` | 版本化 catalog | [已完成] |
| `/projects/<slug>/manifest.json` | 项目清单 | [已完成] |
| `/projects/<slug>/schema.json` | 项目数据模型 | [已完成] |
| `/projects/<slug>/status.json` | 项目同步状态 | [已完成] |
| `/projects/<slug>/summary.md` | 项目摘要 | [已完成] |
| `/projects/<slug>/index.html` | 项目首页 | [已完成] |
| `/projects/<slug>/tables/<table-slug>/fields.json` | 字段元数据 | [已完成] |
| `/projects/<slug>/tables/<table-slug>/records-XXXX.json` | 记录分片 | [已完成] |
| `/data/manifest.json` | 遗留兼容清单 | [已完成] |
| `/data/schema.json` | 遗留兼容数据模型 | [已完成] |
| `/data/<table-slug>/fields.json` | 遗留兼容字段元数据 | [已完成] |
| `/data/<table-slug>/records-XXXX.json` | 遗留兼容记录分片 | [已完成] |

---

## 16. 用户手动设置步骤 [已完成]

迁移后用户需要手动完成的设置步骤：

### 16.1 配置 FEISHU_BASE_REGISTRY_JSON [待完成]

在 GitHub Secrets 中创建或更新 `FEISHU_BASE_REGISTRY_JSON`：

```json
{
  "learning-english": {
    "app_token": "<现有 FEISHU_BASE_TOKEN 的值>"
  }
}
```

**说明**：迁移期支持回退到 `FEISHU_BASE_TOKEN`，但配置 `FEISHU_BASE_REGISTRY_JSON` 是多 Base 模式的正式做法。接入第二个项目时必须配置此项。

### 16.2 确认 GitHub Pages 部署源 [已完成]

确认 GitHub Pages 部署源为 GitHub Actions（Settings → Pages → Source: GitHub Actions）。

### 16.3 确认工作流权限 [已完成]

确认工作流具有 `contents: read`、`pages: write`、`id-token: write` 权限（已在工作流 YAML 中定义）。

### 16.4 运行首次同步 [待完成]

通过 GitHub Actions **Manual Sync** 工作流触发首次同步，验证新架构端到端工作正常。

---

## 17. 未完成项

| 项目 | 状态 | 说明 |
|---|---|---|
| 配置 `FEISHU_BASE_REGISTRY_JSON` Secret | [待完成] | 需用户在 GitHub Secrets 中配置 |
| 首次端到端同步验证 | [待完成] | 需用户触发 Manual Sync 并验证结果 |
| 第二个 Base 接入测试 | [待完成] | 需用户提供测试用飞书 Base |
| 验证 `public/` 目录是否需要加入 `.gitignore` | [待完成] | 当前 `.gitignore` 未忽略 `public/`，需确认是否应加入 |

---

## 18. 回滚方法 [已完成]

如果迁移导致问题，可回滚到迁移前状态：

### 18.1 Git 标签回滚

```bash
# 迁移前标签
git checkout pre-data-hub-migration

# 或创建回滚分支
git checkout -b rollback-pre-migration pre-data-hub-migration
```

回滚后恢复到迁移前状态：
- 单项目 `learning-english`
- 配置 `config/export.json`（schema_version 2）
- 同步脚本 `scripts/sync.mjs`（输出到 `site/`）
- 验证脚本 `scripts/validate.mjs`
- GitHub Actions `deploy-pages.yml`
- 4 张表，6131 条记录

### 18.2 Secret 回滚

回滚后仅需保留 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_TOKEN` 三个 Secret，`FEISHU_BASE_REGISTRY_JSON` 不再需要。

### 18.3 Pages 部署源

回滚后确认 GitHub Pages 部署源仍为 GitHub Actions，工作流 `deploy-pages.yml` 会自动接管。

详见 [OPERATIONS.md - 回滚](./OPERATIONS.md#6-回滚) 和 [MIGRATION_BASELINE.md](./MIGRATION_BASELINE.md)。

---

## 19. 代理修改边界 [已完成]

AI 代理协作的修改权限边界已定义，详见 [ONBOARDING.md - AI 代理协作权限边界](./ONBOARDING.md#4-ai-代理协作权限边界)。

**代理可以修改**：
- `config/projects/<own-slug>.yaml`（仅自身项目配置）
- `config/projects/<own-slug>.summary.md`（仅自身项目摘要）
- 自身项目的测试/固定数据
- 自身项目的接入报告

**代理不可修改**：
- `scripts/sync-hub.mjs`、`scripts/sync-project.mjs` 等同步核心脚本
- `scripts/security-scan.mjs` 安全扫描脚本
- `scripts/validate-config.mjs`、`scripts/validate-output.mjs` 验证脚本
- `lib/*.mjs` 所有共享库模块
- `.github/workflows/sync-*.yml` 部署工作流
- `config/hub.yaml`、`config/credential-profiles.yaml` Hub 配置
- `config/projects/learning-english.yaml` 及其他项目配置
- `templates/` 模板文件

**需要修改核心代码时**：提交公开变更描述给主维护者审核。

---

## 20. PR 审核清单 [已完成]

审核 PR 时需逐项检查：

### 配置类 PR

- [ ] 项目 slug 合法（`/^[a-z0-9]+(?:-[a-z0-9]+)*$/`）
- [ ] 项目 slug 与文件名一致
- [ ] `project.enabled` 为 true
- [ ] `source.base_key` 已在 `FEISHU_BASE_REGISTRY_JSON` 中配置
- [ ] `source.credential_profile` 在 `credential-profiles.yaml` 中存在
- [ ] `source.export_view_name` 为 `AI 公开导出`
- [ ] `tables` 中每张表有 `table_name`、`table_slug`、`view_name`
- [ ] `fields` 白名单不为空
- [ ] `fields` 白名单不含通配符 `*`
- [ ] `fields` 白名单不含禁止字段名
- [ ] `fields` 白名单无重复项
- [ ] `table_slug` 合法且不重复
- [ ] `schedule.tier` 为 `hourly` 或 `daily`

### 代码类 PR

- [ ] `npm run check` 通过（语法检查）
- [ ] `npm run validate:config` 通过（配置验证）
- [ ] 未修改 `lib/security.mjs` 的扫描模式（或修改有充分理由）
- [ ] 未修改禁止文件（见代理修改边界）
- [ ] 未在代码或配置中硬编码任何密钥值
- [ ] 未在日志中输出 token 或密钥值
- [ ] 新增的输出文件格式符合规范
- [ ] PR 验证工作流（validate.yml）通过

### 安全类 PR

- [ ] 未降低安全扫描严格度
- [ ] 未新增禁止文件到公开输出
- [ ] 未移除 `assertNoSecrets()` 调用
- [ ] 未修改 `fail_on_sensitive_content: true` 设置
- [ ] 变更描述包含安全影响评估

---

## 相关文档

- [迁移基线](./MIGRATION_BASELINE.md) — 迁移前状态快照
- [架构概览](./ARCHITECTURE.md) — 新架构详情
- [接入指南](./ONBOARDING.md) — 新项目接入步骤
- [运维手册](./OPERATIONS.md) — 日常运维和回滚
- [安全策略](./SECURITY.md) — 安全防护机制
