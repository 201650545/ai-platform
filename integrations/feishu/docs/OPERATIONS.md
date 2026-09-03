# 运维手册

> **迁移说明（2026-09-03）**
> 本模块已由独立仓 `feishu-data-hub` 迁入 AI 平台主仓 `ai-platform`，位于 `integrations/feishu/`。
> 下文中的站点 URL 已按新仓 Pages 根 `https://201650545.github.io/ai-platform/` 更新；若集成时 Pages 源配置为子路径或
> 自定义域名，请同步替换。旧站点 `https://201650545.github.io/feishu-data-hub/` 已失效。
> 详见 [MIGRATION-NOTE.md](../MIGRATION-NOTE.md)。


本文档涵盖 Feishu Data Hub 的日常运维操作，包括 GitHub Secrets 配置、监控方法、常用操作、故障排查和回滚流程。

---

## 1. GitHub Secrets 配置

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中配置以下 Secrets：

| Secret 名称 | 用途 | 是否必需 |
|---|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID（遗留回退） | 是（迁移期主用） |
| `FEISHU_APP_SECRET` | 飞书应用密钥（绝不记录、绝不写入输出） | 是（迁移期主用） |
| `FEISHU_BASE_TOKEN` | 单 Base 的 app_token（遗留回退） | 否（单 Base 模式回退用） |
| `FEISHU_BASE_REGISTRY_JSON` | 多 Base 注册表（JSON 格式） | 是（多 Base 模式主用） |

### 1.1 FEISHU_APP_ID / FEISHU_APP_SECRET

飞书应用的凭据，用于获取 `tenant_access_token`。

- 在飞书开放平台 → 应用管理 → 凭据与基础信息中获取
- `FEISHU_APP_SECRET` 是高敏感信息，仅在 GitHub Actions 运行时通过环境变量注入，绝不记录在日志中
- `credential-profiles.yaml` 中配置了 `FEISHU_PUBLIC_APP_ID` / `FEISHU_PUBLIC_APP_SECRET` 作为主密钥，`FEISHU_APP_ID` / `FEISHU_APP_SECRET` 作为回退密钥。迁移期使用回退密钥

### 1.2 FEISHU_BASE_TOKEN（遗留回退）

单个飞书 Base 的 `app_token`，用于单 Base 模式。

- 仅当 `FEISHU_BASE_REGISTRY_JSON` 未配置或解析失败时回退使用
- 迁移完成后建议删除此 Secret，统一使用 `FEISHU_BASE_REGISTRY_JSON`

### 1.3 FEISHU_BASE_REGISTRY_JSON（多 Base 注册表）

多 Base 模式的核心配置，一个 JSON 对象，映射 base_key 到 app_token：

```json
{
  "learning-english": {
    "app_token": "REDACTED"
  },
  "another-project": {
    "app_token": "REDACTED"
  }
}
```

**格式说明**：
- 顶层 key：base_key，与项目 YAML 中 `source.base_key` 的值对应
- value：对象，包含 `app_token` 字段
- `app_token` 的值是飞书 Base 的唯一标识（敏感信息）

**凭据解析优先级**（在 `lib/config.mjs` 的 `resolveCredentials()` 中实现）：

```
1. 从 FEISHU_BASE_REGISTRY_JSON 中查找 base_key 对应的 app_token
2. 若未找到，回退到 FEISHU_BASE_TOKEN（单 Base 模式）
3. app_id / app_secret：先查 FEISHU_PUBLIC_APP_ID/SECRET，再回退到 FEISHU_APP_ID/SECRET
```

---

## 2. GitHub Pages 站点

**站点 URL**：

```
https://201650545.github.io/ai-platform/
```

**部署来源**：`public/` 目录（通过 `actions/upload-pages-artifact` 上传）

**部署方式**：GitHub Actions → `actions/deploy-pages`

**部署频率**：
- 每小时第 17 分钟（UTC）自动同步并部署 hourly 层级项目
- 每天 03:17（UTC）自动同步并部署 daily 层级项目
- 手动触发随时可用

---

## 3. 监控

### 3.1 检查 catalog.json

访问全局目录，确认所有项目状态：

```
https://201650545.github.io/ai-platform/catalog.json
```

关键字段：
- `build_id`：当前构建版本标识
- `generated_at`：catalog 生成时间
- `projects[].sync_status`：`ok`（正常）、`failed`/`stale`（异常）
- `projects[].is_stale`：`true` 表示展示的是旧版本数据
- `projects[].last_success_at`：最后一次成功同步时间

### 3.2 检查项目 status.json

访问特定项目的同步状态：

```
https://201650545.github.io/ai-platform/projects/<slug>/status.json
```

关键字段：
- `sync_status`：`ok` 或 `failed`
- `is_stale`：`true` 表示当前数据为旧版本
- `last_attempt_at`：最近一次同步尝试时间
- `last_success_at`：最近一次成功同步时间
- `source_record_count`：源数据记录数
- `published_record_count`：已发布记录数
- `warnings`：警告信息数组

### 3.3 sync_status 字段说明

| 值 | 含义 | 消费者行为建议 |
|---|---|---|
| `ok` | 最近一次同步成功，数据为最新 | 正常使用 |
| `failed` | 最近一次同步失败，已恢复旧版本 | 数据可能过时，检查 `last_success_at` |
| `stale` | 同 `failed`（别名） | 同上 |

### 3.4 is_stale 字段说明

- `false`：数据是最新的
- `true`：当前展示的是上一次成功同步的版本，最近一次同步尝试失败

消费者应定期检查 `is_stale`，若长时间为 `true`，需排查同步故障。

### 3.5 GitHub Actions 运行状态

在 GitHub 仓库的 **Actions** 页面监控工作流运行状态：
- **Hourly Sync**：每小时自动运行
- **Daily Sync**：每天自动运行
- **Manual Sync**：手动触发
- **Validate**：PR 和 push 时运行

关注失败的运行（红色叉号），点击查看日志定位问题。

---

## 4. 常用操作

### 4.1 手动同步单个项目

通过 GitHub Actions 手动触发单个项目同步：

1. 进入仓库 **Actions** 页面
2. 选择 **Manual Sync** 工作流
3. 点击 **Run workflow**
4. 在 `project_slug` 输入框中填入项目 slug（如 `learning-english`）
5. 保持 `dry_run` 不勾选
6. 点击 **Run workflow**

或通过命令行本地执行：

```bash
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_REGISTRY_JSON='{"learning-english": {"app_token": "xxxx"}}'

node scripts/sync-hub.mjs --project learning-english
```

### 4.2 强制重新同步

强制全量重新同步（忽略任何缓存）：

通过 GitHub Actions：
1. 选择 **Manual Sync** 工作流
2. 勾选 `force` 选项
3. 运行

通过命令行：

```bash
node scripts/sync-hub.mjs --force
```

### 4.3 Dry-run 模式

仅验证同步流程，不写入输出、不部署：

通过 GitHub Actions：
1. 选择 **Manual Sync** 工作流
2. 勾选 `dry_run` 选项
3. 运行

通过命令行：

```bash
node scripts/sync-hub.mjs --project learning-english --dry-run
```

### 4.4 查看同步日志

通过 GitHub Actions：
1. 进入仓库 **Actions** 页面
2. 点击对应的 workflow run
3. 点击 **build** job
4. 查看 **Sync Feishu Base** 步骤的日志

日志中会显示：
- 每个项目的同步状态（`✓ 同步成功` 或 `✗ 普通故障`/`✗ 安全故障`）
- 每张表的记录数和分片数
- catalog 构建结果
- 同步摘要（成功/恢复旧版/失败计数）

### 4.5 本地验证

```bash
# 安装依赖
npm ci

# 语法检查
npm run check

# 配置验证
npm run validate:config

# 输出验证（需要先有 public/ 输出）
npm run validate:output

# 安全扫描
npm run security:scan

# 全部验证（配置 + 输出 + 安全）
npm run validate
```

### 4.6 添加新项目脚手架

```bash
npm run project:add -- --slug <slug> --title "标题" --base-key <key>
```

详见 [接入指南](./ONBOARDING.md)。

---

## 5. 故障排查

### 5.1 项目变为 stale 状态

**现象**：`catalog.json` 或 `status.json` 中某项目 `is_stale: true`、`sync_status: "failed"`。

**原因**：该项目的最近一次同步尝试失败（网络超时、API 错误等），系统已自动恢复上一次成功版本。

**排查步骤**：
1. 查看 GitHub Actions 日志中该项目的错误信息
2. 常见原因：
   - 飞书 API 限流（HTTP 429）→ 等待后自动恢复
   - 飞书服务暂时不可用（HTTP 5xx）→ 等待后自动恢复
   - 视图缺失 → 检查飞书 Base 中 `AI 公开导出` 视图是否存在
   - 字段缺失 → 检查项目 YAML 中的字段白名单是否与飞书 Base 当前字段一致
   - 凭据过期 → 检查 `FEISHU_APP_SECRET` 是否有效
3. 修复问题后，手动触发同步
4. 确认 `sync_status` 恢复为 `ok`

### 5.2 视图缺失

**现象**：同步报错 `视图不存在：AI 公开导出` 或 `没有找到带 "AI 公开导出" 视图的表`。

**原因**：飞书 Base 中缺少名为 `AI 公开导出` 的表格视图。

**解决**：
1. 打开飞书 Base
2. 在目标数据表中创建表格视图
3. 名称精确为 `AI 公开导出`（含空格）
4. 重新触发同步

### 5.3 权限错误

**现象**：同步报错飞书 API 权限不足，或 `缺少所需凭据`。

**排查步骤**：
1. 确认 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 已正确配置在 GitHub Secrets 中
2. 确认 `FEISHU_BASE_REGISTRY_JSON` 中包含该项目的 base_key 和 app_token
3. 确认飞书应用已被添加为目标 Base 的协作者
4. 确认权限为只读（`bitable:app:readonly`）
5. 确认飞书应用未被停用或删除

### 5.4 CDN 缓存问题

**现象**：GitHub Actions 同步成功，但访问 Pages URL 仍看到旧数据。

**原因**：GitHub Pages CDN 缓存未更新。

**解决**：
1. 使用带 `?v=<build_id>` 查询参数的 URL 访问最新数据：
   ```
   https://201650545.github.io/ai-platform/catalog.json?v=<build_id>
   ```
2. 查看 `catalog.json` 中的 `build_id` 字段获取当前版本标识
3. 使用版本化 catalog 路径访问特定版本：
   ```
   https://201650545.github.io/ai-platform/catalog-versioned/<build_id>.json
   ```
4. CDN 缓存通常在数分钟到数小时内自动刷新
5. 若急需刷新，可强制重新部署（触发 Manual Sync）

### 5.5 安全扫描失败

**现象**：GitHub Actions 在 **Security scan** 步骤失败，部署未执行。

**原因**：安全扫描检测到致命问题（敏感信息、Token、内部标识符等）。

**排查步骤**：
1. 查看 Actions 日志中 **Security scan** 步骤的输出
2. 日志会列出所有致命错误及其所在文件
3. 常见原因：
   - 输出中包含 `app_secret`、`tenant_access_token` 等模式 → 检查飞书数据是否含敏感字段名
   - 输出中包含 `tbl` 前缀的 table_id → 检查 `fields.json` 是否泄露了内部 ID
   - 输出中包含 Token 前缀（`cli_`、`t-` 等）→ 检查记录内容是否含 token 类字符串
4. 修复数据源或调整字段白名单
5. 重新触发同步

**注意**：安全扫描失败会中止整个部署，所有项目都不会更新。这是设计行为，确保安全优先。

### 5.6 全部项目失败

**现象**：同步摘要显示 "所有项目均失败，退出码 1"。

**原因**：通常是全局性问题——凭据失效、网络故障、飞书服务中断。

**排查步骤**：
1. 检查 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是否有效
2. 检查 `FEISHU_BASE_REGISTRY_JSON` 格式是否正确
3. 检查飞书开放平台服务状态
4. 手动触发同步查看详细错误

---

## 6. 回滚

### 6.1 Git 回滚

如果代码变更导致问题，通过 Git 回滚：

```bash
# 查看最近的提交
git log --oneline -10

# 回滚到指定提交
git revert <commit-sha>
git push

# 或重置到指定提交（谨慎使用）
git reset --hard <commit-sha>
git push --force
```

回滚代码后，下次定时同步会自动使用旧代码重新部署。

### 6.2 回滚到迁移前状态

如果 Data Hub 迁移导致严重问题，可回滚到迁移前的单项目状态：

```bash
# 迁移前已打标签 pre-data-hub-migration
git checkout pre-data-hub-migration

# 或创建回滚分支
git checkout -b rollback-pre-migration pre-data-hub-migration
```

迁移前状态（详见 [迁移基线](./MIGRATION_BASELINE.md)）：
- 单项目 `learning-english`
- 配置文件 `config/export.json`（schema_version 2）
- 同步脚本 `scripts/sync.mjs`（输出到 `site/`）
- 验证脚本 `scripts/validate.mjs`
- GitHub Actions `deploy-pages.yml`（每小时 cron，固定 SHA）
- 4 张表：text-library、vocabulary、learning-log、daily-plan

### 6.3 数据回滚

Data Hub 的公开输出是只读快照，每次同步都是全量替换。因此：
- 回滚代码后，下次同步会重新从飞书拉取数据并生成新输出
- 无需手动回滚数据文件
- 如果飞书源数据已变更，回滚后的输出会反映飞书当前状态（而非历史快照）

---

## 7. 工作流管理

### 7.1 禁用定时同步

如需临时停止定时同步（如维护期间）：

1. 进入仓库 **Actions** 页面
2. 选择 **Hourly Sync** 或 **Daily Sync**
3. 点击右上角 `...` → **Disable workflow**
4. 维护完成后，再次 **Enable workflow**

### 7.2 修改定时频率

编辑 `.github/workflows/sync-hourly.yml` 或 `sync-daily.yml` 中的 `cron` 表达式：

```yaml
on:
  schedule:
    - cron: "17 * * * *"    # 每小时第 17 分钟
```

**注意**：修改工作流文件属于核心代码变更，需由主维护者审核。详见 [接入指南 - 代理权限边界](./ONBOARDING.md#4-ai-代理协作权限边界)。

### 7.3 并发控制

所有 sync 工作流共享并发组 `feishu-pages`，配置为 `cancel-in-progress: false`：
- 新的同步不会取消正在进行的同步
- 同一时间只有一个同步在运行
- 避免并发写入冲突

---

## 相关文档

- [架构概览](./ARCHITECTURE.md) — 系统整体架构
- [接入指南](./ONBOARDING.md) — 新项目接入步骤
- [安全策略](./SECURITY.md) — 安全防护机制
- [迁移基线](./MIGRATION_BASELINE.md) — 迁移前状态快照
- [迁移报告](./MIGRATION_REPORT.md) — 迁移完成情况
