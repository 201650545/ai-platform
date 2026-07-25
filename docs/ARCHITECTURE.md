# 架构概览

本文档描述 Feishu Data Hub 的整体架构、目录结构、数据流、配置体系、共享库模块、故障隔离、遗留兼容和缓存策略。

---

## 1. 总体设计

Feishu Data Hub 采用 **"单仓库多项目"** 架构，核心理念是：

| 维度 | 数量 | 说明 |
|---|---|---|
| 仓库 | 1 | 一个 Git 仓库管理所有项目 |
| Pages 站点 | 1 | 一个 GitHub Pages 站点服务所有公开数据 |
| 同步代码库 | 1 | 一套 `lib/` + `scripts/` 代码服务所有项目 |
| 安全扫描 | 1 | 一次 `security-scan.mjs` 扫描全部公开输出 |
| Actions 集合 | 1 套 | 一组 GitHub Actions 工作流覆盖所有项目 |
| catalog.json | 1 | 一个全局目录文件索引所有项目 |
| 独立项目 | 多个 | 每个飞书 Base 对应一个独立项目，互不干扰 |

**设计目标**：在同一个仓库和同一套代码基础设施中，支持多个相互独立的飞书 Base 公开导出。新项目接入只需新增一个项目 YAML 配置文件和一条 Base 注册表条目，无需修改同步核心代码。

---

## 2. 目录结构

```
feishu-learning-english-export/
├── config/
│   ├── hub.yaml                      # Hub 级全局配置
│   ├── credential-profiles.yaml      # 凭据配置（引用 GitHub Secret 名称）
│ ├── export.json # 遗留单项目配置（迁移期保留）
│   └── projects/
│       └── learning-english.yaml     # 各项目独立配置
├── scripts/
│   ├── sync-hub.mjs                  # Hub 编排器（发现项目、逐个同步、构建 catalog）
│   ├── sync-project.mjs              # 单项目同步（飞书 API → 公开输出）
│   ├── hydrate-existing-project.mjs  # 故障恢复（恢复上次成功版本）
│   ├── security-scan.mjs             # 安全扫描（扫描全部输出文件）
│   ├── add-project.mjs               # 新项目脚手架（CLI）
│   ├── validate-config.mjs           # 配置文件验证
│   ├── validate-output.mjs           # 公开输出验证（校验和、记录数、关联）
│   ├── sync.mjs                      # 遗留单项目同步脚本（迁移期保留）
│   └── validate.mjs                  # 遗留单项目验证脚本（迁移期保留）
├── lib/
│   ├── feishu.mjs                    # 飞书 API 客户端（认证、分页、重试）
│   ├── config.mjs                    # 配置解析与验证
│   ├── security.mjs                  # 安全扫描工具（模式匹配、PII、高熵检测）
│   ├── transform.mjs                 # 数据转换（字段类型映射、记录选择）
│   └── output.mjs                    # 输出文件管理（JSON 写入、HTML 生成）
├── docs/
│   ├── ARCHITECTURE.md               # 本文档
│   ├── ONBOARDING.md                 # 新项目接入指南
│   ├── OPERATIONS.md                 # 运维手册
│   ├── SECURITY.md                   # 安全策略
│   ├── MIGRATION_BASELINE.md         # 迁移前基线快照
│   └── MIGRATION_REPORT.md           # 迁移报告
├── templates/
│   ├── project.example.yaml          # 项目配置模板
│   └── summary.example.md            # 项目摘要模板
├── public/                           # 公开输出目录（GitHub Pages 部署根）
│   ├── index.html                    # Hub 首页 / 遗留兼容首页
│   ├── catalog.json                  # 全局目录（索引所有项目）
│   ├── catalog-versioned/            # 带版本号的 catalog（缓存清除）
│   │   └── <build_id>.json
│   ├── projects/
│   │   └── <slug>/
│   │       ├── manifest.json         # 项目清单（表列表 + 校验和）
│   │       ├── schema.json           # 项目数据模型（字段类型 + 关联）
│   │       ├── summary.md            # 人类可读摘要
│   │       ├── status.json           # 同步状态（sync_status、is_stale）
│   │       ├── index.html            # 项目首页
│   │       └── tables/
│   │           └── <table-slug>/
│   │               ├── fields.json   # 字段元数据
│   │               └── records-XXXX.json  # 记录分片
│   └── data/                         # 遗留兼容路径（mirror_to_legacy_root）
│       ├── manifest.json
│       ├── schema.json
│       └── <table-slug>/
│           ├── fields.json
│           └── records-XXXX.json
├── .github/
│   ├── workflows/
│   │   ├── sync-hourly.yml           # 每小时同步（tier=hourly 项目）
│   │   ├── sync-daily.yml            # 每日同步（tier=daily 项目）
│   │   ├── sync-manual.yml           # 手动同步（全部或单个项目）
│   │   └── validate.yml              # PR/Push 验证（无密钥、无部署）
│   └── dependabot.yml                # GitHub Actions 版本自动更新
├── package.json
├── package-lock.json
├── README.md
├── SECURITY.md
└── .gitignore
```

---

## 3. 数据流

```
飞书 Base (多维表格)
    │
    │  ① sync-project.mjs 读取
    │     - getTenantAccessToken(appId, appSecret)
    │     - listTables / listViews / listFields / listRecords
    │     - 仅读取 "AI 公开导出" 视图
    │     - 仅读取字段白名单中的字段
    │
    ▼
临时目录 public/projects/<slug>.tmp/
    │
    │  ② 原子替换（atomic swap）
    │     - 写入 manifest.json, schema.json, summary.md,
    │       status.json, index.html, tables/<slug>/*.json
    │     - 全部写入成功后，删除旧目录，重命名临时目录
    │     - 若中途失败，旧目录保持不变
    │
    ▼
最终目录 public/projects/<slug>/
    │
    │  ③ sync-hub.mjs 汇编
    │     - 读取所有项目的 manifest 和 status
    │     - 构建 catalog.json（全局目录）
    │     - 构建 catalog-versioned/<build_id>.json
    │     - 构建 Hub 首页 index.html
    │
    ▼
catalog.json + index.html
    │
    │  ④ 遗留兼容镜像（仅 mirror_to_legacy_root=true 的项目）
    │     - 复制 manifest.json → public/data/manifest.json
    │     - 复制 schema.json → public/data/schema.json
    │     - 复制 tables/<slug>/* → public/data/<table-slug>/*
    │     - 生成遗留兼容 index.html
    │
    ▼
GitHub Pages
    │
    │  ⑤ GitHub Actions 部署
    │     - upload-pages-artifact (path: public)
    │     - deploy-pages
    │
    ▼
https://201650545.github.io/feishu-learning-english-export/
```

### 3.1 同步编排流程（sync-hub.mjs）

```
1. 加载 hub.yaml 和 credential-profiles.yaml
2. 生成 build_id（<时间戳>-<短SHA>）
3. 发现项目：
   - 若指定 --project <slug>，仅同步该项目
   - 若指定 --tier hourly/daily，仅同步该层级项目
   - 否则同步所有 enabled=true 的项目
4. 逐个项目调用 syncProject()，故障隔离：
   - 普通故障 → 标记该项目失败，尝试 hydrate-existing-project 恢复旧版
   - 安全故障 → 立即中止整个部署（process.exit(1)）
5. 清理已移除项目的输出目录（仅全量同步时）
6. 构建 catalog.json 和 catalog-versioned/<build_id>.json
7. 构建 Hub 首页 index.html
8. 输出同步摘要
```

---

## 4. 配置体系

配置采用三层分级结构，从全局到局部逐层细化：

```
config/hub.yaml                      ← 全局 Hub 配置（输出路径、安全策略、默认值）
    │
    ├── config/credential-profiles.yaml  ← 凭据配置（引用 GitHub Secret 名称）
    │
    └── config/projects/<slug>.yaml      ← 各项目独立配置
```

### 4.1 hub.yaml（全局配置）

定义 Hub 级别的设置，所有项目共享：

- **hub**：标题和描述
- **output**：输出目录结构（`root_dir: public`、`projects_dir: projects`、`catalog_file: catalog.json`、`catalog_versioned_dir: catalog-versioned`、`homepage_file: index.html`）
- **build**：`include_build_id: true`（缓存清除）
- **security**：安全策略（`fail_on_sensitive_content: true`、`scan_free_text`、`scan_urls`、`forbidden_files`）
- **defaults**：默认导出参数（`chunk_size: 500`、`max_table_bytes: 25MB`、`export_view_name: "AI 公开导出"`）

### 4.2 credential-profiles.yaml（凭据配置）

定义如何向飞书认证。真实密钥绝不存储在配置文件中，仅引用 GitHub Secret 名称：

- **profiles.public-personal**：
  - 主密钥：`FEISHU_PUBLIC_APP_ID` / `FEISHU_PUBLIC_APP_SECRET`
  - 回退密钥：`FEISHU_APP_ID` / `FEISHU_APP_SECRET`（遗留兼容）
  - Base 注册表：`FEISHU_BASE_REGISTRY_JSON`（多 Base 模式）
  - 回退 Base Token：`FEISHU_BASE_TOKEN`（单 Base 遗留模式）
  - 权限：`bitable:app:readonly`、`bitable:app`

### 4.3 projects/*.yaml（项目配置）

每个项目一个 YAML 文件，定义该项目的导出规则：

- **project**：slug、title、description、group、tags、enabled、status
- **source**：provider、credential_profile、base_key、export_view_name
- **table_discovery**：表发现模式（view-name 自动发现 或 显式列表）
- **export**：chunk_size、include_schema、include_summary、include_record_id、stable_sort
- **privacy**：公开标志、审核状态、扫描选项
- **schedule**：同步层级（hourly / daily）
- **compatibility**：`mirror_to_legacy_root`（遗留路径镜像）
- **tables**：显式表配置（table_name、table_slug、view_name、enabled、fields 白名单）

---

## 5. 共享库模块

所有项目共享同一套 `lib/` 模块，确保行为一致性和安全性。

### 5.1 lib/feishu.mjs — 飞书 API 客户端

- **apiRequest()**：低层 API 请求，带重试（指数退避 + retry-after 头）、30 秒超时、永不记录 token 或密钥
- **getTenantAccessToken()**：获取 tenant_access_token（仅返回，绝不记录或写入输出）
- **paginate()**：分页获取，安全上限 10000 页，检测 token 循环
- **listTables / listViews / listFields / listRecords**：Bitable 读取操作
- **exactOne()**：精确匹配工具（不存在或重名均抛错）

### 5.2 lib/config.mjs — 配置解析与验证

- **loadHubConfig()**：加载 hub.yaml
- **loadCredentialProfiles()**：加载 credential-profiles.yaml
- **resolveCredentials()**：从环境变量解析凭据（主密钥 → 回退密钥；注册表 → 单 Token）
- **loadProjectConfig()**：加载并验证单个项目配置（slug 合法性、字段白名单、禁止字段名）
- **discoverProjects()**：发现 config/projects/ 下所有项目
- **loadAllProjects()**：加载所有 enabled 项目
- **loadLegacyExportConfig()**：加载遗留 export.json（迁移兼容）
- **assertSafeSlug()**：slug 合法性校验（`/^[a-z0-9]+(?:-[a-z0-9]+)*$/`）
- **FORBIDDEN_FIELD_NAMES**：禁止公开的字段名集合

### 5.3 lib/security.mjs — 安全扫描工具

- **assertNoSecrets()**：检查实际凭证值和敏感信息模式，命中即抛错（硬中止）
- **SECRET_PATTERNS**：凭证/Token 模式正则数组
- **PII_PATTERNS**：个人身份信息模式（手机号、身份证、邮箱、银行卡）
- **FORBIDDEN_FILES**：禁止出现在公开输出的文件列表
- **scanForPII()**：PII 扫描（返回匹配列表）
- **scanHighEntropy()**：高熵字符串检测（Shannon 熵 > 4.0）
- **scanTokenPrefixes()**：Token 前缀检测（cli_、t-、u-、Bearer、ghp_ 等）
- **scanContent()**：综合安全扫描，返回 `{ passed, issues }`

### 5.4 lib/transform.mjs — 数据转换

- **getFieldTypeLabel()**：飞书字段类型码 → 人类可读标签
- **transformFieldValue()**：飞书原始字段值 → 公开安全 JSON（处理富文本数组、关联字段、选择字段等）
- **selectRecord()**：从原始记录中选取白名单字段并转换
- **buildSchemaEntry()**：构建表的 schema 条目（字段类型、选项、关联解析）
- **escapeHtml()**：HTML 转义

### 5.5 lib/output.mjs — 输出文件管理

- **writeJson()**：写入 JSON 文件，写入前调用 `assertNoSecrets()` 安全扫描，返回 `{ bytes, sha256 }`
- **writeText()**：写入文本文件，同样带安全扫描
- **copyFile()**：复制文件（用于遗留路径镜像）
- **walkDir()**：递归遍历目录
- **generateBuildId()**：生成 build_id（`<时间戳>-<短SHA>`）
- **buildProjectIndexHtml()**：构建项目首页 HTML
- **buildHubHomepage()**：构建 Hub 全局首页 HTML

---

## 6. 故障隔离

### 6.1 故障分类

| 故障类型 | 触发条件 | 影响范围 | 处理方式 |
|---|---|---|---|
| **普通故障** | 网络超时、API 错误、字段缺失、视图缺失 | 仅该失败项目 | 标记失败，尝试恢复旧版，其他项目继续 |
| **安全故障** | 检测到凭证值、敏感信息模式、Token 前缀、内部标识符 | **整个部署中止** | `process.exit(1)`，不部署任何内容 |

### 6.2 普通故障处理

当 `syncProject()` 抛出非安全类错误时：

1. `sync-hub.mjs` 捕获错误，将该项目的状态标记为 `failed`
2. 调用 `hydrateExistingProject()` 尝试恢复上一次成功版本：
   - 读取 `public/projects/<slug>/manifest.json`（因原子替换，旧版本仍在磁盘上）
   - 更新 `status.json`，标记 `is_stale: true`、`sync_status: "failed"`
   - 保留 `last_success_at` 时间戳
3. 该项目在 catalog 中以 `stale` 状态出现，消费者可据此判断数据新鲜度
4. 其他项目不受影响，继续同步和部署

### 6.3 安全故障处理

当 `syncProject()` 抛出安全类错误（错误消息包含 `凭证值`、`敏感信息`、`secret`、`token`、`authorization` 等关键词）时：

1. `sync-hub.mjs` 收集所有安全错误
2. **立即中止整个部署**：`process.exit(1)`
3. GitHub Actions 构建任务失败，部署任务不执行
4. 已有 Pages 部署不受影响（直到下一次成功同步才更新）

### 6.4 原子目录替换

`sync-project.mjs` 对每个项目使用原子目录替换策略：

```
1. 创建临时目录 public/projects/<slug>.tmp/
2. 将所有输出文件写入临时目录
3. 全部写入成功后：
   a. 删除旧目录 public/projects/<slug>/
   b. 重命名临时目录 → public/projects/<slug>/
4. 若步骤 2 中途失败：
   - 临时目录被丢弃
   - 旧目录保持不变（下次 hydrate 可恢复）
```

这保证了同步失败时，上一次成功版本的输出完整保留在磁盘上。

### 6.5 hydrate-existing-project.mjs

故障恢复脚本，在普通故障发生时由 `sync-hub.mjs` 自动调用：

- 检查 `public/projects/<slug>/manifest.json` 是否存在
- 若存在，读取旧 manifest，更新 `status.json`：
  - `sync_status: "failed"`
  - `is_stale: true`
  - `last_attempt_at: <当前时间>`
  - `last_success_at: <保留旧值>`
  - `warnings: ["项目同步失败，已恢复上次成功版本"]`
- 也可通过 CLI 单独运行：`node scripts/hydrate-existing-project.mjs <slug>`

---

## 7. 遗留兼容

### 7.1 mirror_to_legacy_root

`learning-english` 项目配置了 `compatibility.mirror_to_legacy_root: true`，确保迁移后旧 URL 路径继续可用。

镜像规则（在 `sync-project.mjs` 的 `mirrorToLegacyPaths()` 中实现）：

| 新路径 | 旧路径（镜像） |
|---|---|
| `public/projects/learning-english/manifest.json` | `public/data/manifest.json` |
| `public/projects/learning-english/schema.json` | `public/data/schema.json` |
| `public/projects/learning-english/tables/<slug>/fields.json` | `public/data/<slug>/fields.json` |
| `public/projects/learning-english/tables/<slug>/records-XXXX.json` | `public/data/<slug>/records-XXXX.json` |

同时生成一个遗留兼容的 `public/index.html`，保持旧版首页外观并添加指向新 catalog 的链接。

### 7.2 遗留配置文件

`config/export.json`（schema_version 2）在迁移期保留，供遗留脚本 `scripts/sync.mjs` 和 `scripts/validate.mjs` 使用。新架构不再依赖此文件。

### 7.3 遗留脚本

- `scripts/sync.mjs`：旧版单项目同步脚本，输出到 `site/` 目录
- `scripts/validate.mjs`：旧版单项目验证脚本，验证 `site/` 目录

这两个脚本在新架构中不再被 GitHub Actions 调用，仅作为迁移期参考保留。

---

## 8. 缓存清除

GitHub Pages 使用 CDN 缓存，为确保消费者获取最新数据，采用多层缓存清除策略：

### 8.1 build_id

每次同步生成唯一的 `build_id`，格式为 `<时间戳>-<短SHA>`：

```
20260725T031700Z-a1b2c3d4
```

`build_id` 嵌入到以下文件中：
- `catalog.json`（`build_id` 字段）
- `catalog-versioned/<build_id>.json`（文件名本身）
- 各项目的 `manifest.json`（`build_id` 字段）
- 各项目的 `status.json`（`build_id` 字段）
- `index.html`（显示在页面上，用于链接的 `?v=` 参数）

### 8.2 URL 查询参数 ?v=<build_id>

所有 HTML 页面中的 JSON 链接都附加 `?v=<build_id>` 查询参数：

```html
<a href="catalog.json?v=20260725T031700Z-a1b2c3d4">catalog.json</a>
<a href="projects/learning-english/manifest.json?v=20260725T031700Z-a1b2c3d4">manifest.json</a>
```

CDN 将带不同查询参数的 URL 视为不同资源，确保浏览器和 CDN 获取最新版本。

### 8.3 catalog-versioned/ 目录

每次同步在 `public/catalog-versioned/` 下写入一个以 `build_id` 命名的 catalog 快照：

```
public/catalog-versioned/20260725T031700Z-a1b2c3d4.json
public/catalog-versioned/20260725T041700Z-e5f6g7h8.json
```

消费者可以引用特定版本的 catalog，确保数据可追溯。首页同时提供指向当前版本 catalog 和版本化 catalog 的链接。

---

## 9. GitHub Actions 工作流

| 工作流 | 触发条件 | 说明 |
|---|---|---|
| `sync-hourly.yml` | cron `17 * * * *`（每小时第 17 分钟）+ `workflow_dispatch` | 同步 tier=hourly 的项目 |
| `sync-daily.yml` | cron `17 3 * * *`（每天 03:17 UTC）+ `workflow_dispatch` | 同步 tier=daily 的项目 |
| `sync-manual.yml` | `workflow_dispatch` 仅手动 | 同步全部或指定项目，支持 force 和 dry-run |
| `validate.yml` | `pull_request` + `push`（main 分支）+ `workflow_dispatch` | 轻量验证，**无密钥访问**，仅配置和语法检查 |

所有 Actions 均使用固定 commit SHA 锁定，依赖 Dependabot 每周检查更新。

### 工作流流水线（sync-* 系列）

```
checkout → setup Node 22 → npm ci → npm run check（语法检查）
    → npm run validate:config（配置验证）
    → node scripts/sync-hub.mjs（同步）
    → npm run validate（输出验证 + 安全扫描）
    → configure-pages → upload-pages-artifact → deploy-pages
```

并发控制：`concurrency.group: feishu-pages`，`cancel-in-progress: false`（不取消正在进行的同步）。

### validate.yml 工作流（PR 验证）

```
checkout → setup Node 22 → npm ci → npm run check → npm run validate:config
```

**注意**：PR 验证工作流不注入任何 GitHub Secrets，无法访问飞书凭据，仅验证配置文件结构。这是安全设计——外部贡献者的 PR 不会接触生产密钥。

---

## 10. 输出文件结构详解

### 10.1 catalog.json（全局目录）

```json
{
  "catalog_version": 1,
  "build_id": "20260725T031700Z-a1b2c3d4",
  "generated_at": "2026-07-25T03:17:00.000Z",
  "hub": {
    "title": "Feishu Data Hub",
    "description": "统一公开导出的飞书多维表格数据中心"
  },
  "projects": [
    {
      "slug": "learning-english",
      "title": "英语学习系统",
      "description": "词汇、文本、计划、日志和能力状态",
      "group": "learning",
      "tags": ["英语", "学习"],
      "status": "active",
      "sync_status": "ok",
      "is_stale": false,
      "last_success_at": "2026-07-25T03:17:00.000Z",
      "manifest": "projects/learning-english/manifest.json",
      "schema": "projects/learning-english/schema.json",
      "summary": "projects/learning-english/summary.md",
      "homepage": "projects/learning-english/index.html",
      "table_count": 4,
      "total_records": 6131
    }
  ]
}
```

### 10.2 项目 manifest.json

```json
{
  "schema_version": 2,
  "project_slug": "learning-english",
  "build_id": "20260725T031700Z-a1b2c3d4",
  "generated_at": "2026-07-25T03:17:00.000Z",
  "base": { "name": "英语学习系统" },
  "tables": [
    {
      "name": "文本库",
      "slug": "text-library",
      "view_name": "AI 公开导出",
      "field_count": 18,
      "record_count": 30,
      "fields_file": "tables/text-library/fields.json",
      "fields_bytes": 1234,
      "fields_sha256": "...",
      "record_files": [
        { "path": "tables/text-library/records-0001.json", "record_count": 30, "bytes": 5678, "sha256": "..." }
      ]
    }
  ]
}
```

### 10.3 项目 status.json

```json
{
  "project_slug": "learning-english",
  "build_id": "20260725T031700Z-a1b2c3d4",
  "sync_status": "ok",
  "is_stale": false,
  "last_attempt_at": "2026-07-25T03:17:00.000Z",
  "last_success_at": "2026-07-25T03:17:00.000Z",
  "source_record_count": 6131,
  "published_record_count": 6131,
  "warnings": []
}
```

`sync_status` 可能的值：`ok`（成功）、`failed`（失败但已恢复旧版，即 stale）、`stale`（同 failed）。

`is_stale: true` 表示当前展示的是上一次成功版本，最近一次同步尝试失败。

---

## 相关文档

- [接入指南](./ONBOARDING.md) — 如何添加新的飞书 Base
- [运维手册](./OPERATIONS.md) — 日常运维操作
- [安全策略](./SECURITY.md) — 公开数据边界和安全防护
- [迁移基线](./MIGRATION_BASELINE.md) — 迁移前状态快照
- [迁移报告](./MIGRATION_REPORT.md) — 迁移完成情况
