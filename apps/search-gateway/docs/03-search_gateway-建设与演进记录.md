---
id: search_gateway-03
type: changelog
project: ai-platform
component: search_gateway
---

# 03 · search_gateway 建设与演进记录

> 长期 CHANGELOG，只记重大工程演进；不记录日常函数级改动。

## 2026-09

### 迁入 ai-platform

状态：完成

变化：
- search_gateway 从旧目录迁入 AI 工程主目录
- `services/` 与 `data/` 已迁入
- 子项目归属正式调整为 ai-platform
- 全部相关路径配置已改（启动脚本 / 看门狗 / 计划任务 / 全局启动）

影响：
- 项目索引由独立工程视角调整为 ai-platform 子项目视角
- 新人工任务卡回归 Work 库，停止工程库任务卡双写（自本项目始）

决策：
`ADR/ADR-001-迁入-ai-platform-作为子项目`

执行：
`../../docs/work/task-cards/search-gateway/SG-001-迁入-ai-platform-主工程`

---

### 配置三拆与路由机制重构

状态：完成

变化：
- 新增 `model_catalog.json`（产品目录 / alias）
- 新增 `model_routes.json`（primary / backup / fallback）
- 新增 `channel_registry.json`（渠道状态）
- 新增 `catalog_routes.py`（三拆加载 / 解析 / 路由逻辑）
- 默认策略调整为单渠道单模型
- fallback 改为显式备用链（`fallback_policy.enabled=false` 默认）
- 旧多渠道智能轮动机制进入废弃路径

决策：
`ADR/ADR-002-配置三拆与显式备用链`

执行：
`../../docs/work/task-cards/search-gateway/SG-002-配置三拆与路由机制重构`

---

### 网关登记与三拆端点接入

状态：完成

变化：
- `config/gateways.json` 新增 search_gateway 网关 entry
- `TOPOLOGY.md` 网关拓扑更新为仓内子项目视图
- `api_gateway.py` 接入 `catalog_routes`，新增 `GET /api/gateway-catalog` 只读汇总端点
- 冒烟验证通过（3100 监听 / healthz 200 / /api/models 200 / /api/gateway-catalog 200）

决策：
`ADR/ADR-002-配置三拆与显式备用链`

执行：
`../../docs/work/task-cards/search-gateway/SG-003-网关登记与冒烟验证`