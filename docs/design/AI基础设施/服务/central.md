---
service_id: central
registry_key: central
role: platform
lifecycle: active
doc_status: active
verified_at: 2026-09-05
---

# central — 中央平台

> 运行身份、canonical path、端口与 desired state：`config/gateways.json -> gateways.central`。
> PID、alive、health、drift：`gateway_runtime.json -> services.central`。
> 本页不保存第二份运行态。

## 身份

- 服务：central
- 作用：中央管理 / 入口平台（dashboard / registry / github / feishu sync）
- 类型：platform
- canonical：`D:\项目\services\central`（**confirmed**）
- 入口：`server.py`
- 端口：8000
- 配置 ID：`central`

## 当前状态（以 runtime 为准）

- desired = started
- 2026-09-05 探测：healthy（PID 绑定 8000）

## 关联

- 声明：`ai-hub/config/gateways.json`
- 运行态：`ai-hub/search_gateway/data/gateway_runtime.json`
- 历史：ai-hub 子仓库内 `00_中央平台/` 为参考副本，勿与 canonical 混淆。设计史见 `ai-hub/ARCHITECTURE.md` 与中央平台相关 ADR。