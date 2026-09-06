---
service_id: orchestrator
registry_key: orchestrator
role: orchestrator
lifecycle: active
doc_status: active
verified_at: 2026-09-05
---

# orchestrator — 组件编排器

> 运行身份、canonical path、端口与 desired state：`config/gateways.json -> gateways.orchestrator`。
> PID、alive、health、drift：`gateway_runtime.json -> services.orchestrator`。
> 本页不保存第二份运行态。

## 身份

- 服务：orchestrator
- 作用：Agent / 组件编排（canvas_server serve-only）
- 类型：orchestrator
- canonical：`D:\项目\services\orchestrator`（**confirmed**）
- 入口：`canvas_server.py`（启动参数 `--serve-only`）
- 端口：8791
- 配置 ID：`orchestrator`

## 当前状态（以 runtime 为准）

- desired = started
- 2026-09-05 探测：healthy（PID 绑定 8791）

## 关联

- 声明：`ai-hub/config/gateways.json`
- 运行态：`ai-hub/search_gateway/data/gateway_runtime.json`
- 历史：ai-hub 子仓库内 `06_组件编排器/` 为参考副本/旧位，勿与 canonical 混淆。