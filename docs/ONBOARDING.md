# 新项目接入指南

本文档提供将一个新的飞书 Base 接入 Feishu Data Hub 的完整步骤，以及 AI 代理（Agent）协作时的修改权限边界。

---

## 1. 接入工作流概览

将一个新的飞书 Base 接入 Data Hub 需要以下 8 个步骤：

```
① 创建 "AI 公开导出" 视图
② 给统一飞书应用授予只读权限
③ 更新 FEISHU_BASE_REGISTRY_JSON Secret
④ 添加项目 YAML 配置（npm run project:add）
⑤ Dry-run 同步验证
⑥ 安全扫描
⑦ 手动部署验证
⑧ 启用定时同步
```

---

## 2. 详细步骤

### 步骤 1：创建 "AI 公开导出" 视图

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

### 步骤 2：给统一飞书应用授予只读权限

将 Data Hub 使用的飞书应用添加为目标 Base 的协作者，授予只读权限。

1. 在飞书 Base 中打开 **设置** → **协作者管理**（或 **添加协作者**）
2. 搜索并添加 Data Hub 使用的飞书应用
3. 权限设为 **只读**（可查看）
4. 确认应用可以看到所有需要导出的表

**安全要求**：
- 只授予只读权限，绝不授予编辑权限
- 应用权限范围已在 `credential-profiles.yaml` 中定义为 `bitable:app:readonly` 和 `bitable:app`
- 多个 Base 共用同一个飞书应用，通过 `FEISHU_BASE_REGISTRY_JSON` 中的 `app_token` 区分

### 步骤 3：更新 FEISHU_BASE_REGISTRY_JSON Secret

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

### 步骤 4：添加项目 YAML 配置

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

### 步骤 5：Dry-run 同步验证

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

### 步骤 6：安全扫描

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

### 步骤 7：手动部署验证

同步成功后，验证部署结果。

1. 等待 GitHub Actions 运行完成（build + deploy 两个 job 均为绿色）
2. 访问以下 URL 确认新项目已出现：

```
https://201650545.github.io/feishu-learning-english-export/catalog.json
```

确认 `projects` 数组中包含新项目条目，且 `sync_status: "ok"`、`is_stale: false`。

3. 访问项目级入口确认数据正确：

```
https://201650545.github.io/feishu-learning-english-export/projects/<slug>/manifest.json
https://201650545.github.io/feishu-learning-english-export/projects/<slug>/index.html
https://201650545.github.io/feishu-learning-english-export/projects/<slug>/status.json
```

4. 检查各表的 `record_count` 和 `field_count` 是否符合预期
5. 检查 `status.json` 中的 `sync_status` 是否为 `ok`

### 步骤 8：启用定时同步

确认手动同步无误后，项目将自动参与定时同步。

- 若 `schedule.tier: hourly`：每小时第 17 分钟由 `sync-hourly.yml` 自动同步
- 若 `schedule.tier: daily`：每天 03:17 UTC 由 `sync-daily.yml` 自动同步

无需额外配置，定时工作流会自动发现并同步所有 enabled 的项目。

---

## 3. 接入检查清单

完成接入后，逐项确认：

- [ ] 飞书 Base 中每张需要导出的表都有 `AI 公开导出` 视图
- [ ] 飞书应用已添加为 Base 协作者，权限为只读
- [ ] `FEISHU_BASE_REGISTRY_JSON` 中已添加新项目的 `app_token` 条目
- [ ] `config/projects/<slug>.yaml` 已创建，slug、title、base_key 配置正确
- [ ] `config/projects/<slug>.yaml` 中 `tables` 已显式配置字段白名单（非自动发现）
- [ ] `schedule.tier` 设置为合适的同步频率
- [ ] Dry-run 同步通过，无报错
- [ ] 实际同步通过，安全扫描无致命错误
- [ ] `catalog.json` 中新项目 `sync_status: "ok"`
- [ ] 项目级 `manifest.json`、`schema.json`、`status.json` 可正常访问
- [ ] 各表 `record_count` 和 `field_count` 符合预期

---

## 4. AI 代理协作权限边界

当使用 AI 代理（Agent）协助接入新项目时，必须遵守以下权限边界。

### 4.1 代理可以修改的文件

| 文件/目录 | 说明 |
|---|---|
| `config/projects/<own-slug>.yaml` | 仅限代理正在接入的自身项目的配置文件 |
| `config/projects/<own-slug>.summary.md` | 仅限自身项目的摘要模板 |
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
| `scripts/hydrate-existing-project.mjs` | 故障恢复脚本 | 影响所有项目 |
| `scripts/add-project.mjs` | 脚手架脚本 | 影响所有项目 |
| `lib/*.mjs` | 所有共享库模块 | 影响所有项目 |
| `public/` 相关的工作流 | `.github/workflows/sync-*.yml` | 部署核心 |
| `config/hub.yaml` | Hub 全局配置 | 影响所有项目 |
| `config/credential-profiles.yaml` | 凭据配置 | 安全核心 |
| `config/projects/learning-english.yaml` | 英语学习项目配置 | 其他项目 |
| `config/projects/<other-slug>.yaml` | 其他项目的配置 | 其他项目 |
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

---

## 相关文档

- [架构概览](./ARCHITECTURE.md) — 系统整体架构
- [运维手册](./OPERATIONS.md) — 日常运维操作
- [安全策略](./SECURITY.md) — 公开数据安全策略
