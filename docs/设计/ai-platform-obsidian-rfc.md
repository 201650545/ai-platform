# RFC · ai-platform × Obsidian 结合方案（v1 评审草稿）

> **状态**：评审中草稿 v1（送 GPT 镜像站 Extended 评审，未拍板，未动代码）
> **作者**：调度大脑（Claude）
> **日期**：2026-09-03
> **评审判据**：见文末「待评审问题」——GPT 按此给意见；红线见「红线」。

## 1. 背景与现状（勿重查，已实测）

- GitHub 9→6 仓库整合已完成（2026-09-03）：新主仓 **ai-platform**（https://github.com/201650545/ai-platform），main 已含四模块：
  - ai-hub 主干（根目录）/ `resource-ops/` / `integrations/feishu/` / `agent/memory/`（记忆**协议**快照；运行仓 `ai-hub-memory` 独立勿动）
- 飞书同步管线已跑绿，Pages 上线 https://201650545.github.io/ai-platform/，catalog 4 项目
- 工作区索引 `D:\项目索引` = 独立 Obsidian vault（外部 AI 路由入口，projects.yaml + STATUS.md 一行式快照）
- **本地 `D:\AI平台`（= ai-platform 工作树）当前不是 vault（无 `.obsidian/`）**，且是运行体混杂：
  - 纯代码/运行目录：`00_中央平台/`（网关服务代码+面板）、`integrations/`、`resource-ops/`、`agent/`、`tests/`、`config/`、`06_组件编排器/`（编排器代码）、`modelscope-daily/`（运行产出）、`docs/migration/`（历史存档）
  - 机器派发运行体：`04_任务卡/`（task_XXX.md，orchestrator 派发消费）、`05_执行指令/`（每模型指令）、`AI日报/`（日志）
  - 根级知识 md：`README.md` / `项目简述.md` / `问题分诊.md` / `反馈记录.md` / `免费资源权益清单_2026.md` + `ARCHITECTURE.md` / `TOPOLOGY.md` / `project.yaml`  / `root .github/.gitignore`

## 2. 参照惯例（nitian-theme 已实测验证）

鉴定的四件套骨架：**仓库根 = vault**（根含 `.obsidian/` 与 `Home.md`），`docs/` 四件套 = 唯一事实源：
`00-项目总览.md` / `01-任务看板.md`（四态：待办/进行中/待验收/完成）/ `02-资产清单.md` / `03-规格与规范.md`，外加 `任务书/` `归档/` `设计/` 子目录；根 `project.yaml`。project 索引 key：`task_board: docs/01-任务看板.md`。

## 3. 设计方案

**核心原则**：仓库根 = vault（镜像 nitian）；`docs/` 四件套 = 人维护、只读此仓能答的唯一事实源；代码/运行目录不许进 Obsidian 图。

### 3.1 Vault 边界
补 `D:\AI平台\.obsidian/` + 根 `Home.md`（vault 入口；README 仍为 GitHub/陌生 Agent 入口）。Obsidian 设置排除全部纯代码/运行目录，图里只待笔记。

### 3.2 任务卡双轨（关键分叉，需拍板）
nitian 的 01-任务看板 = **人维护看板**；ai-platform 已有 `04_任务卡`（orchestrator 机器消费）+ `05_执行指令` = **运行体**。建议：
- 新增 `docs/01-任务看板.md` = 人看的基础设施看板（四态），registry `task_board` 指向它；
- `04_任务卡`/`05_执行指令` 原样保留、Obsidian 排除（机器读写，不打断运行契约）；
- 关系：任务卡执行完 → 调度大脑回写 `docs/01-任务看板` 状态/验收。

### 3.3 四件套内容
00-总览（平台能力/记忆协议在哪/飞书导出在哪 → 满足「陌生 Agent 只读本仓能答」）；01-任务看板；02-资产清单（**只登记名称/用途/存放位置 = env-key 或 GitHub secret 槽位名，值一律不回显不入仓**）；03-规格与规范（网关路由/编排/飞书管线 + handbook 链接）。

### 3.4 根级 md 归位
倾向能少动就少动：`ARCHITECTURE/TOPOLOGY` 留根；现有功能目录不重命名；核心是「增 docs/ 四件套 + Home + 排除」，不是推倒重排。

### 3.5 与项目索引关系
项目索引 = 元登记（只指向各 vault，不回流）。ai-platform 行补 `task_board`（齐平 nitian），可选 `vault: Home.md`。

### 3.6 执行顺序（获批后）
写四件套骨架 → Home+.obsidian+排除 → 最小归位 → 补 registry key → 送 GPT 评审 → 拍板 → 动代码。

## 4. 待评审问题（请 GPT 逐条给意见）

1. **Vault 边界**：把整个工作树当 vault、用排除法隔离代码目录，是否优于「另建 docs 子 vault / 双目录」？Obsidian 排除代码目录有无漏网/索引负担隐患？
2. **任务卡双轨**：新增人看板与保留机器任务卡双轨，是否正确？会不会制造「两套账」？有无更优的「一套真源」折叠方式且不打断 orchestrator 契约？
3. **资产清单红线**：02-资产清单只登记 env-key/secret 槽位名、值不走仓库，这个泄密边界是否够？Gateway 等本就是运行时取 env 的，还有什么该补的防护？
4. **项目索引单向**：索引只指向不回流是否合理？多 vault 各自独立有无 navigation/一致性风险？
5. **根级 md 归位**：能少动就少动是否合理？哪些根级文件其实该并进四件套？

## 5. 红线

- 评审未过，零代码改动；方案获拍板后才动仓库。
- 任何 secret/凭证值不回显、不入仓、不进输出（资产清单只留槽位名）。
- `financial-security-plan` 永不公开（个人财务档案）。
- 涉及外部 API 的凭据走环境变量/CI secret，不落盘不入仓。

## 6. 关联

- 数据桥/管线：`integrations/feishu/`（Pages 管线）
- 记忆协议：`agent/memory/`（快照）；运行仓 `ai-hub-memory`
- 索引：`D:\项目索引\projects.yaml`