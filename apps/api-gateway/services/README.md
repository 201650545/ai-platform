# API 转发网关（api-gateway）

不同厂商 API 聚合转发网关，与 AI 搜索网关（`apps/search-gateway`，:3000）**独立平级**。
运行于 **:3100**。

## 入口与端口
- 主入口：`api_gateway.py`（默认 :3100，可用 `API_GATEWAY_PORT` 覆盖；默认只绑 `127.0.0.1`，
  全接口需显式 `API_GATEWAY_ALLOW_WILDCARD=1`，否则 fail closed）
- 启动：PowerShell 窗口内 `.\start_api_gateway_3100.ps1`（WMI 分离父进程，脱钩会话）
- 看门狗：`watchdog_3100_alert.ps1`

## 核心观测 API
- `GET /api/gateway-catalog` 目录；`/api/usage` 用量；`/api/rate-limits` 限流；`/api/route-log` 路由日志；`/api/route-plan` 路径规划；`/api/health` 健康
- OpenAI 兼容：`POST /v1/chat/completions`、`GET /v1/models`

## 配置三拆（`data/model_catalog.json` / `model_routes.json` / `channel_registry.json`）
- `model_catalog.json` = 目录「是什么」：`models→alias→display/billing/tier/use`
- `model_routes.json` = 路由「怎么走」：`routes→alias→primary/backup/fallback_policy/members`
- `channel_registry.json` = 渠道「怎么样」：`channels→id→enabled/credential_status/last_success/quota/health`
- `fallback_policy.enabled` 默认关，备用链须显式声明（ADR-002）

## 数据真源（重要）
本目录为**代码镜像**；网关实际运行时数据（含上述三拆配置、`api_state.json`、`quota.json`、
`route_log.jsonl` 等）在**运行体 `D:\项目\ai-hub\search_gateway\data`**（gitignore 排除，不入库）。
代码目录布局须保持 `services/` 与 `data/` 同级（`channels.DATA_DIR = <上级>/data`）。

## 主题与文档
- 前端控制台：`web/api_page.html`
- 项目专属文档（自包含）：`../docs/api_gateway.md`（服务）、`../docs/主题体系.md`（四主题总览）
- 四主题：`../docs/主题设置-黑白建筑极简.md`（+预览图）、`../docs/主题设置-云海天舟.md`、`../docs/主题设置-星河枢机.md`、`../docs/主题设置-月夜穹顶.md`（+预览图）