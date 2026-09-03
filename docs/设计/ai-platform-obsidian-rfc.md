# RFC v2 · ai-platform × Obsidian 结合方案（评审修订版）

> **状态**：评审修订 v2（2026-09-03）。已按 GPT 镜像站 Extended 送审意见**重构**，复审中，**未动仓库**。
> **作者**：调度大脑（Claude）　**日期**：2026-09-03
> **上一评审**：GPT 送审回「有条件通过 / Request changes」9287 字意见（PDF 落盘 `.claude/gpt_review_aiplatform.md`），v2 已逐条消化（见 §4 生效表）。

## 1. 背景与现状（勿重查，已实测）

- GitHub 9→6 整合已完成（2026-09-03）：新主仓 **ai-platform**（https://github.com/201650545/ai-platform），main 已含四模块：ai-hub 主干（根）/ `resource-ops/` / `integrations/feishu/` / `agent/memory/`（协议快照；运行仓 `ai-hub-memory` 独立勿动）。
- 飞书同步管线绿，Pages 上线 https://201650545.github.io/ai-platform/。
- 工作区索引 `D:\项目索引` = 独立 Obsidian vault（外部 AI 路由入口，projects.yaml + STATUS）。
- **本地 `D:\AI平台`（ai-platform 工作树）当前不是 vault（无 .obsidian/）**，且运行体与知识混层：代码/运行目录（`00_中央平台`/`integrations/`/`resource-ops/`/`agent/`/`tests/`/`config/`/`06_组件编排器`/`docs/migration/`）、机器派发体（`04_任务卡`/`05_执行指令`/`AI日报`）、根级知识 md（`README.md`/`项目简述.md`/`问题分诊.md`/`反馈记录.md`/`免费资源权益清单_2026.md` + `ARCHITECTURE.md`/`TOPOLOGY.md`/`project.yaml`）。

## 2. 参照惯例（nitian-theme 已实测）

鉴定骨架：**仓库根 = vault**（含 `.obsidian/` + `Home.md`），`docs/` 四件套 = 人维护入口：`00-项目总览.md` / `01-任务看板.md`（四态：待办/进行中/待验收/完成）/ `02-资产清单.md` / `03-规格与规范.md` + `任务书/` `归档/` `设计/` 子目录；根 `project.yaml`。索引 key：`task_board: docs/01-任务看板.md`。

## 2.5 命名原则（用户 2026-09-03 拍板，全仓适用）

用户非英语母语，中英混名混乱难懂。**人看的层全中文**：Obsidian 笔记/文档/运行手册/看板/项目显示名一律中文命名与中文内容；**代码目录/被 CI/import 引用的路径保留英文**（是给机器跑的），但在中文文档（如 docs 四件套）里注明中文名便于对照；**GitHub slug 受平台限制只能 ASCII**，走英文/pinyin 作 URL 把手，中文名登记在索引里。详见记忆 [[feedback_chinese_naming]]。

## 3. 设计方案（v2 按 GPT 意见重构）

**核心原则**（改）：仓库根 = vault；`docs/` 四件套 = **人与陌生 Agent 的统一知识入口**——具体事实由各领域唯一 owner 持有，四件套只做摘要与指向，**不复制运行事实**。

### 3.1 Vault 边界
整个仓库根 = vault（补 `.obsidian/` + 根 `Home.md`），**不做 docs/ 子 vault**。Obsidian 排除列表只是**展示层隔离**（图里只待笔记），不等于架构/安全边界——纯代码/运行目录不依赖排除来保护。`.obsidian/` 只提交**最小可复现**配置（设置 + 排除清单），不提交本地缓存。

### 3.2 任务卡：一状态一 owner（否决双写）
nitian 01-看板 = 人维护；ai-platform 已有 `04_任务卡`（orchestrator 机器消费）+ `05_执行指令` = 运行体。**驳回双写状态**（会成两套账）。
- `04_任务卡` = **机器执行唯一真源**，原样保留、Obsidian 排除；
- 新增 `docs/01-任务看板.md` = **人类验收视图**，registry `task_board` 指向它；
- **互不复制执行状态**：看板只记录「验收结论/状态/证据链接」，指向 `04_任务卡/task_XXX.md` 而不是搬运里面每步状态。

### 3.3 四件套内容（摘要+指向，不复制事实）
- `00-项目总览`：平台能力/记忆协议在哪/飞书导出在哪 + 命名原则 → 满足「陌生 Agent 只读本仓能答」；
- `01-任务看板`：人类验收视图（见 3.2）；
- `02-资产清单`：只登记名称/用途/存放位置 = **env-key 或 GitHub secret 槽位名**，值一律不回显；**不含 key_prefix 等任何疑为凭据的字段**（见 §5）；
- `03-规格与规范`：网关/编排/飞书管线 + handbook 链接（指向各自领域唯一 owner，不复制正文）。

### 3.4 根级 md 归位（合并一部分、链接一部分，不全当真源）
- `README.md`：保留（GitHub/陌生 Agent 入口）+ 指向 Home；
- `ARCHITECTURE.md`：**标题仍是「AI Hub 架构设计」（旧主干）**——不能当整个 ai-platform 完整架构真源。处置：并入 `docs/03-规格与规范` 相关小节改为「平台主干架构摘要」，完整拓扑链接到各模块 README；
- `TOPOLOGY.md` / `项目简述.md`：合理并保留或并入总览；
- 现有功能目录**不重命名**（命名原则 §2.5 已覆盖：机器路径英文、中文文档注名）。

### 3.5 项目索引：单向 + 迁移溯源全归 path-map
- 索引只**指向**各 vault，不回流；多 vault 各自独立（nitian / ai-platform / 逆天主题）。
- `project.yaml` 可信性修复：删 `modules[].from` 旧仓名（溯源已在 `docs/migration/path-map.md`），修正「迁移启动」→「已完成」矛盾，`migration:` 指针指向 path-map。**旧仓名只在 path-map 出现**。

### 3.6 执行顺序（修正自洽冲突）
按 §5 红线「评审未过零代码改动」，执行顺序改为——①②是文档草稿（本轮已做）：**① 修订 RFC 草稿（v2）→ ② 送 GPT 复审 → ③ 拍板 → ④ 通过后才动仓库（写四件套 → Home+.obsidian 最小配置 → registry key → 扫命名 → 用户验收）**。拍板前不动任何功能/CI/Pages。

## 4. GPT 评审意见生效表（6 条 → v2 决定）

| # | GPT 意见 | v2 决定 | 落点 |
|---|---|---|---|
| 1 | vault 边界倾向整根；排除列≠架构/安全边界；.obsidian 只提最小可复现 | 采纳 | §3.1 |
| 2 | 驳回任务卡双写（两套账）；一状态一 owner；01=验收视图不复制执行状态 | 采纳 | §3.2 |
| 3 | 资产红线只保「02 不写 secret 值」不够；威胁面含 auth.json token/history/飞书对话/key_prefix；扩为任何凭据+仓库级防护 | 采纳（最重） | §3.3 + §5 |
| 4 | 索引单向赞成但更彻底；project.yaml 不可靠（迁移启动vs已完成矛盾、残留旧仓 from）；溯源全归 path-map | 采纳 | §3.5 |
| 5 | 根 md 合并一部分+链接一部分；ARCHITECTURE 还是旧主干标题不能当整仓真源 | 采纳 | §3.4 |
| 6 | 「docs 四件套=唯一事实源」→「统一知识入口；各领域唯一owner持事实，四件套摘要+指向不复制」 | 采纳 | 3 顶部核心原则 |
| 7(新) | 执行顺序与 §5 红线自洽冲突 | 修正 | §3.6 |

## 5. 红线（扩严）

- 评审未过，零代码改动；拍板后才动仓库。
- **任何凭据**——不止 secret 值，含 config/auth.json token、history.json、飞书对话、`api_channels` 的 key_prefix 等疑为凭据字段——**不回显、不入仓、不进输出**；资产清单只留 env-key/secret 槽位名。
- `financial-security-plan` 永不公开（个人财务档案）。
- 涉及外部 API 凭据走环境变量/CI secret，不落盘不入仓。
- 旧仓名只在 `docs/migration/path-map.md` 出现；命名遵守 §2.5（人看层中文）。

## 6. 关联

- 数据桥/管线：`integrations/feishu/`（Pages 管线）
- 记忆协议：`agent/memory/`（快照）；运行仓 `ai-hub-memory`
- 索引：`D:\项目索引\projects.yaml`
- 送审流程：`docs/运行手册/GPT镜像站送审流程.md`；命名政策：记忆 [[feedback_chinese_naming]]