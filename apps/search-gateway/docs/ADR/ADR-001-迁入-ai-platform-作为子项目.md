---
id: ADR-001
project: ai-platform
component: search_gateway
status: Accepted
date: 2026-09-05
---

# ADR-001：search_gateway 迁入 ai-platform 作为子项目

## 状态

Accepted

## 日期

2026-09-05

## 背景

原 search_gateway（API 转发网关）位于独立旧目录。2026-09-03
ai-hub、ai-resource-hub、feishu-data-hub 三仓已整合为 ai-platform。
需要统一 AI 工程的代码、资产和文档边界，避免网关游离在项目治理之外。

## 决策

search_gateway 整体迁入 ai-platform 工程，作为**仓内子项目**维护。

保留两段式结构：

- `services/` —— 代码
- `data/` —— 配置与运行数据

工程位置：`D:\项目\ai-hub\search_gateway`

## 原因

- search_gateway 与 ai-platform 同属 AI 基础设施，资源与配置强耦合。
- 将其作为独立工程维护，会与 ai-platform 产生重复治理与边界模糊。
- 文档/资产/项目索引统一跟随 ai-platform，Agent 定位成本最低。

## 不采用的方案

### 继续作为独立工程
不采用原因：与 ai-platform 同域（AI 基础设施），独立维护会造成"一个能力两套入口"。

### 只迁代码、不迁 data
不采用原因：配置与运行数据是网关运行的一部分，分离会破坏"代码 + 数据两段式"的一致性。

## 后果

正面：
- 代码、资产、文档、治理统一归属 ai-platform。
- Agent 从 ai-platform 即可定位网关全部资源。

约束：
- search_gateway 不再视为独立 GitHub 项目。
- 项目级治理归 ai-platform（projects.yaml 保持 ai-platform 唯一顶层 entry）。

## 不变量

- Obsidian Work 为人工知识真源。
- GitHub 仅承担代码历史和发布镜像。
- 不建立双向同步。

## 关联

- `../00-search_gateway-总览`
- `../../docs/work/task-cards/search-gateway/SG-001-迁入-ai-platform-主工程`
- GPT 三轮咨询结论：`./_三轮咨询纪要_20260905_GPT`