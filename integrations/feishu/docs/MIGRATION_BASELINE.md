# 迁移基线快照

> **历史存档（2026-09-03）**
> 本文档记录的是 **迁入 ai-platform 之前** 的状态，文中的仓库名与 URL 均指向已退役的旧仓
> （`201650545/feishu-data-hub`）与旧站点（`https://201650545.github.io/feishu-data-hub/`）。
> **原样保留、不做改写**，仅供追溯。当前状态见 [MIGRATION-NOTE.md](../MIGRATION-NOTE.md)。


本文档记录 Feishu Data Hub 迁移前的系统状态，作为迁移的参照基线和回滚目标。迁移前已打 Git 标签 `pre-data-hub-migration`。

---

## 1. 迁移前状态概览

| 维度 | 迁移前状态 |
|---|---|
| 项目数量 | 1（单项目） |
| 项目名称 | learning-english |
| 数据表数量 | 4 |
| 记录总数 | 6131 |
| 配置文件 | `config/export.json`（schema_version 2） |
| 同步脚本 | `scripts/sync.mjs`（单文件，输出到 `site/`） |
| 验证脚本 | `scripts/validate.mjs`（单文件，验证 `site/`） |
| GitHub Actions | `deploy-pages.yml`（每小时 cron） |
| 输出目录 | `site/` |
| Git 标签 | `pre-data-hub-migration` |

---

## 2. 数据表记录

迁移前的 4 张数据表及其记录数：

| 飞书表名 | Slug | 字段数 | 记录数 | 视图名 |
|---|---|---|---|---|
| 文本库 | `text-library` | 18 | 30 | AI 公开导出 |
| 轻量学习记录 | `vocabulary` | 22 | 6000 | AI 公开导出 |
| 学习日志 | `learning-log` | 9 | 92 | AI 公开导出 |
| 每日计划 | `daily-plan` | 8 | 9 | AI 公开导出 |
| **合计** | | **57** | **6131** | |

### 2.1 文本库（text-library）

- **字段数**：18
- **记录数**：30
- **字段白名单**：文本标题、英文原文、来源类型、来源详情、难度等级、适用词带、文本总词数、覆盖词数、词汇覆盖率、生词暴露数、使用状态、使用次数、上次使用日期、最早复用日期、中文参考译文、覆盖词汇列表、关联词汇、备注

### 2.2 轻量学习记录（vocabulary）

- **字段数**：22
- **记录数**：6000
- **字段白名单**：单词、词性、最简中文、核心用法、例句、我的造句、修改后句子、考研搭配、音标、词根词缀助记、派生词、学习次数、难度等级、词表来源、掌握状态、记忆阶段、正确次数、上次测验、下次复习、掌握维度、学习日志、关联文本

### 2.3 学习日志（learning-log）

- **字段数**：9
- **记录数**：92
- **字段白名单**：日期、测验方向、测验维度、结果、正确答案、你的回答、测验类型、关联单词、检测方式

### 2.4 每日计划（daily-plan）

- **字段数**：8
- **记录数**：9
- **字段白名单**：日期、复习词数、单词列表、完成状态、新词数、正确率、计划类型、单词列表(link)

---

## 3. 旧 URL 路径（必须继续可用）

以下 URL 路径在迁移后必须继续工作，通过 `mirror_to_legacy_root` 机制实现：

| 旧路径 | 用途 | 迁移后对应新路径 |
|---|---|---|
| `/index.html` | 人类可读首页 | `/index.html`（遗留兼容版本） |
| `/data/manifest.json` | 机器可读表清单（含校验和） | `/projects/learning-english/manifest.json` |
| `/data/schema.json` | 数据模型（字段类型、关联） | `/projects/learning-english/schema.json` |
| `/data/<table-slug>/fields.json` | 字段元数据 | `/projects/learning-english/tables/<table-slug>/fields.json` |
| `/data/<table-slug>/records-XXXX.json` | 记录分片 | `/projects/learning-english/tables/<table-slug>/records-XXXX.json` |

**具体 URL 列表**：

```
https://201650545.github.io/feishu-data-hub/index.html
https://201650545.github.io/feishu-data-hub/data/manifest.json
https://201650545.github.io/feishu-data-hub/data/schema.json
https://201650545.github.io/feishu-data-hub/data/text-library/fields.json
https://201650545.github.io/feishu-data-hub/data/text-library/records-0001.json
https://201650545.github.io/feishu-data-hub/data/vocabulary/fields.json
https://201650545.github.io/feishu-data-hub/data/vocabulary/records-0001.json
https://201650545.github.io/feishu-data-hub/data/vocabulary/records-0002.json
https://201650545.github.io/feishu-data-hub/data/learning-log/fields.json
https://201650545.github.io/feishu-data-hub/data/learning-log/records-0001.json
https://201650545.github.io/feishu-data-hub/data/daily-plan/fields.json
https://201650545.github.io/feishu-data-hub/data/daily-plan/records-0001.json
```

**注意**：`vocabulary` 表有 6000 条记录，按 `chunk_size: 500` 分片，共 12 个分片（`records-0001.json` 到 `records-0012.json`）。

---

## 4. 旧输出目录结构

```
site/
├── index.html              # 人类可读首页
└── data/
    ├── manifest.json       # v2: 表清单含校验和
    ├── schema.json         # 字段类型、选项、关联
    ├── text-library/
    │   ├── fields.json
    │   └── records-0001.json
    ├── vocabulary/
    │   ├── fields.json
    │   ├── records-0001.json
    │   └── ...              # 共 12 个分片
    ├── learning-log/
    │   ├── fields.json
    │   └── records-0001.json
    └── daily-plan/
        ├── fields.json
        └── records-0001.json
```

---

## 5. 旧配置格式

### 5.1 config/export.json

迁移前使用单一 JSON 配置文件，schema_version 2：

```json
{
  "schema_version": 2,
  "chunk_size": 500,
  "max_table_bytes": 26214400,
  "include_record_id": true,
  "include_timestamps": true,
  "tables": [
    {
      "table_name": "文本库",
      "table_slug": "text-library",
      "view_name": "AI 公开导出",
      "enabled": true,
      "fields": ["文本标题", "英文原文", "..."]
    }
  ]
}
```

**与新架构的区别**：
- 旧：单一 JSON 文件，所有表在一个 `tables` 数组中
- 新：每个项目一个 YAML 文件（`config/projects/<slug>.yaml`），支持多项目
- 旧：无项目概念，隐含单项目
- 新：显式项目概念，支持 `source.base_key`、`schedule.tier`、`compatibility` 等
- 迁移期：`config/export.json` 保留，供遗留脚本使用

### 5.2 旧 GitHub Secrets

| Secret 名称 | 用途 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用密钥 |
| `FEISHU_BASE_TOKEN` | 单个 Base 的 app_token |

迁移前无 `FEISHU_BASE_REGISTRY_JSON`，使用单一 `FEISHU_BASE_TOKEN`。

---

## 6. 旧 GitHub Actions

### 6.1 deploy-pages.yml

迁移前的 GitHub Actions 工作流文件为 `deploy-pages.yml`：

- **触发**：`cron: "17 * * * *"`（每小时第 17 分钟）+ `workflow_dispatch`
- **权限**：`contents: read`、`pages: write`、`id-token: write`
- **所有 Actions 固定到完整 commit SHA**
- **流水线**：checkout → setup Node → npm ci → syntax check → sync → validate → configure pages → upload artifact → deploy
- **失败即停止部署**：sync 或 validate 失败时，构建任务非零退出，部署任务不执行

### 6.2 与新架构工作流的对比

| 维度 | 旧（deploy-pages.yml） | 新（sync-hourly/daily/manual.yml + validate.yml） |
|---|---|---|
| 文件数 | 1 | 4 |
| 触发 | 每小时 cron + 手动 | 每小时 cron + 每日 cron + 手动 + PR/push |
| 项目范围 | 全部（隐含单项目） | 按 tier 分层（hourly/daily）或指定项目 |
| 同步脚本 | `scripts/sync.mjs` | `scripts/sync-hub.mjs` |
| 输出目录 | `site/` | `public/` |
| 配置验证 | 无独立步骤 | `npm run validate:config`（独立步骤） |
| 安全扫描 | 内嵌在 `validate.mjs` 中 | 独立 `npm run security:scan` 步骤 |
| Dry-run | 不支持 | 支持 |
| PR 验证 | 无 | `validate.yml`（无密钥） |
| 并发控制 | 无 | `concurrency.group: feishu-pages` |

---

## 7. 旧同步脚本

### 7.1 scripts/sync.mjs

迁移前的同步脚本是单文件 `scripts/sync.mjs`：

- 从环境变量读取 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_TOKEN`
- 从 `config/export.json` 读取配置
- 输出到 `site/` 目录
- 无项目概念，隐含单项目
- 内嵌飞书 API 客户端、安全扫描、数据转换逻辑（未模块化）
- `assertNoSecrets()` 内嵌在脚本中
- 同步前清空整个 `site/` 目录（`fs.rm(OUTPUT_DIR, { recursive: true, force: true })`）

### 7.2 scripts/validate.mjs

迁移前的验证脚本是单文件 `scripts/validate.mjs`：

- 验证 `site/` 目录
- 检查 manifest.json 结构和版本
- 验证各表的校验和（SHA-256）
- 验证记录数一致性
- 检查重复 record_id
- 验证关联字段目标 slug
- 扫描所有文件中的敏感信息模式
- 检查禁止文件
- 硬编码检查特定 table_id 和 app_token 值

### 7.3 与新架构的区别

| 维度 | 旧 | 新 |
|---|---|---|
| 代码组织 | 单文件，逻辑内嵌 | 模块化（`lib/` + `scripts/`） |
| 输出目录 | `site/` | `public/` |
| 项目支持 | 单项目 | 多项目 |
| 配置格式 | JSON | YAML（每项目独立文件） |
| 安全扫描 | 内嵌 | 独立模块 + 独立脚本 |
| 故障隔离 | 无（整体失败） | 普通故障仅影响失败项目 |
| 缓存清除 | 无 | build_id + ?v= + catalog-versioned/ |
| 目录替换 | 清空后重建 | 原子替换（temp → rename） |

---

## 8. Git 标签

迁移前已打 Git 标签：

```
pre-data-hub-migration
```

**用途**：
- 作为迁移的参照点
- 作为回滚目标（`git checkout pre-data-hub-migration`）
- 记录迁移前的完整代码状态

**查看标签**：

```bash
git tag -l "pre-data-hub-migration"
git show pre-data-hub-migration
```

---

## 9. 迁移兼容性保证

迁移后，以下兼容性必须得到保证：

### 9.1 URL 兼容性

所有旧 URL 路径（`/data/*`、`/index.html`）必须继续可用，通过 `mirror_to_legacy_root: true` 实现镜像。

### 9.2 数据一致性

迁移后 `learning-english` 项目的数据必须与迁移前一致：
- 相同的 4 张表
- 相同的字段白名单
- 相同的记录数（30 + 6000 + 92 + 9 = 6131）
- 相同的记录内容

### 9.3 同步频率

迁移后保持每小时同步频率（`schedule.tier: hourly`，cron `17 * * * *`）。

### 9.4 安全策略

迁移后安全策略不降级：
- 视图级防护（`AI 公开导出` 视图）保持
- 字段级防护（显式白名单，禁止通配符）保持
- 内容级防护（安全扫描）增强（独立 `security-scan.mjs`）

---

## 相关文档

- [迁移报告](./MIGRATION_REPORT.md) — 迁移完成情况
- [架构概览](./ARCHITECTURE.md) — 新架构详情
- [运维手册](./OPERATIONS.md) — 回滚操作
- [安全策略](./SECURITY.md) — 安全策略
