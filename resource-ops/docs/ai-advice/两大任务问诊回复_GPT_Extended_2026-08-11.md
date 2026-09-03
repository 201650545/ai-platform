# 两大任务方案 · GPT 问诊回复（Extended 深度版）

> 问诊对象：ChatGPT（镜像站 vip-17，GPT-5.6 Thinking·Extended）
> 问诊时间：2026-08-11
> 问诊输入：docs/ai-advice/两大任务问诊提示词_2026-08-10.md
> 模式说明：首轮问诊（2026-08-10，Auto 模式）回复较浅且发现思考时长 0 秒，永涛要求重问；本轮切 Extended 模式重问，思考约 5 分钟，回复深度显著提升
> 首轮回复（Auto）已存档：两大任务问诊回复_GPT_2026-08-10.md
> 凭证值：本文件不含任何凭证值

---
结论

v1 的方向是对的，但目前更像“平台清单 + 提醒”，还不够成为一个执行 Agent 可以无人看守连续跑的任务包。尤其缺四样东西：明确的页面路径与字段、统一判断状态、人工介入边界、可复核证据。而项目总方案已经定义了 PENDING → LEASED → RUNNING → SUCCEEDED / FAILED / NEEDS_HUMAN、最多 3 次尝试、MFA/验证码/支付立即转人工、证据采用哈希+脱敏摘要等规则，这些应直接下沉到本次任务。

两大任务仍建议保持 A 海外 4 + B 国内 6，不再拆成两个独立阶段或两个 Agent 接力。正确做法是：同一个 Agent 对每个平台执行“入口/登录 Gate → 账户权益深查 → API 规格深查”，能一路跑通就一次完成；遇到验证码、扫码、实名认证等则把该平台转 NEEDS_HUMAN，先继续下一个平台。这样既避免二次导航和上下文丢失，也不会被某个平台卡死。

但 A1 必须改写：GitHub 官方已经确认 GitHub Models 于 2026-07-30 完全退役，playground、model catalog、inference API、BYOK 都已关闭，而且官方明确它与 GitHub Copilot 是两个不同服务。因此不要再让 Agent 花时间寻找“GitHub Models 新入口”；应改为“退役确认 + GitHub Copilot/其他替代资源另建候选记录”。

另外三项海外平台也不能再把旧传闻写进任务作为事实：Colab 免费 GPU 类型和使用上限是动态的，Google 明确不公布固定额度；Together 当前官方明确“不提供免费试用”，平台使用需至少购买 $5 credits；Mistral 则当前明确存在 Free mode，可创建 API key，并使用账户 Limits 页显示的月度包含额度。

国内组同样出现结构性变化：腾讯混元旧平台计划于 2026-09-30 全面停服，新模型正在迁往 TokenHub，所以 B2 必须同时记录“旧混元剩余权益”和“TokenHub 新入口”，否则刚建好的规格库很快就过期。

最终每个平台不要只回答“有没有免费额度”，而要产出一条接近未来「资源实例表」的数据：服务状态、登录态、认证方式、Key 是否存在、免费额度结构、剩余量、重置/有效期、绑卡/后付费、API Base URL、协议、模型 ID、限流、证据、人工待办。这与项目方案里“能力与实例分离、结构化额度、验证策略、证据”的设计更一致。

优化后方案
两大任务 · 免费资源调研执行方案 v2
0. 两任务共享规则

目标

对指定平台完成“账号可达性 + 当前真实权益 + 可执行 API/计算规格”验证，为后续飞书「资源能力规格表 / 资源实例表」提供素材。Secret 值绝不写入 GitHub、Markdown、终端日志或截图；只记录 key_exists=true/false、Key 数量及认证类型。项目本身也明确要求 Secret 只留本地，配置面只保存 credential ID / auth scheme / allowed host。

统一执行顺序

打开“账户/控制台入口”，先判断登录态。

若已登录：直接进入额度/账单/用量页。

若未登录但页面提供已允许的 Google OAuth：可选择永涛现有 Google 账号并完成普通登录。

登录完成后查“额度 → API Key → API 文档/模型 → 限流/计费”。

登录受阻时，仍可通过官方公开文档完成公开规格调查，然后把账户专属字段记 UNKNOWN_NEEDS_LOGIN。

不因为账户登录失败而终止整个任务，立即继续下一个平台。

统一状态值

AVAILABLE_VERIFIED：已登录，权益及调用规格已核实。

AVAILABLE_DOC_ONLY：官方确认存在资源，但本账号权益未登录核实。

NO_FREE_QUOTA：已确认当前账号没有免费额度。

RETIRED：产品/API 已退役。

NEEDS_HUMAN：验证码、扫码、实名认证、密码、人工表单等阻塞。

UNKNOWN：官方资料与控制台均无法确认，禁止自行猜测。

人工介入 / 防卡死规则

以下情况第一次出现立即停该步骤，不重试：

手机验证码、短信验证码；

微信/QQ 扫码；

CAPTCHA；

Passkey、2FA、设备确认；

要求重新输入 Google/其他账号密码；

实名认证、身份证信息；

绑定手机；

绑卡、开通后付费、充值、购买 credits；

任何扣费确认；

创建组织时要求填写无法从现有上下文确定的公司/职位/用途；

新的法律协议、企业认证或需要永涛做主观选择的 onboarding。

Google OAuth 仅允许处理普通的“选择已有账号 → 基础登录/继续”；若出现新的敏感权限授权、身份确认或上述项目，则转 NEEDS_HUMAN。

对网络错误、页面加载失败等纯技术故障：同一动作可重新执行，但总 attempt 不超过 3 次；达到上限后转 NEEDS_HUMAN/FAILED。这与项目方案中的 attempt 上限和 NEEDS_HUMAN 阻塞规则保持一致。

对于 404/入口迁移：最多执行“旧入口 → 官网产品导航 → 官方文档搜索”三步；找到官方退役/迁移声明即停止，不继续猜 URL。

禁止自动执行

不创建或删除 API Key；不充值；不绑卡；不开后付费；不订阅套餐；不修改账单设置；不领取需要同意付费回退机制的权益。

统一记录格式

每个平台回写：

## 平台 N · 平台名 · <STATUS>

- 平台入口：
- 服务状态：ACTIVE / MIGRATING / RETIRED
- 登录态：LOGGED_IN / LOGGED_OUT / NEEDS_HUMAN
- 登录方式：
- 账号权益：
  - free_quota_type：
  - quota_total：
  - quota_remaining：
  - quota_unit：
  - reset_cycle：
  - expires_at：
  - claim_required：
  - requires_card：
  - paid_fallback：
- API：
  - api_available：
  - api_base_url：
  - protocol：OpenAI-compatible / Anthropic-compatible / Vendor SDK / WebSocket / N/A
  - model_ids：
  - auth_scheme：
  - key_exists：
  - rate_limit：
- 资源价值：
- 验证证据：
  - console_url_path：
  - observed_fields：
  - key_exists：
  - official_doc：
  - screenshot_local_path：（可选；仅本地、已脱敏）
  - checked_at：
  - evidence_hash：（可生成则填写）
- 待办：
- 不确定项：

其中“验证证据”优先采用 URL path + 页面字段文字摘要 + Key 存在性 + 官方文档；截图只作为本地辅助证据，不上传含凭证、Cookie、Authorization、账户敏感信息的整页截图。项目原方案也要求结构化回写和脱敏 evidence，而不是传输整页敏感页面。

任务 A · 海外平台组
A1 · GitHub Models —— 改为「退役确认 + 替代候选登记」

动作清单

打开旧入口 https://github.com/marketplace/models，记录最终 URL/状态。

打开 GitHub 官方 Models 文档。

查找 retired、July 30, 2026、inference API 等字段。

一旦官方退役声明确认，直接填写：

service_status=RETIRED

api_available=false

free_quota_type=N/A

key_exists=N/A

不要继续寻找所谓“GitHub Models 新入口”。官方已经说明此服务完全退役。

若 GitHub 当前账号已登录，可顺手查看 Copilot entitlement/plan，但只新增一条“候选资源：GitHub Copilot”，不可把 Copilot 免费/高级请求额度写成 GitHub Models 免费额度，因为 GitHub 官方明确两者不是同一个服务。

待办写：“原 A1 资源退役；如资源库需要 GitHub 内 AI 权益，后续单独建 GitHub Copilot 能力/账号实例。”

验收标准

看到官方退役声明即可完成；不以找到可调用模型为验收目标。

A2 · Google Colab —— 验证「当前实际可分配计算资源」，不再写死 T4

动作清单

打开 https://colab.research.google.com。

看右上角 Google 头像/账号，判断登录状态。

未登录且普通 Google OAuth 可直接完成，则自动登录；出现密码重验、2FA 等立即 NEEDS_HUMAN。

新建一个空白 notebook。

打开 Runtime → Change runtime type，记录当前账户实际出现的 hardware accelerator 选项。

如果免费账户允许选择 GPU：

选择 GPU；

连接 runtime；

仅执行一个最小 GPU 信息探针，例如 nvidia-smi；

记录实际分配 GPU 型号；

完成后断开 runtime。

若 GPU 不可选、提示 usage limit、资源不足或需购买 compute units，原样记录提示。

查看账户是否显示 Colab 订阅/Compute Units；记录 plan 和剩余单位（若有）。

不填写“免费 T4 = 固定权益”。Google 官方明确免费资源的 GPU 类型、VM 生命周期、idle timeout、总体 usage limit 都会动态变化，并且不公布固定限制。

api_available=false/N/A；资源类型应记作“交互式计算/GPU”，不要错误登记成模型 API。

验收标准

必须回答：今天这个账号能否获得 hosted runtime、是否能选 GPU、实际拿到什么 GPU/提示什么限制。

A3 · Together.ai —— 重点确认「是否还有历史免费 credits」，不要假设有免费层

动作清单

打开 Together 控制台。

判断登录态；若有普通 Google OAuth 按共享规则操作。

登录后先进入 Billing/Credits，而不是先去模型页。

记录：

credit balance；

是否有 promotional/historical credits；

是否显示充值要求；

是否有过期时间。

官方当前明确：Together 不再提供 free trial，并要求至少购买 $5 credits 才能使用平台；因此如果余额为 0 且页面要求购买 credits，直接判 NO_FREE_QUOTA，禁止充值。

打开 API Keys，只记录 key_exists 和数量；不要创建新 key。

记录 API Base URL https://api.together.ai/v1、OpenAI compatibility 和当前可用 model IDs。

打开 Rate Limits/Usage 页面；不要写死固定 RPM/TPM，因为 Together 当前使用动态、按组织/模型变化的限流，并建议依据实际 response headers 获取最新值。

如果账号存在历史免费 credits，则记录为现有资产；若没有，则资源库价值改为“付费候选”，不要归类成“免费资源”。

验收标准

必须明确区分“平台技术上可调用”和“这个账号目前是否有零成本可用余额”。

A4 · Mistral —— 深查 Free mode、Limits、API 权限

动作清单

打开 https://console.mistral.ai。

判断登录态；登录页若提供普通 Google OAuth，可按规则完成。

登录后打开 Admin/Subscription：

记录当前 plan；

判断是否为 Free mode；

检查 pay-as-you-go 是否启用。

打开 Usage/Limits：

记录 included monthly usage；

remaining usage；

reset 周期；

RPM/RPS/TPM/月 token 等实际显示值。

官方当前说明 Free mode 可以创建 API key 并使用账户包含的月度 usage；具体额度以账户 Limits 页面为准，因此不要在任务文字里预填一个固定免费 token 数。

打开 API Keys，只记录已有 Key 的存在性/数量，不新建。

API 记录：

Base：https://api.mistral.ai/v1

auth：Bearer API key

models：从当前 Models 页面/API 可见 ID 中记录

model availability：以账户实际可见结果为准。

如果出现需要绑卡才能开启 pay-as-you-go，不要开启；Free mode 能否继续调用单独记录。

如果 free allowance 已耗尽，记录下一 reset 时间，而不是简单写“无免费额度”。

验收标准

必须拿到“plan + included/remaining/reset + key_exists + API endpoint + 至少一组账户可用 model ID”。

任务 B · 国内平台组
B1 · 百度千帆

动作清单

打开百度千帆控制台，判断百度账号是否已登录。

若需要手机验证码等，立即 NEEDS_HUMAN，但继续公开文档调查。

已登录则进入 模型广场 → 模型版本详情。

对具有免费权益的模型记录：

model/model version；

免费额度总量；

剩余量；

剩余可用时间。
百度官方当前就是通过模型版本详情页展示免费额度剩余量和剩余时间。

再检查预置推理服务/计费详情，核对是否标为“免费额度”。

进入 系统管理 → API Key：

key_exists

Key 数量

权限类型

不复制 Secret、不创建新 Key。

查当前模型调用文档，记录 OpenAI SDK compatibility、实际模型 ID、endpoint 类型；千帆官方目前提供 OpenAI SDK 兼容调用。

记录免费额度耗尽后是“停止”还是“进入后付费”；如果控制台要求主动开后付费则只记录，不开启。

不要把“百度 AI 搜索每日免费额度”等工具额度和 LLM token 免费额度混成一个实例；不同能力分别记录。

验收标准

至少得到一个“模型 ID + 免费剩余量/有效期 + API Key 状态 + 调用协议”的组合。

B2 · 腾讯混元 / TokenHub

动作清单

先打开现有混元控制台，判断账号登录态。

若已登录，进入资源包/用量页，记录旧混元当前剩余免费包、有效期。

当前官方生文免费资源包括部分模型共享的 100 万 tokens 等，且资源包有有效期；账号实际页面优先于任务预设数字。

进入 API Key 页面，只记录 Key 是否存在。

记录旧接口 Base URL（若账号仍在使用）以及当前 model IDs；旧混元目前仍提供 OpenAI-compatible 接口。

随后必须再检查 TokenHub。

判断：

是否已经迁移；

TokenHub 是否有独立 API Key；

当前免费体验/资源包；

模型 ID；

新 endpoint；

原混元权益能否迁移。

官方已宣布旧混元平台将在 2026-09-30 全面停服，因此记录必须增加：

migration_status

successor=TokenHub

legacy_expiry/platform_shutdown=2026-09-30。

不因旧混元目前还能调用就把它标成长期稳定实例；建议状态写 MIGRATING。

验收标准

必须同时回答“旧混元还有什么”和“以后应该从哪里调用”。

B3 · MiniMax 开放平台

动作清单

打开 MiniMax 开放平台并判断登录态。

遇手机号验证码立即 NEEDS_HUMAN。

已登录先查账户余额/赠送权益/活动权益，确认当前账号到底还有没有免费额度。

分开检查两类 Key：

普通按量付费 API Key；

Token Plan 订阅 Key。
MiniMax 官方明确两者是两个独立 Key 体系，不能混用。

两类 Key 均只记录存在性，不创建。

查当前模型列表与调用文档，记录 model IDs、base URL、OpenAI-compatible 支持情况。

查 Rate Limits，并分别记录免费用户/充值用户限制；例如当前官方对部分语言模型明确列出了“免费用户”RPM/TPM 档位，这说明“免费用户限速”与“账户是否仍有可消费免费余额”是两个不同概念，不能混写。

查 Token Plan/积分余额及窗口规则，但如果没有订阅，不购买。

若控制台无余额、只有购买入口，写 NO_FREE_QUOTA；不要依据 v1 的“新户免费额度”旧印象直接填数字。

验收标准

必须分清“免费账号速率档”“实际赠送余额”“Token Plan 套餐额度”三种概念。

B4 · 零一万物 Yi

动作清单

打开 https://platform.lingyiwanwu.com。

判断是否已有 session。

若要求手机验证码/实名认证，立即 NEEDS_HUMAN。零一万物当前官方账号规则明确以手机号注册/验证码登录，并可能要求实名认证。

即使无法登录，也继续读公开文档：

当前模型列表；

OpenAI-compatible 调用方式；

model ID；

API endpoint；

pricing/rate limit；

是否仍有新户/免费额度。

若已登录：

查余额/赠送金；

查免费额度有效期；

查 API Key 是否已有；

查用量页面。

特别记录 model_routing_behavior：零一万物当前平台官方描述其为多模型聚合平台，并可能根据资源/质量等因素智能匹配模型。

因本项目要求同一 routing_group 不得偷偷换底层模型，如果某个接口无法固定具体模型而会自动路由，则：

标 canonical_model_pinnable=false

不要直接作为严格 canonical model 实例入库

转待架构确认。

官方主页仍明确展示 OpenAI API 兼容能力，可将协议兼容作为公开规格收集。

验收标准

除了额度，还必须确认“能否明确锁定底层 model ID”。

B5 · 讯飞星火

动作清单

打开讯飞开放平台/星火 API 产品页。

判断登录态；手机号验证码即 NEEDS_HUMAN。

已登录则查“我的资源/服务量/免费额度”，记录具体模型对应剩余 token/调用量及有效期。

官方当前仍明确提供“领取免费额度”的流程，因此不能只调查营销页，要进入账号控制台确认是否已经领取、剩多少。

查凭证：

HTTP API：记录当前 APIPassword/API credential 类型；

WebSocket 旧/其他接口：记录 AppID + APIKey + APISecret 这一认证方案；

只记类型与存在性，不记值。

优先调查当前 HTTP OpenAI-compatible 接口，官方当前给出的 Base URL 为 https://spark-api-open.xf-yun.com/v1/。

记录实际可用 model IDs、免费版本、RPM/并发限制。

注意不要照搬旧的 Spark Max 等型号：官方文档已经说明部分版本在 2026 年发生升级/下线，应以当前模型列表为准。

如发现“智能体 API”“MaaS Token Plan”等另外的免费资源，作为独立 capability/instance 候选，不并入基础聊天模型额度。

验收标准

至少产出“当前模型 ID + 免费余额 + HTTP Base URL + credential scheme”。

B6 · 阶跃星辰 StepFun

动作清单

打开 StepFun 开放平台，判断登录状态。

手机验证码等出现即 NEEDS_HUMAN。

已登录分别查看：

标准 API 账户余额/赠送余额；

Step Plan / Token Plan Credit；

API Key 页面。

不预设“新户一定有免费 token”。当前 StepFun 已有多个过去的限时免费资源结束，例如 step-2x-large 已在 2026-06-12 结束限时免费，Step Explore 也不单独发放免费额度。

如果标准 API 账户为 0 元充值级别，记录其当前 V0 的并发/RPM/TPM 限制；这只是限流等级，不是免费余额。官方当前标准 API V0 仍列有明确速率档。

检查 Step Plan：

plan 是否存在；

Credit 总量/剩余；

reset 周期；

专用 Key 是否存在。

Step Plan 在 2026-06-18 已升级为 Credit 月池模式，因此旧“Coding Plan/免费额度”的历史描述不能继续作为规格真源。

记录两类 endpoint 时必须分开：

标准 API；

Step Plan 专用 https://api.stepfun.com/step_plan/...。
官方当前 Step Plan 使用独立路径和权限。

如无免费余额且必须购买套餐，写 NO_FREE_QUOTA，禁止购买。

验收标准

必须区分“标准 API 余额/限速”和“Step Plan Credit/月池”，不能把二者合并成一个额度。

两任务最终汇报格式

任务结束后追加：

## 本轮汇总

### 1. 模块 × 验收项
A：完成 x/4
B：完成 x/6

### 2. 状态统计
AVAILABLE_VERIFIED：
AVAILABLE_DOC_ONLY：
NO_FREE_QUOTA：
RETIRED：
NEEDS_HUMAN：
UNKNOWN：

### 3. 待永涛一次性处理
平台 | 卡点 | 永涛唯一需要做的动作 | 完成后从哪一步继续

### 4. 重要政策变化
平台 | v1 旧认知 | 本次核实结果 | 官方证据

### 5. 可直接进入资源库的实例
平台 | capability/model | quota | endpoint | key_exists | verified_at

### 6. 已知偏差
仅列尚未实际登录验证、政策冲突、模型路由不确定等问题。
风险

GitHub Models 已退役，继续按旧任务寻找入口会造成无效执行。

腾讯混元正处于向 TokenHub 的迁移期，旧平台数据若直接入长期规格库会很快失效。

Colab 免费 GPU 没有稳定、公开的固定额度或固定 GPU 型号，只能记录“验证时刻实际状态”。

Together 已不属于“默认免费 API 平台”，历史 credits 与当前免费政策必须分开。

“免费用户限流档”不等于“账户拥有免费余额”，MiniMax、StepFun 等平台尤其容易被误判。

Mistral 免费额度是账户/计划动态 Limits 数据，不应把网上旧额度数字固化进任务。

国内平台登录、实名、手机号绑定会导致大量 NEEDS_HUMAN，Agent 必须允许跳过单平台继续全局执行。

自动创建 API Key 会产生新的 Secret 生命周期，因此本轮只验证 Key 是否存在，不负责凭证发放。

自动开通后付费可能把“免费资源调研”变成真实消费风险，因此任何 pay-as-you-go/绑卡动作都禁止自动执行。

零一万物若使用无法锁定底层模型的智能路由，会与项目“不跨模型自动切换”的核心规则冲突。

只记录余额而不记录单位、重置周期和有效期，会使后续调度器无法正确判断资源是否可用。

截图若包含 API Key、Cookie 或账户敏感字段，会破坏项目的 Secret 本地化边界。

实施步骤

用本方案整体替换 两大任务方案_v1_2026-08-10.md，版本建议升为 两大任务方案_v2_2026-08-11.md。

先执行任务 A；A1 应很快转 RETIRED，A2-A4按“登录 Gate → 权益 → API”完成。

任务 A 不等待任何单平台人工处理；遇 NEEDS_HUMAN 后继续后续平台。

执行任务 B；优先把六个平台的公开规格全部摸完，再利用现有登录态补账户专属额度。

把所有手机号/微信/实名认证卡点合成一张待永涛处理清单，避免十次零散打断。

永涛一次性完成这些人工登录后，让同一 Agent 仅恢复对应平台，从上次 Gate 后继续，不重跑已确认的公开文档。

回写 验证记录_2026-08-10.md 时统一使用新状态和新证据字段，不再出现“疑似”“通常”“应该有”等无法验证的额度表述。

对每条 AVAILABLE_VERIFIED 做一次完整性检查：model/capability + quota + expiry/reset + endpoint + auth_scheme + key_exists + limit + evidence 缺任一核心字段则仍标“待补”。

将 GitHub Models、腾讯混元迁移、Together 无免费 trial 等“政策变化”单列，防止后续 Agent 再根据旧上下文把错误信息写回来。

调研完成后再把验证记录映射成飞书资源能力/资源实例字段；本轮不要急着把原始网页字段直接当最终表结构。

需确认

API Key 创建边界：我建议本轮严格“不新建 Key，只查是否存在”；如果永涛希望本轮同时完成“免费权益领取 + 新 Key 配置”，应把它明确升级成“调研 + 领取/配置”任务，并规定 Secret 直接写入哪个本地凭证后端。

GitHub Models 的替代项：建议 A1 保留为退役记录，同时另建“GitHub Copilot 权益”候选，而不是把 Copilot 强行当 Models 后继实例；是否要在本轮顺手深查 Copilot，需要永涛拍板。

腾讯 TokenHub 是否纳入 B2 必验范围：我建议“必须”，因为原混元平台官方已经给出 2026-09-30 下线时间。

零一万物智能路由是否允许入库：如果不能保证底层模型固定，我建议只能作为“聚合/自动路由能力”单独登记，不能加入严格 canonical model 的轮换池。

证据截图策略：建议默认只保存 URL path + 字段摘要；只有额度/迁移等容易变化且文字 extract 不充分时才留本地脱敏截图，这样更符合现有 evidence_hash 安全设计。

“免费资源”定义：建议正式定义为“当前账号无需新增付费即可调用的权益”，把“需要至少充值一次才能访问”“仅有免费用户限速但无余额”“免费试用已结束”全部排除，否则 Together、StepFun、MiniMax 等平台很容易产生口径混乱。

