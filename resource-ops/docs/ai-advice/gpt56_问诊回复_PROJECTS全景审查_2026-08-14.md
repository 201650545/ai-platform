# GPT 镜像问诊回复 — PROJECTS 项目全景方案审查（强制实读确认）

> 问诊对象：global/PROJECTS.md（项目全景进记忆常读层）方案审查
> 时间：2026-08-14 ｜ 模型：GPT 镜像站 vip-23 · GPT-5.6 Extended
> 执行：v4 Flash ｜ **实读证据**：24 处 GitHub 引用；精确复述 MEMORY.json global_read 三项、PROJECTS.md 结构、RULES R14/R16 与 global 边界测试。
> **核心结论**：① 方向对，但 PROJECTS 应从"5 仓库 README 合集"收缩为"跨仓库路由图" ② 5 分法：RULES=MUST / PROJECTS=WHERE / RESOURCES=WHAT / TOOLS=HOW / STATE=NOW ③ 删除所有状态/版本/端口/进度字段（防漂移）④ RULES 补 registry 例外 ⑤ 读取模型：Kernel→Landscape→Routed Project→On-demand Detail。
> **我方拍板（代表用户）**：① RULES 补例外 ② global_read 保留三项（新项目单元读一次）③ 全部删除状态字段。已落地 push `1dfda9b`。
> **第二轮确认回复为空回复**（镜像站渲染失败），不影响——方案按第一轮定稿执行。

---

确认，这 3 个拍板点组合起来是自洽的，不需要再引入 bootstrap_read 或新的 memory schema。最终应把 PROJECTS.md 定义成一个非常窄的 跨仓库路由索引：回答“有哪些项目、各自负责什么、相互怎么连接、确定归属后下一步去哪读”，而不是保存任何项目事实快照。

我建议最终结构固定为下面 5 段，之后也尽量不要继续长出新栏目：

Markdown
# PROJECTS — 跨仓库项目地图

> 作用：帮助 Agent 快速判断任务属于哪个仓库，以及下一步应该读取哪里。
>
> 边界：仅记录项目身份（Identity）、职责边界（Boundary）、
> 跨仓库关系和下一跳（Source）。
> 不记录项目状态、版本、进度、端口、目录结构或实现细节。
> 生命周期信息仅在其会改变 Agent 路由时记录，例如 archived / 禁止使用。

## 1. 全景

- ai-hub-memory — 多 Agent 共享记忆与上下文路由
- ai-resource-hub — AI 资源与配置的管理/权威来源
- ai-hub — AI 能力的操作、网关与编排层
- feishu-data-hub — 飞书数据到 AI 消费侧的数据桥
- english-teaching-production — 英语教学业务生产体系

## 2. 项目路由

| Repository | Identity | Boundary | Next hop |
|---|---|---|---|
| ai-hub-memory | Agent 共享记忆系统 | 管记忆、路由和跨 Agent 上下文；不承载具体业务实现 | MEMORY.json / 对应 project STATE |
| ai-resource-hub | AI 资源管理中心 | 管资源事实和配置；不承担 Agent 记忆职责 | repo README / authoritative resource source |
| ai-hub | AI 操作与编排层 | 管能力调用、网关和编排；不作为资源台账真源 | repo README / code |
| feishu-data-hub | 飞书数据桥 | 管飞书数据到消费侧的转换与发布链路；不定义上层业务规则 | repo README |
| english-teaching-production | 教学生产业务仓库 | 管英语教学领域的生产规范和业务流程；不承载通用 Agent 基础设施 | repo README / teaching STATE |

## 3. 跨仓库关系

- ai-hub-memory → 为各 Agent / 项目提供共享记忆与上下文路由
- ai-resource-hub → 向 ai-hub / Agents 提供资源与配置来源
- feishu-data-hub → 将飞书侧数据转换为 AI 可消费的数据
- ai-hub → 消费资源和数据，提供能力调用与编排
- english-teaching-production → 作为具体业务生产层使用上述基础设施

## 4. 下一跳规则

- 不知道任务归属 → 先读本文件
- 已确定 memory project → 读对应 `STATE`
- 查当前项目状态 / 下一步 → `STATE`
- 查资源、账号、额度、服务事实 → `RESOURCES` / ai-resource-hub 权威来源
- 查工具和操作方法 → `TOOLS`
- 查不可违反的系统规则 → `RULES`
- 查实现细节 → 对应仓库 README / code
- 查跨项目长期决定 → `DECISIONS`

## 5. 维护规则

仅在以下变化发生时更新本文件：

- 新增、删除或重命名仓库
- 仓库核心 Identity 改变
- 仓库职责 Boundary 改变
- 权威来源 / Next hop 改变
- 跨仓库关系改变
- 生命周期变化足以影响 Agent 路由

以下变化不得写入本文件：

- 版本号
- 上线日期
- 当前进度 / 任务完成情况
- 端口
- 目录结构
- 临时实现方案
- private / public 等不影响路由的属性

有三个细节我建议在落地时固定下来。

第一，Source 最好正式叫 Next hop，或者 Source / Next hop。 因为这里不是要复制“权威事实”，而是告诉 Agent 去哪里取得权威事实。例如 PROJECTS 不写“当前 API 有多少额度”，只写“资源事实 → RESOURCES / ai-resource-hub”。这样天然避免双写。

第二，不要再设置 Status 栏。 即使以后觉得“加个状态很方便”，也尽量抵制。只要新增 Status，很快就会重新出现 active、M1、上线日期之类的漂移内容。影响路由的 archived 可以直接写进 Boundary，例如“已归档；新任务不得路由至此”。

第三，关系图只表达稳定的职责/数据依赖，不表达当前运行拓扑。 比如“资源配置 → ai-hub”可以；“某服务当前部署在哪、哪个端口调用哪个端口”不可以。后者属于 HOW/NOW。

这样最终的信息架构就是：

RULES      = MUST   不可违反什么
PROJECTS   = WHERE  任务属于哪里、下一步去哪
RESOURCES  = WHAT   现在拥有什么资源
TOOLS      = HOW    怎么操作
STATE      = NOW    当前做到哪里

再加一个 DECISIONS = WHY 其实也很自然：为什么系统长期选择了这种做法。 不必因此改你的“五分法”，但 Agent 在判断某个设计为什么存在时，应去 DECISIONS，而不是让 PROJECTS 承担解释历史。

在你已经确认“global_read 只在新项目单元启动读一次”的前提下，我会明确支持继续保留 RULES + DECISIONS + PROJECTS 三项 global_read。PROJECTS 压缩到上述粒度后，它不是上下文负担，而是路由成本的优化器。

最后，RULES 中那句例外建议按你已经拍板的文字直接加入，不再扩展更多例外。PROJECTS 是唯一的 registry/index 例外，而不是开启“单项目信息也可以进 global”的口子。 这样整个架构的边界最干净。

