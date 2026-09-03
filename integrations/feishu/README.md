# Feishu Data Hub

> **迁移状态（2026-09-03）**
> 本模块已由独立仓 `feishu-data-hub` 迁入 AI 平台主仓 `ai-platform`，现位于 **`integrations/feishu/`**。
> - 新仓：<https://github.com/201650545/ai-platform>
> - 迁移说明见 **[MIGRATION-NOTE.md](MIGRATION-NOTE.md)**
> - 旧 Pages 站点 `https://201650545.github.io/feishu-data-hub/` 将在集成后失效，新站点地址待 Pages 源重新配置后确定（详见迁移说明）。
> - 下文所有命令默认在 **`integrations/feishu/`** 目录下执行。

统一公开导出的飞书多维表格数据中心。将飞书 Bitable 数据导出为静态 JSON，部署到 GitHub Pages，供 AI 工具和其他消费者读取数据模型、记录和表间关联，无需飞书访问权限。

**站点地址**：迁移后待定（原 `https://201650545.github.io/feishu-data-hub/` 已失效）

---

## 公开入口

| 路径 | 用途 |
|---|---|
| `/catalog.json` | 全局目录，索引所有项目及其状态 |
| `/index.html` | Hub 首页，人类可读的项目总览 |
| `/projects/<slug>/manifest.json` | 项目清单（表列表 + 校验和） |
| `/projects/<slug>/schema.json` | 项目数据模型（字段类型 + 关联） |
| `/projects/<slug>/status.json` | 项目同步状态（sync_status、is_stale） |
| `/projects/<slug>/index.html` | 项目首页，人类可读的表总览 |
| `/data/manifest.json` | 遗留兼容清单（learning-english 镜像） |
| `/data/schema.json` | 遗留兼容数据模型（learning-english 镜像） |

---

## 当前项目

| 项目 | Slug | 表数 | 记录数 | 说明 |
|---|---|---|---|---|
| 英语学习系统 | `learning-english` | 4 | 6131 | 词汇、文本、计划、日志 |

### learning-english 数据表

| 飞书表名 | Slug | 字段数 | 记录数 |
|---|---|---|---|
| 文本库 | `text-library` | 18 | 30 |
| 轻量学习记录 | `vocabulary` | 22 | 6000 |
| 学习日志 | `learning-log` | 9 | 92 |
| 每日计划 | `daily-plan` | 8 | 9 |

---

## 如何添加新项目

简要步骤：

1. 在飞书 Base 中创建 `AI 公开导出` 视图
2. 给统一飞书应用授予只读权限
3. 更新 GitHub Secret `FEISHU_BASE_REGISTRY_JSON`
4. 运行 `npm run project:add -- --slug <slug> --title "标题" --base-key <key>`
5. 编辑项目 YAML，配置表和字段白名单
6. Dry-run 验证 → 安全扫描 → 手动部署验证

详见 **[docs/ONBOARDING.md](docs/ONBOARDING.md)**。

---

## 本地执行

> 在 `integrations/feishu/` 目录下执行（迁入主仓后路径已变更）：

```bash
cd integrations/feishu
# 安装依赖
npm ci

# 语法检查
npm run check

# 配置验证
npm run validate:config

# 同步所有项目（需设置飞书凭据环境变量）
npm run sync

# 同步单个项目
npm run sync:project -- <slug>
# 或: node scripts/sync-hub.mjs --project <slug>

# 全部验证（配置 + 输出 + 安全扫描）
npm run validate

# 仅安全扫描
npm run security:scan

# 添加新项目脚手架
npm run project:add -- --slug <slug> --title "标题" --base-key <key>
```

所需环境变量：

```bash
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_REGISTRY_JSON='{"learning-english": {"app_token": "xxxx"}}'
```

---

## 架构概览

采用 **"单仓库多项目"** 架构：一个仓库、一个 Pages 站点、一套同步代码、一次安全扫描、一组 Actions、一个 catalog.json，支持多个独立的飞书 Base。

```
飞书 Base → sync-project.mjs → public/projects/<slug>/ → catalog.json → GitHub Pages
```

核心特性：
- **故障隔离**：普通故障仅影响失败项目，安全故障中止整个部署
- **遗留兼容**：`mirror_to_legacy_root` 保持旧 URL 可用
- **缓存清除**：`build_id` + `?v=<build_id>` + `catalog-versioned/`

详见 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**。

---

## 安全

公开数据采用三层防护：

1. **视图级**：仅导出 `AI 公开导出` 视图
2. **字段级**：显式字段白名单，禁止通配符，禁止敏感字段名
3. **内容级**：写入时和部署前双重模式扫描

安全故障（检测到凭证或敏感信息）会中止整个部署。

详见 **[docs/SECURITY.md](docs/SECURITY.md)**。

---

## GitHub Actions

| 工作流文件 | 工作流 `name:`（迁入后） | 触发 | 说明 |
|---|---|---|---|
| `sync-hourly.yml` | `Feishu: Hourly Sync` | cron `17 * * * *` | 每小时同步 hourly 层级项目 |
| `sync-daily.yml` | `Feishu: Daily Sync` | cron `17 3 * * *` | 每日同步 daily 层级项目 |
| `sync-manual.yml` | `Feishu: Manual Sync` | 手动 | 同步全部或指定项目，支持 force 和 dry-run |
| `validate.yml` | `Feishu: Validate` | PR / push | 轻量验证（无密钥访问） |

> **重要 —— 工作流当前不生效**
> 四个工作流文件现位于本模块的 `integrations/feishu/.github/workflows/` 下。
> GitHub **只识别仓库根目录** `.github/workflows/`，因此当前位置不会触发任何运行。
> 集成阶段需由负责根目录的维护者将这 4 个文件迁移到根目录 `.github/workflows/`，
> 并按上表的 `name:` 重命名，避免与主仓其他业务线的工作流重名。
> 文件内已预置 `working-directory`、路径过滤与 `cache-dependency-path`，迁移到根目录后可直接运行。

所有 Actions 固定到完整 commit SHA，Dependabot 每周检查更新（配置文件：`integrations/feishu/.github/dependabot.yml`，集成时需合并进根目录的 dependabot 配置）。

流水线：checkout → Node 22 → npm ci → 语法检查 → 配置验证 → 同步 → 输出验证 → 安全扫描 → 部署

---

## 文档

| 文档 | 说明 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构概览 |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | 新项目接入指南 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 运维手册 |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全策略 |
| [docs/MIGRATION_BASELINE.md](docs/MIGRATION_BASELINE.md) | 迁移前基线快照（历史存档） |
| [docs/MIGRATION_REPORT.md](docs/MIGRATION_REPORT.md) | 迁移报告（历史存档） |
| [MIGRATION-NOTE.md](MIGRATION-NOTE.md) | **2026-09-03 迁入 ai-platform 的迁移说明** |
