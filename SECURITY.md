# 安全策略

> **完整安全策略已迁移至 [docs/SECURITY.md](docs/SECURITY.md)。**
>
> 本文件保留简要摘要，完整内容请参阅上述链接。

---

## 公开数据边界

`public/` 目录下的所有内容均为互联网公开数据。只有经过显式审核批准的表、视图、记录和字段才能进入公开输出。

## 三层防护

1. **视图级**：每张导出的表必须有 `AI 公开导出` 视图，无此视图的表不被导出。
2. **字段级**：`fields` 白名单显式列出所有导出字段，禁止通配符 `*`，禁止空数组，禁止敏感字段名（`app_secret`、`tenant_access_token`、`authorization`、`client_secret` 等）。
3. **内容级**：写入时通过 `assertNoSecrets()` 扫描实际凭证值和敏感模式；部署前通过 `security-scan.mjs` 全面扫描所有输出文件。

## GitHub Secrets

| Secret | 用途 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用密钥（绝不记录、绝不写入输出） |
| `FEISHU_BASE_TOKEN` | 单 Base app_token（遗留回退） |
| `FEISHU_BASE_REGISTRY_JSON` | 多 Base 注册表（`{"base-key": {"app_token": "REDACTED"}}`） |

## 绝不进入日志、代码或输出的信息

- `FEISHU_APP_SECRET` 值
- `tenant_access_token` / `user_access_token` 值
- `authorization` 头值
- `client_secret` 值
- GitHub Token 值
- 飞书 `app_token` / `BASE_TOKEN` 值
- 飞书内部 `table_id` 值

## 运行时保障

- `assertNoSecrets()`（`lib/security.mjs`）：每个文件写入前扫描，命中即硬中止
- `security-scan.mjs`：部署前全面扫描，致命错误中止整个部署
- `validate-config.mjs`：同步前配置验证
- `validate-output.mjs`：同步后输出完整性验证

## 安全故障 vs 普通故障

- **安全故障**（检测到凭证/敏感信息）：**中止整个部署**，所有项目不更新
- **普通故障**（网络/API 错误）：仅影响失败项目，其他项目继续

## PR 验证无密钥访问

`validate.yml` 工作流不注入任何 GitHub Secrets，外部贡献者的 PR 不会接触生产密钥。

## 只读快照保证

同步脚本仅执行 GET / list 操作，不执行任何写操作。GitHub Pages 是静态站点，每次部署是不可变快照。

## 事件响应

1. 禁用同步工作流
2. 下线 GitHub Pages
3. 轮换飞书应用密钥
4. 清理受影响的部署和 artifact
5. 审查和修复安全策略
6. 确认扫描通过后恢复

---

**完整详情请参阅 [docs/SECURITY.md](docs/SECURITY.md)。**
