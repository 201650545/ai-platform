---
id: search_gateway-00
type: subproject
project: ai-platform
component: search_gateway
status: active
tech_stack:
  - Python
ports:
  - 3000
  - 3100
source_of_truth: Obsidian
created: 2026-09-05
---

# search_gateway

## 1. 定位

- 服务名：search_gateway
- 类型：OpenAI 兼容 API 转发网关
- 作用：多渠道模型聚合与转发
- 所属：ai-platform
- 项目形态：仓内子项目
- 技术栈：Python

## 2. 当前目录形态

```text
search_gateway/           # 工程位置：D:\项目\ai-hub\search_gateway
├─ services/              # 代码（api_gateway.py / channels.py / catalog_routes.py ...）
└─ data/                  # 配置与运行数据（model_catalog.json / model_routes.json / channel_registry.json ...）
```

## 3. 当前架构状态

目标架构：

- 默认单渠道单模型
- 显式 primary / backup / fallback
- 禁止依赖隐式智能轮动（旧机制已废弃）

配置三拆：

- `model_catalog.json` —— 产品目录 / alias / 展示
- `model_routes.json` —— primary / backup / fallback 路由
- `channel_registry.json` —— 渠道 credential 引用 / quota / health

相关实现：`catalog_routes.py`

## 4. 服务入口与端口（已确认事实）

| 端口 | 职责 | 说明 |
|---|---|---|
| 3100 | OpenAI 兼容 API 转发网关 | 网关对外服务入口 |
| 3000 | 搜索网关 | 另一套搜索服务（含历史记录） |

未核实的进程入口、调用链、暴露范围等细节见 `01-search_gateway-架构与运行.md`（标"待核实"处）。

## 5. Agent 阅读顺序

Agent 或维护者修改 search_gateway 前按顺序阅读：

1. 本文
2. `02-search_gateway-配置与路由规范.md`
3. `ADR/ADR-002-配置三拆与显式备用链.md`
4. `ADR/ADR-003-统一模型名聚合同模多渠道成员池.md`
5. 当前相关任务卡
6. 对应代码

涉及运行拓扑时追加：
`01-search_gateway-架构与运行.md`

涉及历史问题时追加：
`03-search_gateway-建设与演进记录.md`

## 6. 关键决策（ADR）

- `ADR/ADR-001-迁入-ai-platform-作为子项目`
- `ADR/ADR-002-配置三拆与显式备用链`
- `ADR/ADR-003-统一模型名聚合同模多渠道成员池`

## 7. 当前任务

参见：`docs/01-任务看板.md`（search_gateway 区域）+ `docs/docs/work/task-cards/search-gateway/`

## 8. Agent 执行约定

1. 修改 search_gateway 前，必须先读取本总览和相关 ADR。
2. 任何改变路由语义的修改，都必须检查是否需要新增/更新 ADR。
3. 任务状态只能更新任务卡 / 任务看板，不把进行中状态写进架构规范。
4. Obsidian 是知识真源；GitHub 文档仅作为发布镜像，不从 GitHub 反向覆盖 Obsidian。
5. 文档中的"当前状态 / 目标状态 / 历史状态"必须明确区分，不得混写。