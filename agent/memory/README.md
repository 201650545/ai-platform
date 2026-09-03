# agent/memory — Agent 记忆协议（快照）

> 本目录是 `ai-hub-memory` 记忆协议的**文档快照**（2026-09-03 迁移时复制）。
> **运行系统不在本仓**：Agent 记忆的读写脚本与运行数据仍以原仓为唯一运行地：
> - 本地：`D:\ai-hub-memory`（scripts/memory.py 等工具链 + STATE/DECISIONS/inbox 运行数据）
> - GitHub：`201650545/ai-hub-memory`（保持独立仓，未并入 ai-platform）
>
> 在这里写运行状态**无效**——Agent 写记忆请走原仓协议。

## 本目录内容

| 文件 | 说明 |
|---|---|
| AGENTS.md | 记忆协作协议主体（快照自原仓） |
| protocol/Agent记忆上报指令.md | Agent 上报记忆的指令格式 |
| protocol/Agent记忆同步操作文档_memory-sync.md | 记忆同步操作流程 |
| protocol/RULES.md | 全局规则（快照） |
| protocol/SKILL.md | memory-router 技能定义 |

原仓 README（协议入口）全文见 AGENTS.md 快照；协议以原仓最新版为准，本快照可能滞后。

## 协议要点速览（以原仓 AGENTS.md 为准）

- 多 Agent 共享记忆：GitHub 仓为唯一记忆真源，projects/<项目ID>/ 分层（STATE 当前状态 / DECISIONS 决策 / CHANGELOG 流水 / MEMORY 索引）
- 操作纪律：memory.py 先 pull 后写；STATE ≤ 8 条活动项；archive 同日不可改（修错另建 _r2）；多 Agent 并发写走 coordination/ 锁
- 全局层：global/（RULES=宪法 / PROJECTS=项目地图 / DECISIONS / TOOLS）
