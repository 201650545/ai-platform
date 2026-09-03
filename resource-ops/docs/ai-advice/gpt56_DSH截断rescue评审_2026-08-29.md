DSH-TOKEN-MAXTOKENS-64ROOT-3QK9-FIXED

结论（一页以内总评）

已实读 [S-20260829-09]：主对话实际 max_tokens=32768，长上下文下可被纯 reasoning 全部耗尽；真正的 64 来自 session-title-llm；真实 title 提示词下 512 仍空、1024 首次稳定产出，且现有 1024 patch 已正确处理 Cordis 整对象替换问题。
GitHub

总体建议：当前 title 修复保持 1024，不改 768，也暂不升 2048。 1024 对目前约 473–513 completion 的实测需求已有接近 2× 的预算余量；768 只有约 50% 余量，面对提示词、标题输入长度和模型推理波动偏紧；2048 虽然更稳，却会削弱 title 本应是“小任务”的保护上限，容易把模型行为退化掩盖成“继续加预算”。如果后续仍出现 1024 + length + 空正文，再升 2048，而不是现在预防性翻倍。

title 更好的长期方案确实是让它走零价非推理模型，但不应作为本轮修复继续扩功能。 标题生成天然属于低复杂度、短输出任务，让推理模型先花约 500 token 思考再吐十几个字，本身就是模型—任务错配。如果现有配置里已经存在一个可通过统一白名单语义调用的零价非推理组，可纯配置切换；如果必须新增网关 per-route/task-aware routing 才能做到，则列入 backlog，本轮不要为了 title 再改网关。

主对话问题我建议排序为 a > c（条件成立时可反超 a） > b：

a 网关自动 rescue retry：当前最现实的主修方向。 但只能做成非常窄的“reasoning-only truncation rescue”，而不是通用 length 自动重试。

c 长上下文改走非推理成员：架构上比重试更干净。 一旦以后存在“零价、长上下文能力足够、质量经过回归”的非推理成员，它应成为这类任务的优选，届时甚至可排到 a 前面；目前没有合格成员就不要硬做。

b DSH 自动发“继续”：最后选择。 不仅闭源改造成本高，而且第二轮“继续”不等价于给原调用更多推理预算，模型可能重新推理，再次耗尽；还会改变会话结构、工具调用与计费/统计语义。

对候选 a，我建议采用四条硬边界：首版只处理非流式；只重试原 resolved member、绝不重新选路；最多 1 次；初始硬上限建议 65536，但必须先确认该上游实际接受 >32768 的输出预算。 如果模型/上游自身最大 completion 就是 32768，那么 a 从机制上无效，不值得写代码。

优化后方案（可直接替换的完整版）

方案目标：把 title 层和主对话层视为两个独立故障域，不再用同一种“加 max_tokens”逻辑处理。

A. session title 层

维持当前：

session-title-llm.config.maxOutputTokens = 1024

并保持五个 required 配置字段完整写入 patch，不依赖 Cordis 深度合并。

预算策略定为：

512 = 已实测不足，禁止回退。
768 = 不采用，安全余量不足。
1024 = 当前默认。
2048 = 只作为 1024 再现 length + empty 后的二级处置。

同时把“title 改走零价非推理模型”登记为 backlog 优化项。若以后无需增加网关新能力、仅通过现有统一组配置即可完成，则可以提前实施；否则不要与本轮主对话 rescue 混在一个变更中。

B. 主对话 reasoning-only truncation

首版实现 gateway-side sticky rescue retry，而不是普通 failover。

触发条件必须同时满足：

客户端请求的是统一模型组 fast；

本次 resolved member 属于网关明确登记的推理型成员；

stream=false；

首次上游请求正常获得完整 HTTP 响应，尚未向客户端 commit；

finish_reason == "length"；

对客户端有意义的正文为空或纯空白；

没有 tool_calls、function_call、refusal 等其他有效语义输出；

若上游提供 usage，则 completion 已接近请求预算上限；reasoning_content 非空可作为加强证据，但不要让它成为所有厂商都必须提供的硬依赖；

首版将 rescue 范围限制在“大预算主对话”，建议配置为 original_max_tokens >= 32768，从结构上把现在 1024 的 title 请求排除掉。

首次命中后：

retry_max = min(original_max_tokens × 2, rescue_hard_cap, member_max_output, context_remaining_limit)

当前已知请求为 32768，因此建议首个实验值：

32768 → 65536

但 65536 不是先写死再试。实施前先直接核验 dots3-note-prev 是否真的接受并执行 65536；同时检查模型上下文限制能否容纳 input_tokens + retry_max。如果上游最大输出本来就是 32768，则关闭该成员的 rescue，不能靠不断重发同一个 32768 假装解决。

最重要的是 retry 路由语义：

第一次已经 resolved 到哪个 channel/model，第二次就固定调用同一个 channel/model。不得重新执行 fast 编排，不得因为 rescue 而跳到下一成员。

这同时解决两个问题：

不把“增加推理预算”偷偷变成“换模型/换供应商”；

不给新的收费路径留下入口，fast 的零价安全边界不会因 rescue 扩张。

第二次请求的返回策略建议：

retry 得到正常正文 + stop：返回 retry 响应；

retry 得到非空正文 + length：返回 retry 响应，并保留真实 finish_reason=length，至少用户已有可继续的正文；

retry 仍然 length + empty：停止，不做第三次；

retry 遇到网络错误、5xx、超时等：不要因为 rescue 再 failover；保留并返回第一次已经拿到的合法 length 响应，避免新增功能反而降低可靠性。

max rescue attempts = 1 应作为首版硬限制，而不是配置默认 1、允许随手改成 3。一次 32768 再一次 65536，最坏已经接近 3× 原始生成量；再增加重试次数通常意味着架构选型有问题，而不是重试次数不够。

C. 流式请求

首版明确不支持自动 rescue。

原因不是技术上绝对做不到，而是它直接碰到现有不变量：一旦 reasoning/content chunk 已经发送给客户端，就已经越过 commit point，之后不得假装原请求没发生再切请求。

不要为了支持它而：

缓存完整流直到结束；

延迟所有流式首 token；

在 commit 后 failover；

把两个上游 completion 拼成同一个 OpenAI stream。

这些都属于另一项设计，应留在 backlog。

因此规则简单化为：

stream=true → 保持现行为，不进入 rescue retry

D. fast 零价保障

rescue 不是一次新的路由决策。

它必须复用首轮已经通过 fast 准入得到的 resolved member，并再次确认该 member 当前仍满足 fast 的既有准入规则；不得在 rescue 代码里接受任意客户端指定的渠道/成员，也不得增加新的模型寻址语法。

如果固定成员在 retry 前已经不可用，则放弃 rescue、返回第一次响应；不要把“空正文修复”扩张成新的 failover 子系统。

E. 长上下文非推理路由

作为第二阶段 backlog：

如果以后出现满足以下条件的候选——零价、上下文窗口足够、指令遵循/Agent 工具能力达标、长上下文回归测试达到 dots3 所需质量——则对长上下文任务优先路由到它，比“先浪费 32768 reasoning、发现失败后再花 65536”更合理。

这里不要简单写死“输入超过 N token 就换模型”。应先采集截断率数据，再确定阈值；否则会把模型质量差异隐藏在一个未经验证的 token 阈值后面。

风险（每条一句话）

1024 title 风险： 模型推理分布如果未来明显右移仍可能再次截断，但目前升到 2048 缺少实测必要性。

768 风险： 与已测约 513 completion 的距离太近，很容易把偶发波动重新变成空标题。

自动 retry 语义风险： 网关实际上修改了客户端给出的 completion 上限，因此必须严格限定在 fast 的内部 rescue policy，不能推广成所有 OpenAI 请求的默认行为。

能力上限风险： 如果 dots3-note-prev 或其渠道最大 completion 就是 32768，则 65536 retry 方案在实现前提上不成立。

上下文窗口风险： 12 万+ 输入再申请大 completion 可能撞总 context limit，因此 retry_max 必须按剩余窗口裁剪。

延迟风险： 失败一次后再完整生成一次会显著放大尾延迟。

负载风险： 单次问题最坏会由 32768 completion 放大到约 32768+65536，所以首版必须坚持最多一次。

流式风险： commit 后重试会破坏现有响应一致性，因此首版完全排除 streaming。

路由风险： rescue 若重新执行 fast 选路，会把预算修复和 failover 混成一个不可预测的新语义。

DSH “继续”风险： 新 turn 可能重新进行推理而不是延续第一次内部 reasoning，因此不保证解决 32768 耗尽。

动态长上下文路由风险： 非推理模型即使更省 token，也可能降低复杂 Agent 任务质量，必须先做质量回归。

可观测性风险： 如果不记录首轮/重试的预算、resolved member、finish_reason 和是否产出正文，后续很难判断究竟是模型退化还是预算设计错误。

实施步骤（编号，可执行）

title 不再改配置。 保留当前 maxOutputTokens=1024 和完整五字段 Cordis patch；下一次真实新会话仅验证事件中的 maxTokens=1024 以及标题成功即可，完成 [S-20260829-09] 已留下的闭环项。
GitHub

在写 gateway rescue 代码之前先做 capability probe。 用同一 dots3-note-prev 链路验证 32768、49152、65536 请求是否均被上游接受，并确认实际最大 output/context 限制；若 65536 不被接受，立即停止候选 a 的实现，不要用多次 32768 重试替代。

定义一个非常窄的 is_reasoning_only_truncation() 判定。 首版只接受 fast + known reasoning member + non-stream + finish_reason=length + 无可见语义输出 + original max_tokens>=32768。

实现 sticky retry。 保存首次 resolved_channel/resolved_model，第二次绕过 unified route selection，直接复用该 resolved member，只修改允许修改的 output budget。

实现预算公式与硬上限。 初始采用 min(2×original, 65536, upstream output limit, context remaining)，且 attempts=1。

保留第一次响应作为 fallback。 第二次出现网络错误、超时或上游异常时，返回第一次 HTTP 200/length 响应，而不是把一个原本确定的截断变成网关错误。

明确禁用 streaming rescue。 代码入口在发现 stream=true 时直接跳过新逻辑，现有 commit/failover 行为一个字不改。

补最小回归集。 至少覆盖：正常 stop 不重试、length+有正文 不触发首轮 rescue、length+空正文 恰好重试一次、title 1024 不进入主对话 rescue、stream 不重试、retry 失败返回第一次响应、retry 不改变 resolved member。

补可观测字段而非扩管理功能。 日志记录 rescue_triggered / original_max / retry_max / resolved_member / retry_finish_reason / retry_has_content / retry_latency；不要记录提示正文或任何凭证值。

上线后先观察而不是继续加预算。 核心指标看 reasoning_only_length 发生率、一次 rescue 成功率以及 P95/P99 延迟；若 65536 仍频繁耗尽，停止“继续翻倍”的思路，重新评估 c 类路由或上下文治理。

把 title 非推理路由和长上下文智能路由分别列入 backlog。 不与这次 rescue patch 合并提交，以免一次修复同时改变预算、路由和模型选择三个维度。

需确认（拿不准、需要用户拍板的点）

1. 需要先拍板是否接受网关在极窄条件下突破客户端原始 max_tokens。 我建议接受，但仅限统一组 fast 的 reasoning-only + empty + length rescue；从严格 OpenAI API 语义看，客户端给出的 max_tokens 本来就是上限，因此这是有意识的网关策略例外，而不是透明代理行为。

2. 65536 必须以实测能力为准。 我建议它作为候选 hard cap，而不是现在就定成事实；如果上游实际最大 completion 只有 32768，候选 a 应判定为不可行，而不是继续堆 retry。

3. 对候选 c 的决策可以暂缓。 我的建议是：当前没有经过验证的等价零价非推理成员，就保持 backlog；一旦以后出现合格成员，再让 c 在符合条件的长上下文任务上逐步取代 a。

4. title 我建议现在明确拍板为“1024 固化，出现新失败证据才升 2048”。 不建议 768，也不建议本轮顺手开发 title 专用 per-route 路由。

如果按这套边界落地，我认为本轮最合适的最终状态是：title=1024 封版；主对话只新增一个非流式、同成员、一次、最高候选 65536 的 reasoning-only rescue；其他路由优化全部留 backlog。