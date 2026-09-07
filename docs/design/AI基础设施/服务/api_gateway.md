---
service_id: api_gateway
port: 3100
role: gateway
lifecycle: active
doc_status: active
---

# api_gateway — API 转发网关

> API 转发网关，OpenAI 兼容 LLM 聚合转发。监听 :3100，常驻服务本体为 `api_gateway.py`。
> 仓库内为**独立平级应用** `apps/api-gateway/`，与搜索网关应用 `apps/search-gateway`(:3000) 同级；
> 配置三拆（model_catalog / model_routes / channel_registry）位于 `data/`（真源在运行体 `D:\项目\ai-hub\search_gateway\data`，gitignore 不入库）。

## 身份

- 服务：api_gateway
- 作用：API 转发网关（OpenAI 兼容 LLM 聚合转发）
- 端口：3100
- 仓库应用：`apps/api-gateway/`（与 `apps/search-gateway`(:3000) 平级；运行体二者仍共用 `D:\项目\ai-hub\search_gateway\services` + `data`）
- 入口：`apps/api-gateway/services/api_gateway.py`
- 前端控制台：`apps/api-gateway/services/web/api_page.html`（已启用 鉴权 + 多主题机制）

## 前端主题

- 主题设置（玄白·黑白建筑极简 / MONO）：`服务/主题设置.md`（预览图 `服务/玄白_MONO_GATEWAY_预览图.png`）