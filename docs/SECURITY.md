# 安全策略

本文档定义 Feishu Data Hub 的安全策略，包括公开数据边界、三层防护机制、密钥管理、运行时保障和事件响应流程。

本文档是仓库的**权威安全策略文档**，根目录 `SECURITY.md` 已重定向至此。

---

## 1. 公开数据边界

**`public/` 目录下的所有内容均为互联网公开数据。**

这意味着：
- 任何写入 `public/` 的文件都会被部署到 GitHub Pages，任何人都可以访问
- 任何出现在 `public/` 中的信息都视为已公开泄露
- 因此，安全策略的核心目标是：**确保只有经过显式审核批准的数据才能进入 `public/`**

公开数据包括：
- `public/catalog.json` — 全局项目目录
- `public/index.html` — Hub 首页
- `public/projects/<slug>/` — 各项目输出（manifest、schema、records、fields、status、summary、index）
- `public/data/` — 遗留兼容路径（`learning-english` 项目的镜像）
- `public/catalog-versioned/` — 版本化 catalog

**绝不公开**的数据：
- 飞书应用密钥（`app_secret`）
- 飞书访问令牌（`tenant_access_token`、`user_access_token`）
- 飞书 Base 标识（`app_token` / `BASE_TOKEN`）
- 飞书内部表标识（`table_id`）
- GitHub Token
- 任何 HTTP Authorization 头的值
- `.env` 文件及环境变量值

---

## 2. 三层防护机制

Data Hub 采用三层纵深防御，确保敏感数据不会进入公开输出。

### 2.1 第一层：视图级防护

**每张需要导出的表必须有一个名为 `AI 公开导出` 的表格视图。**

- 同步脚本仅读取 `AI 公开导出` 视图中的记录
- 没有此视图的表不会被导出（`require_export_view: true`）
- 视图名称必须精确匹配 `AI 公开导出`（含空格，区分大小写）
- 不接受任何其他视图名称作为替代
- 飞书 Base 所有者可以在视图中隐藏不需要公开的列（额外安全层）

**实现位置**：`lib/feishu.mjs` 的 `listRecords()` 仅传入 `view_id`；`scripts/sync-project.mjs` 通过 `exactOne()` 精确匹配视图名称。

### 2.2 第二层：字段级防护

**字段白名单是显式的、穷举的，禁止通配符。**

- 每个项目的 YAML 配置中，每张表的 `fields` 数组必须显式列出所有要导出的字段名
- **禁止使用通配符 `*`**（配置验证时即拒绝）
- **禁止空数组**（配置验证时即拒绝）
- **禁止包含敏感字段名**：`app_secret`、`tenant_access_token`、`user_access_token`、`authorization`、`client_secret`、`github_token`、`cookie`
- **禁止字段名重复**（配置验证时即拒绝）
- 同步时，`selectRecord()` 仅从原始记录中选取白名单字段，其他字段一律丢弃

**实现位置**：`lib/config.mjs` 的 `loadProjectConfig()` 在加载时验证；`lib/transform.mjs` 的 `selectRecord()` 在运行时过滤。

### 2.3 第三层：内容级防护

**对所有输出文件进行模式扫描，检测敏感信息泄露。**

在两个阶段执行内容扫描：

**阶段 A — 写入时扫描（`lib/security.mjs` 的 `assertNoSecrets()`）**：
- 每个文件写入磁盘前，对序列化后的字符串进行扫描
- 检查是否包含实际凭证值（`app_secret`、`app_token`、`tenant_access_token` 的真实值）
- 检查是否匹配敏感信息模式（`SECRET_PATTERNS`）
- 命中即抛错，**硬中止**，该文件不会被写入

**阶段 B — 部署前扫描（`scripts/security-scan.mjs`）**：
- 同步完成后、部署前，对 `public/` 目录下所有文件进行全面扫描
- 检查项（**致命错误，中止部署**）：
  - 禁止文件（`.env`、`debug-response.json`、`api-cache.json` 等）
  - 敏感信息模式（`app_secret`、`tenant_access_token`、`authorization`、`client_secret`、`github_token`、`bearer`、私钥头）
  - Token 前缀（`cli_`、`t-`、`u-`、`Bearer `、`ghp_`、`gho_`、`ghs_`、`ghr_`）
  - 内部 Feishu 标识符（`table_id` 前缀 `tbl`、`app_token` JSON 键值对）
- 检查项（**警告，不中止**）：
  - PII 疑似（手机号、身份证号、邮箱、银行卡号）
  - 高熵字符串（Shannon 熵 > 4.0 的 Base64/Hex 序列）

**实现位置**：`lib/security.mjs`（扫描工具）、`lib/output.mjs` 的 `writeJson()`/`writeText()`（写入时调用）、`scripts/security-scan.mjs`（部署前全面扫描）。

---

## 3. GitHub Secrets

生产环境密钥存储在 GitHub Secrets 中，仅在 Actions 运行时通过环境变量注入，绝不记录在日志或输出中。

| Secret 名称 | 用途 | 敏感等级 |
|---|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID | 中（非密钥，但不应公开） |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | **极高** |
| `FEISHU_BASE_TOKEN` | 单 Base 的 app_token（遗留回退） | **高** |
| `FEISHU_BASE_REGISTRY_JSON` | 多 Base 注册表（含多个 app_token） | **极高** |
| `FEISHU_PUBLIC_APP_ID` | 飞书应用 ID（新架构主用） | 中 |
| `FEISHU_PUBLIC_APP_SECRET` | 飞书应用密钥（新架构主用） | **极高** |

**Secret 管理原则**：
- Secret 值绝不写入代码、配置文件、文档或注释
- Secret 值绝不记录在日志中（`lib/feishu.mjs` 的 API 请求永不记录 token 或密钥）
- Secret 值绝不写入输出文件（`assertNoSecrets()` 在写入前检查实际凭证值）
- `FEISHU_BASE_REGISTRY_JSON` 中的 `app_token` 值在本文档中以 `REDACTED` 表示

---

## 4. 绝不进入日志、代码或输出的信息

以下信息**绝不**允许出现在任何日志输出、源代码、配置文件或公开输出中：

| 信息 | 说明 |
|---|---|
| `FEISHU_APP_SECRET` 的值 | 飞书应用密钥 |
| `tenant_access_token` 的值 | 飞书租户访问令牌 |
| `user_access_token` 的值 | 飞书用户访问令牌 |
| `authorization` 头的值 | HTTP 认证头 |
| `client_secret` 的值 | 客户端密钥 |
| GitHub Token 的值 | `ghp_`、`gho_`、`ghs_`、`ghr_` 前缀的 token |
| `app_token` / `BASE_TOKEN` 的值 | 飞书 Base 的唯一标识 |
| `table_id` 的值 | 飞书内部表标识（`tbl` 前缀） |
| `.env` 文件内容 | 环境变量文件 |
| API 响应缓存 | `debug-response.json`、`api-cache.json`、`raw-response.json` |

**日志安全**：`lib/feishu.mjs` 中的 `apiRequest()` 函数在所有错误处理路径中均不输出 token 或密钥值。错误消息仅包含 HTTP 状态码、飞书 API 错误码和 `request_id`。

---

## 5. 运行时保障

### 5.1 assertNoSecrets()（lib/security.mjs）

`assertNoSecrets()` 是写入时的安全门卫，在 `lib/output.mjs` 的 `writeJson()` 和 `writeText()` 中被调用：

```javascript
export function assertNoSecrets(serialized, secretValues = [], context = "输出") {
  // 检查实际凭证值
  for (const v of secretValues) {
    if (v && serialized.includes(v)) {
      throw new Error(`检测到实际凭证值即将进入${context}，已中止部署`);
    }
  }
  // 检查敏感信息模式
  for (const p of SECRET_PATTERNS) {
    if (p.test(serialized)) {
      throw new Error(`检测到疑似敏感信息模式（${context}）：${p.source}`);
    }
  }
}
```

**`secretValues` 包含**：`appSecret`、`appToken`、`tenantToken`（在 `sync-project.mjs` 中收集）。

这意味着：即使飞书 API 返回的记录中意外包含了真实的密钥值，`assertNoSecrets()` 也会在写入磁盘前拦截。

### 5.2 security-scan.mjs（部署前全面扫描）

`scripts/security-scan.mjs` 在同步完成后、部署前运行，扫描 `public/` 目录下所有文件：

- **遍历所有文件**：递归遍历 `public/` 目录
- **禁止文件检查**：检测 `.env`、`debug-response.json`、`api-cache.json`、`raw-response.json`、`.npmrc`、`.netrc` 等文件
- **敏感信息模式**：检测 `app_secret`、`tenant_access_token`、`user_access_token`、`authorization`、`client_secret`、`github_token`、`bearer`、私钥头等模式
- **Token 前缀**：检测 `cli_`、`t-`、`u-`、`Bearer `、`ghp_`、`gho_`、`ghs_`、`ghr_` 等 token 前缀
- **内部标识符**：检测 `tbl` 前缀的 table_id、JSON 格式的 app_token
- **PII 疑似**（警告）：手机号、身份证号、邮箱、银行卡号
- **高熵字符串**（警告）：Shannon 熵 > 4.0 的长字符串

任何致命错误都会使扫描脚本以非零退出码结束，GitHub Actions 的部署步骤不会执行。

### 5.3 配置验证（validate-config.mjs）

`scripts/validate-config.mjs` 在同步前运行，验证所有配置文件：
- hub.yaml 结构完整性
- credential-profiles.yaml 结构完整性
- 各项目 YAML 的 slug 合法性和唯一性
- 字段白名单不含禁止字段名
- 字段白名单不含通配符 `*`
- 字段白名单不为空
- 字段白名单无重复项
- 项目引用的 credential_profile 存在

### 5.4 输出验证（validate-output.mjs）

`scripts/validate-output.mjs` 在同步后运行，验证公开输出完整性：
- catalog.json 结构和版本
- 各项目 manifest.json、schema.json、status.json、summary.md、index.html 存在且合法
- fields.json 和 records 文件的 SHA-256 校验和与 manifest 中记录的一致
- 记录数与 manifest 中记录的一致
- 无重复 record_id
- 关联字段的目标 slug 在已知表中
- 遗留兼容路径（data/manifest.json、data/schema.json）验证

---

## 6. 安全故障 vs 普通故障

### 安全故障 — 中止整个部署

**触发条件**：`sync-project.mjs` 抛出的错误消息包含安全相关关键词（`凭证值`、`敏感信息`、`secret`、`token`、`authorization`、`private key`、`cookie`、`app_secret`、`bearer`）。

**处理方式**：
1. `sync-hub.mjs` 收集所有安全错误
2. **立即中止整个部署**：`process.exit(1)`
3. GitHub Actions 构建任务失败，deploy job 不执行
4. **所有项目都不会更新**（即使是成功同步的项目）
5. 已有 Pages 部署保持不变（直到下一次成功同步）

**设计理由**：安全是最高优先级。一旦检测到潜在密钥泄露，宁可停止全部部署，也不冒风险更新任何数据。

### 普通故障 — 仅影响该失败项目

**触发条件**：网络超时、API 错误、字段缺失、视图缺失等非安全类错误。

**处理方式**：
1. 该项目标记为 `failed`
2. 尝试恢复上一次成功版本（`hydrate-existing-project.mjs`）
3. **其他项目继续同步和部署**
4. 失败项目在 catalog 中以 `stale` 状态出现

**设计理由**：普通故障是临时性的，不应影响其他项目的正常更新。

---

## 7. PR 验证工作流无密钥访问

`validate.yml` 工作流在 PR 和 push 时运行，**不注入任何 GitHub Secrets**：

```yaml
# validate.yml 的 jobs 中没有 env 注入 FEISHU_* 密钥
jobs:
  validate:
    steps:
      - name: Static syntax check
        run: npm run check
      - name: Validate configuration
        run: npm run validate:config
```

**安全意义**：
- 外部贡献者提交的 PR 不会接触生产密钥
- PR 验证仅检查代码语法和配置结构
- 只有 merge 到 main 后的定时/手动同步工作流才会注入密钥并执行实际同步
- 防止恶意 PR 通过日志窃取密钥

---

## 8. 只读快照保证

Data Hub 对飞书 Base 的访问是**严格只读**的：

- **同步脚本只执行 GET / list 操作**：`listTables`、`listViews`、`listFields`、`listRecords`
- **不执行任何写操作**：不创建、不修改、不删除飞书 Base 中的任何数据
- **飞书应用权限为只读**：`bitable:app:readonly`
- **GitHub Pages 是静态站点**：无后端、无数据库、无用户输入
- **每次部署是不可变快照**：直到下一次同步运行前，Pages 内容不变
- **同步频率由 GitHub Actions cron 控制**：每小时或每天自动刷新

---

## 9. 事件响应

如果发现密钥或私有字段被暴露在公开输出中：

### 步骤 1：立即停止同步

1. 进入 GitHub 仓库 **Actions** 页面
2. 禁用 **Hourly Sync** 和 **Daily Sync** 工作流
3. 阻止下一次自动同步覆盖证据

### 步骤 2：下线 GitHub Pages

1. 进入仓库 **Settings → Pages**
2. 暂停或删除 Pages 部署
3. 确认公开 URL 不再可访问

### 步骤 3：轮换飞书应用密钥

1. 进入飞书开放平台 → 应用管理
2. 重新生成 `App Secret`
3. 更新 GitHub Secrets 中的 `FEISHU_APP_SECRET`（和 `FEISHU_PUBLIC_APP_SECRET`）
4. 如果 `app_token` 也被泄露，需要重建飞书 Base 并获取新的 app_token

### 步骤 4：清理受影响的部署

1. 删除受影响的 GitHub Pages 部署和 artifact
2. 检查 Git 历史中是否包含敏感信息（若有，需要清理 Git 历史）
3. 检查 GitHub Actions 运行日志中是否泄露了密钥

### 步骤 5：审查和修复

1. 审查 `lib/security.mjs` 的扫描模式是否需要更新
2. 审查项目 YAML 的字段白名单是否需要收紧
3. 审查飞书 Base 中的 `AI 公开导出` 视图是否泄露了不应公开的字段
4. 审查 `assertNoSecrets()` 的 `secretValues` 列表是否完整

### 步骤 6：恢复

1. 确认安全扫描和输出验证均通过
2. 重新启用 GitHub Pages
3. 重新启用定时同步工作流
4. 监控首次同步结果，确认无安全告警

---

## 10. 安全扫描模式参考

### SECRET_PATTERNS（致命）

```javascript
/"app_secret"\s*:\s*"[^"]{10,}"/i
/"tenant_access_token"\s*:\s*"[^"]{10,}"/i
/"user_access_token"\s*:\s*"[^"]{10,}"/i
/"authorization"\s*:\s*"[^"]{10,}"/i
/"client_secret"\s*:\s*"[^"]{10,}"/i
/"github_token"\s*:\s*"[^"]{10,}"/i
/\bbearer\s+[a-z0-9_-]{20,}\b/i
/-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/i
```

### PII_PATTERNS（警告）

```javascript
/\b1[3-9]\d{9}\b/g                          // 中国手机号
/\b\d{17}[\dXx]\b/g                         // 中国身份证号（18位）
/\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/gi  // 邮箱
/\b\d{16,19}\b/g                            // 银行卡号
```

### Token 前缀检测（致命）

```javascript
cli_    // 飞书应用 ID 前缀
t-      // 飞书 tenant_access_token 前缀
u-      // 飞书 user_access_token 前缀
Bearer  // HTTP Bearer 认证
ghp_    // GitHub Personal Access Token
gho_    // GitHub OAuth Token
ghs_    // GitHub Server Token
ghr_    // GitHub Refresh Token
```

### 内部标识符检测（致命）

```javascript
/\btbl[A-Za-z0-9]{6,}\b/g           // 飞书 table_id
/"app_token"\s*:\s*"[^"]{15,}"/i    // 飞书 app_token
```

### 禁止文件列表（致命）

```
.env, .env.local, .env.production
debug-response.json, api-cache.json, raw-response.json
.npmrc, .netrc
```

---

## 相关文档

- [架构概览](./ARCHITECTURE.md) — 故障隔离机制
- [接入指南](./ONBOARDING.md) — 字段白名单配置
- [运维手册](./OPERATIONS.md) — 安全扫描故障排查
- [迁移基线](./MIGRATION_BASELINE.md) — 迁移前安全策略
