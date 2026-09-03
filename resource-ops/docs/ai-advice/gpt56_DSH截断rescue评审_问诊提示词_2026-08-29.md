【角色设定】
你是一位资深 LLM 网关/Agent 系统架构专家 + 成本与可靠性审稿人。

【背景】
本地多 Agent 环境：DSH（DeepSeek Harness，类 Claude Code 的 agent 宿主，node 服务）经本地 OpenAI 兼容网关(:3100)调 LLM；统一模型组 fast 的首选位是 xiaohongshu/dots3-note-prev（推理型、零价）。该模型先做 reasoning 再输出正文，推理会消耗 max_tokens 预算；预算耗尽时 HTTP 200 但正文空、finish_reason=length。

【上下文（请先打开实读，再作答）】
- 必读（唯一的实读对象）：https://raw.githubusercontent.com/201650545/ai-hub-memory/master/projects/ai-resources/STATE.md
  只需精读最末条 [S-20260829-09]（含全部实测数据）。该条目内嵌核验令牌：DSH-TOKEN-MAXTOKENS-64ROOT-3QK9-FIXED
  实读要求：你的回复第一行必须原文引用这个令牌；引用不出即视为未实读，本轮作废。

【当前方案概要】
1. 实测推翻转交假设"DSH 发小 max_tokens"：DSH 主对话请求实际 max_tokens=32768（pi-ai 库 profile 级 defaultMaxTokens 的 schema 默认值）；主对话截断实录（会话 jsonl：turn 37/38 的 outputTokens=32768、stopReason=length、blocks 仅 reasoning、responseModel=dots-studio/dots3-note-prev，输入上下文 12 万+ token）——即 32768 大预算也会被长上下文任务的纯推理烧光。
2. 真正的小值 64 来自 session-title-llm 会话标题插件（bundle/base 默认配置树 maxOutputTokens=64；session/title-llm-request 事件实证 route=local-gateway/fast、maxTokens=64）。
3. 网关量化实测（title 真实 system 提示词形态）：max_tokens=64 与 512 均 finish_reason=length 且 content 空（512 也不够，title 形态推理约耗 500 completion）；1024 才 stop 且标题正常（completion 513）；2048 亦稳（473）。此前"正常回答普遍耗 130~260"的口径只适用于简单问答。
4. 已落地修复（纯配置零代码）：~/.dsh/profiles/web/cordis.patch.yml 新增 patch，把 session-title-llm 的 config.maxOutputTokens 64→1024；坑：cordis 的 config patch 是整对象替换而非深度合并（首版只写一个字段时 dump-config 显示其余 required 字段全丢、插件会加载失败），必须写全 5 个字段；已用 `dsh --profile web --dump-config` 验证合成树；UAC 提权重启 nssm 服务 DeepSeekHarness 成功，web :3080 恢复 200。
5. 已按纪律回写共享记忆并推送（S-20260829-09）。

【请优化的点】
1. title 预算 1024 是否合理？更稳（2048）还是更省（768）？是否存在比"给 title 插件提预算"更优的替代方案（例如 title 路由改走非推理型成员）？注意约束：统一名 fast 是网关白名单语义（客户端不可自由点名成员），网关侧 per-route 路由属新功能。
2. 主对话层截断（32768 仍被烧光）的处置优先级与设计要点，三个候选：a) 网关在"fast 命中推理型成员且 finish_reason=length 且 content 为空"时自动加大预算重试（新功能）；b) DSH 侧在 turn/end reason=max-tokens 时自动补一轮"继续"（DSH 是第三方、闭源、运行中服务，改造成本高）；c) fast 编排对长上下文场景改路由到非推理型成员（若上游无等价零价非推理模型则不可行）。
3. 若做候选 a（网关自动重试），边界条件怎么定才能不破坏网关既有不变量："流式 commit point 后不得 failover/换上游"、"fast 全零价保障"、重试预算上限与次数上限？

【约束 / 红线】
- 凭证纪律：任何回复不得包含真实 token/key/密码；只描述"是否存在"。
- 禁 git push --force；禁给 :3100 加 /v1/messages 端点；不让网关重新接受 <渠道>:<模型> 前缀（D-GLOBAL-20260828-02）。
- 不顺手扩功能：超出本次修复范围的想法只作为 backlog 建议。
- 本次问诊单任务 ≤3 轮对答，这是第 1 轮。

【输出格式】（严格按此结构输出）
- 结论（一页以内总评）
- 优化后方案（可直接替换的完整版）
- 风险（每条一句话）
- 实施步骤（编号，可执行）
- 需确认（拿不准、需要用户拍板的点）
