---
service_id: ds_v4_cli
registry_key: ds_v4_cli
role: cli
lifecycle: retired
doc_status: active
verified_at: 2026-09-05
---

# ds_v4_cli — 智能聚合 CLI 网关（retired / 已删除）

> 运行身份、canonical path、desired state：`config/gateways.json -> gateways.ds_v4_cli`。
> 旧 DeepSeek 聚合网关，功能与 `search_gateway` 重叠，已在 2026-09-05 备份后删除。

## 身份

- 服务：ds_v4_cli
- 作用：AI 搜索 + LLM 聚合 CLI 网关
- 类型：cli（一次性命令，无常驻端口）
- lifecycle：**retired**（已删除，仅历史归档）
- 备份：`D:\项目\_backup\ds_v4_cli_20260905_191509.zip`（压缩前目录大小 0.47MB / 50 文件）
- 配置 ID：`ds_v4_cli`（gateways.json 中 `lifecycle=retired`）

## 历史

- 曾位于 `D:\游戏\ds_v4_cli`（独立于 ai-hub）。
- 曾标记 **legacy**，与 `search_gateway`（3100 转发 / 3000 搜索）功能重叠。
- 2026-09-05 经确认由 `search_gateway` 完全覆盖后，压缩备份到 `D:\项目\_backup\` 并删除源目录。

## 当前状态

- desired = stopped（无实例）
- canonical 指向备份包；不再启动，不在维护。