# 三端同步（GitHub ↔ 本地 ↔ 飞书）

> 用途：把各项目仓库的本地改动统一提交到 GitHub，拉取远端最新，并按需导出飞书数据到本地。
> 任何 Agent 读本文档即可执行，无需额外解释。

## 核心命令

```bash
# 全量同步（pull + push + feishu）
python sync_all.py

# 只拉取远端（GitHub → 本地）
python sync_all.py --pull

# 只提交推送本地改动（本地 → GitHub，含敏感扫描）
python sync_all.py --push

# 只导出飞书数据（飞书 → 本地，缺环境变量自动跳过）
python sync_all.py --feishu

# 先预览不执行（强烈建议先跑）
python sync_all.py --dry-run

# 只处理指定仓库/导出
python sync_all.py --repo ai-resource-hub --repo feishu-data-hub
```

## 行为说明

| 方向 | 机制 | 安全约束 |
|------|------|----------|
| GitHub → 本地 | `git pull --ff-only` | 只快进，绝不 force |
| 本地 → GitHub | `git add -A` + commit + push | 提交前敏感扫描，命中即跳过该仓库 |
| 飞书 → 本地 | 运行 `feishu_exports` 配置的导出命令 | 缺环境变量自动跳过（CI 已托管） |

- 同步结果自动追加到 `sync_log.md`。
- 仓库清单与导出配置在 `sync_config.json`，按需增删。
- `ai-hub-monorepo`（逆天主题单仓）默认 `enabled: false`，需要时手动开启。

## 敏感扫描

提交前对工作区文本文件做正则扫描（`sk-`、`AIza`、`ghp_`、`Bearer`、`app_secret`、
`tenant_access_token`、`cli_`、JWT 等）。命中即跳过该仓库提交并告警，绝不把密钥推上 GitHub。
