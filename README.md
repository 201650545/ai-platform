# AI 平台（ai-platform）

AI 基建主仓：多网关 API 聚合、AI 搜索、GitHub 管理、飞书集成、Agent 记忆协议、AI 资源运营。
由 4 个旧仓整合而成：`ai-hub`（平台主干）+ `ai-resource-hub`（资源运营）+ `feishu-data-hub`（飞书导出）+ `ai-hub-memory`（记忆协议文档；运行数据仓仍独立）。

> 状态：迁移已完成（2026-09-03）。旧三仓（ai-hub / ai-resource-hub / feishu-data-hub）转入 Archive 冷却期（30-60 天），期满经人工确认后删除。

## 目标结构

```
AI平台/                     ← 本仓（GitHub: ai-platform）
├─ （根）                  ← ai-hub 平台主干原样迁入
├─ resource-ops/           ← ai-resource-hub 迁入
├─ integrations/feishu/    ← feishu-data-hub 迁入
├─ agent/memory/           ← ai-hub-memory 协议文档
└─ docs/migration/         ← 迁移映射表与旧 README 存档
```

## 迁移状态

| 来源仓 | 去向 | 状态 |
|---|---|---|
| ai-hub | （根） | ✅ 已并入 |
| ai-resource-hub | resource-ops/ | ✅ 已并入 |
| feishu-data-hub | integrations/feishu/ | ✅ 已并入 |
| ai-hub-memory（协议部分） | agent/memory/ | ✅ 快照已迁 |
| ai-hub-memory（运行数据） | 原仓保留独立 | ✅ 不迁移 |

## 给 AI / Agent 的读取顺序

1. 本 README → 2. `docs/migration/`（路径映射）→ 3. 对应模块目录内的 README → 4. 需要历史时查旧仓（Archive 冷却期内仍可读）。

## 红线

- 密钥/凭证/个人数据不入仓（沿用旧仓 .gitignore 黑名单，迁移时复核）。
- 旧仓名引用只允许出现在 `docs/migration/` 的映射说明里。
