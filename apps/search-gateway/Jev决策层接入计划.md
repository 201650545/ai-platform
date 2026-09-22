# Jev 决策层接入计划（System One Model）

> 郭老师 2026-09-21 指示「把这个计划上」。定位：**不是聊天模型，不进三档编排**——它是给网关和上层自动化加的「毫秒级决策层」。
> 状态：✅ 已注册+实测通过（2026-09-21）。key 在 `data/typesafe_key.txt`（gitignore），console.typesafe.ai/keys（key 名 gateway）。实测：noul/choice+置信度+概率全通，2.1s/次。当日全网解禁：注册送 $5≈1.2亿 token，输入 $0.042/M、输出免费。

## Jev 是什么

- TypeSafe AI 出品（前 OpenAI 研究员创办，2026-09-15 发布，DCVC 领投 $40M 种子轮）
- **System One 模型**：不生成文字，专出结构化决策。三种提问原语：
  - **Choice**：从选项列表选一个（返回 choice + 各选项概率 + confidence）
  - **Score**：按 rubric 给状态打分（score + confidence）
  - **Noul**：判断陈述真伪（0–1）
- 毫秒级响应、近零成本（Forbes：比 LLM 便宜 100x）、多问题并行评估
- 官方 patterns：intent routing / confidence-gated routing / speculative fan-out / composite scoring

## 为什么跟我们有缘（郭老师的判断）

> 「对普通人才是刚需，普通人没有那么多创业场景，反而很多重复性工作」

LLM 聊天解决"创作"，Jev 解决"判断"——普通人日常大量是重复性判断（分类/路由/打分/批准/拒绝），这才是刚需缺口。

## 接入方案（三步走）

### 第一步：注册实测（门槛：注册 typesafe.ai 拿 TYPESAFE_API_KEY）
- API：`POST https://api.typesafe.ai/v1/systemone`（Bearer key）
- SDK：`pip install typesafe-sdk`（Python≥3.10）；官方还有 agent skill
- ⚠️ 定价未公开：官网只说 near-zero，需注册后看账单页；先用 Playground 验证效果再定规模
- 验证场景：课件审核打分、消息分类、网关意图路由

### 第二步：接入网关自身（最有价值的内部用途）
- **意图路由**：请求进来先让 Jev 分类 → 自动选 free-fast / free-balanced / free-heavy
  （现在三档靠调用方自己选别名，Jev 能实现"发一句话自动走对档位"；confidence 低→升档）
- **派发中心 :8791**：任务→执行位选择用 Jev 打分（派发矩阵四维：能力/速度/资源限度/有效时间）
- 实现：api_gateway 加一个内部决策调用模块（非 chat 渠道，独立于 members 编排）

### 第三步：对外的「决策即服务」（普通人刚需产品化）
- 在网关上开决策端点：用户给状态+问题模板 → 返回结构化决策
- 场景举例：消息/邮件分类、工单路由、内容审核打分、清单批准/拒绝、简单客服分流
- 这些场景调用量大单价低，正好吃 Jev 的近零成本

## 风险与备注
- 定价不透明：若没有免费档，按量成本也应在可忽略级（每决策约 $0.0000x），注册后核实
- Jev 只做判断不生成内容——创作仍走 LLM 三档，两者互补不冲突
- 品牌新（9月中发布），API 可能变动；接入层做薄封装隔离

## 关联
- 真源规则：`渠道编排规则.md`（Jev 不进三档，无需改编排）
- Obsidian：project_ai_gateway 时间线
