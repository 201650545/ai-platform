# AI Hub 拓扑（仓库结构与数据流）

> 更新：2026-08-10（P4-1 补齐三仓库关系与 CI 工作流拓扑）
> 初建：P2-3 飞书双写分工固化

## 三仓库关系

| 仓库 | GitHub | 本地唯一真源 | 职责 |
|---|---|---|---|
| **ETP** english-teaching-production | 201650545/english-teaching-production（私有） | `D:\英语教学` | 英语教学**规范/工具/命令/汇报镜像**（非成品库）。发布：`publish_all.py` 一键双发 → GitHub + 飞书看板 |
| **HUB** ai-hub | 201650545/ai-platform | `D:\项目\ai-hub` | AI 聚合管理平台。中央平台 `00_中央平台/`（:8000）；网关子项目 `search_gateway/`（:3000 搜索 / :3100 API 转发）；组件编排器 `06_组件编排器/` |
| **FDH** feishu-data-hub | 201650545/feishu-data-hub | `D:\feishu-learning-english-export` | 飞书多维表格数据导出 Hub。定时同步 → GitHub Pages |

> 说明：2026-09-03 起 Work 库内将 ai-hub + ai-resource-hub + feishu-data-hub 整合为 **ai-platform**；本工程目录仍为 `D:\项目\ai-hub`，网关子项目 `search_gateway` 已迁入本目录（`services/` + `data/`）。已废弃旧的「D:\游戏\ds_v4_cli 独立运行网关」描述。

## CI 工作流拓扑

| 仓库 | 工作流 | 触发 | 校验内容 |
|---|---|---|---|
| ETP | `.github/workflows/verify.yml` | push / PR | `validate_banks.py`（题库 Schema）+ `validate_content.py`（内容 JSON 有效性） |
| HUB | `.github/workflows/test.yml` | push / PR | `tests/run_all.py`（依赖缺失的网关时代套件 SKIP） |
| FDH | `sync-daily.yml` / `sync-hourly.yml` | schedule / manual | 同步飞书 → validate → security scan → GitHub Pages；**P3-2 防噪音**：内容无实质变化时跳过部署 |
| FDH | `sync-manual.yml` | manual | 手动同步（始终部署） |
| FDH | `validate.yml` | push / PR | 校验 + 安全扫描 |

## 飞书双写分工（P2-3 结论）

ETP 与 HUB 两份 feishu_sync 写入**不同的飞书 Base / 表，无交集**，不存在双写冲突：

| 脚本 | 仓库 | 写入 Base | 写入表 | 独占声明 |
|---|---|---|---|---|
| `00_工具/ops/feishu_sync.py` | ETP | 英语教学流水线 | 课程进度看板 `tblDQL47cLPeDkqg` | 文件头已加 ✅ |
| `00_中央平台/feishu_sync.py` | HUB | AI Hub 网关数据 | gateways / api_channels / conversations / daily_stats | 文件头已加 ✅ |

分工规则：**ETP 侧只写「课程进度看板」；HUB 侧只写「AI Hub 网关 4 表」**。
任一脚本不得写对方 Base。

## 网关拓扑（P2-1 结论）

AI Hub 网关能力由**仓内子项目 search_gateway** 提供，工程位置 `search_gateway/`：
- `services/` — 代码（api_gateway.py :3100 API 转发 / search_gateway.py :3000 搜索）
- `data/` — 配置与运行数据（含三拆：model_catalog.json / model_routes.json / channel_registry.json）

旧的「网关三件套删除 / Cherry Studio 提供 / D:\游戏\ds_v4_cli 独立运行」为历史状态，已废弃。
未知细节见 Work 库 `AI平台/docs/04-建设与演进/search_gateway/`。

<!-- P4-1 完成：三仓库关系、CI 拓扑、双写分工、网关拓扑均已固化 -->
