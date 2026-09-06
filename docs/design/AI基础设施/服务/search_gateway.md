---
service_id: search_gateway
registry_key: search_gateway
role: gateway
lifecycle: active
doc_status: active
verified_at: 2026-09-05
---

# search_gateway — 搜索 / API 转发网关

> 运行身份、canonical path、端口与 desired state：`config/gateways.json -> gateways.search_gateway`。
> PID、alive、health、drift：`gateway_runtime.json -> services.search_gateway`。
> 设计史与建设记录见 `docs/apps/search-gateway/docs/`（详档），本页只做当前事实入口。

## 身份

- 服务：search_gateway
- 作用：Search 网关（3000）+ OpenAI 兼容 API 转发网关（3100）
- 类型：gateway
- canonical：`D:\项目\ai-hub\search_gateway\services`（唯一）
- 配置三拆：`search_gateway/data/model_catalog.json / model_routes.json / channel_registry.json`
- 入口：`search_gateway.py`(:3000) / `api_gateway.py`(:3100)
- 端口：3000（搜索）/ 3100（API 转发）
- 配置 ID：`search_gateway`

## 当前状态（以 runtime 为准）

- desired = **started**（2026-09-05 起常驻）
- 搜索 :3000 已运行：8 引擎（yuanbao/doubao/kimi/qianwen/metaso/grok/perplexity/zai）全 connected。
- API 转发 :3100（`api_gateway.py`）未起；按需启动。
- 2026-09-05 修复：`search_gateway.py` `DATA_DIR` 相对路径错位（曾指向不存在的 `ai-hub\data\search_gateway` 致预检失败），改指向 `ai-hub\search_gateway\data`。

## MCP 接入（供 Agent 调用）

- 标准 MCP server：`D:\项目\ai-hub\search_gateway\mcp\search_mcp_server.py`
- 工具：`search`（多引擎检索，返回结构化正文+来源）/ `aggregate`（搜索→LLM→HTML 报告）/ `health` / `history`
- 接入注册：`...\mcp\mcp_config.json`；说明：`...\mcp\README.md`
- 独立 venv：`...\mcp\.venv`（Python 3.12 + mcp<2 + httpx）
- 前提：本网关 :3000 常驻且引擎会话已登录；多引擎并发时偶发抓取中间态，建议少引擎单跑。

## 设计历史入口

- 详档：`docs/apps/search-gateway/docs/00-search_gateway-总览.md`
- 架构：`.../search_gateway/01-search_gateway-架构与运行.md`
- 配置规范：`.../search_gateway/02-search_gateway-配置与路由规范.md`
- 里程碑：`.../search_gateway/03-search_gateway-建设与演进记录.md`