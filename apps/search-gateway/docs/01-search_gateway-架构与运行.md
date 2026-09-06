---
id: search_gateway-01
type: architecture
project: ai-platform
component: search_gateway
status: active
---

# 01 · search_gateway 架构与运行

> 本文件回答"search_gateway 怎么跑"。**已确认事实写死；未核实细节标"待核实"，不要猜。**

## A. 端口拓扑

| 端口 | 职责 | 协议 | 说明 |
|---|---|---|---|
| 3100 | OpenAI 兼容 API 转发网关 | HTTP | 网关对外服务入口（已确认） |
| 3000 | 搜索网关 | HTTP | 另一套搜索服务，含历史记录（已确认） |

待核实项：3100 的具体入口进程、上游调用方、暴露范围；3000 的进程入口与下游。以实际启动代码 / 配置为准。

## B. 模块边界

```text
search_gateway/
├─ services/                  # 可执行代码
│  ├─ api_gateway.py          # OpenAI 兼容 API 入口（含路由端点）
│  ├─ channels.py             # 渠道配置与路由逻辑（数据目录 at .../data）
│  ├─ catalog_routes.py       # catalog + route 三拆加载/解析
│  ├─ capabilities.py         # 模型能力
│  ├─ resource_config.py      # 资源配置
│  ├─ quota.py / rate_limit.py / history.py
│  └─ ...（其余模块见工程源码）
└─ data/                      # 配置与运行数据
   ├─ model_catalog.json
   ├─ model_routes.json
   ├─ channel_registry.json
   ├─ channels.json / routing.json / channel_models.json  # 历史/既有配置
   ├─ model_capabilities.json
   └─ ...（运行态：quota / history / control_plane ...）
```

## C. 目标请求流

> 此图表达目标架构关系；实际函数调用链以代码为准。

```text
Client
  ↓
OpenAI Compatible API (:3100)
  ↓
模型名称 / alias 解析
  ↓
model_catalog
  ↓
model_routes
  ↓
primary channel
  ↓ 失败时仅按显式配置
backup / fallback
  ↓
channel_registry 中的渠道状态
  ↓
上游模型渠道
  ↓
Response
```

## D. 故障流

- **primary 不可用怎么办**：仅按 `model_routes.json` 中显式声明的 backup / fallback 处理。
- **backup 在哪里定义**：`model_routes.json` 的 `backup[]`。
- **fallback 什么时候触发**：仅当 `fallback_policy.enabled=true` 且命中 `trigger`（如 5xx / timeout）时。
- **没有备用链时怎么办**：直接返回上游错误，不做隐式换渠道。
- **health / quota 是否允许影响执行**：以 `channel_registry.json` 现实状态为准；渠道 disabled / quota exhausted 时行为应符合设计，不做未声明接管。

## E. 运行验证

上线 / 变更后检查：

- [ ] 3100 / 3000 是否监听
- [ ] OpenAI compatible endpoint 是否返回
- [ ] alias 能否解析
- [ ] primary 是否命中预期渠道
- [ ] primary 失败后是否只进入声明的 backup / fallback
- [ ] 不存在隐式随机 / 轮动渠道
- [ ] channel disabled / quota exhausted 时行为是否符合设计