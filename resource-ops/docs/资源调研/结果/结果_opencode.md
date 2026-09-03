# 资源调研 · 结果_opencode（海外组：Cohere / Replicate / Stability / fal.ai）

> 执行者：opencode（主 Agent 自领）｜日期：2026-08-10
> 依据：`分派/05_opencode_海外组.md`｜交接书：`调研任务交接_2026-08-10.md`

---

## 平台 1 · Cohere ⚠️ 已登录但 onboarding 未完成

- **平台**：https://dashboard.cohere.com
- **登录态**：✅ 已登录（Google OAuth 通过，账号 `yongtaog767@gmail.com`，跳到 /welcome/about-you onboarding）
- **登录方式**：Google OAuth
- **免费额度现状**：被 onboarding 流程挡住未看到具体额度（新户通常有试用 credit）
- **价值**：Cohere Command R / Embed 系列 API，海外可直连
- **待办**：⚠️ onboarding「Let's get to know you better」表单提交失败（营销邮件 checkbox 程序无法勾选，点击后提交回跳原页）——**需郭老师人工点一次 Continue** 完成新户引导，之后才能看到 API keys / 免费额度

---

## 平台 2 · Replicate ✅ 已登录

- **平台**：https://replicate.com
- **登录态**：✅ 已登录（GitHub OAuth，账号 `201650545`，即 GitHub 同名）
- **登录方式**：GitHub OAuth（唯一入口，无 Google）
- **免费额度现状**：无卡模式（Billing 未绑定）；API token 已有（Default，`r8_***`）；免费档模型可跑，付费模型需绑卡
- **价值**：Run/fine-tune 模型 API，聚合大量开源模型；新户无卡可跑免费档
- **待办**：无（已可用）；若要跑付费模型需郭老师绑卡
- **登录技巧（记给后续复用）**：GitHub OAuth 的 `requestSubmit()` 不带按钮 `authorize=1` 值导致授权无效——需 `eval` 注入 `<input name=authorize value=1>` 再 `form.submit()`

---

## 平台 3 · Stability AI ✅ 已登录

- **平台**：https://platform.stability.ai
- **登录态**：✅ 已登录（Google OAuth，账号 yongtaog767@gmail.com / 郭永涛）
- **登录方式**：Google OAuth（Auth0）
- **免费额度现状**：**25 credits**（新户赠送）；API key 已自动生成（`sk-Rt9***Qol`，2026-08-10 创建）；无支付记录
- **价值**：Stable Diffusion / Stable Image 生图 API（SD3.5/SDXL 等）；25 credits 可跑少量生成
- **待办**：无（已可用）；额度用完后需购买 credits
- **登录技巧（记给后续复用）**：Google OAuth + Auth0 双 consent——① Google 账号 chooser 的 `role=link` 卡片需 eval 模拟 click ② Google consent 点 Continue ③ Auth0 consent 需注入 `<input name=action value=accept>` 再 `form.submit()`

---

## 平台 4 · fal.ai ✅ 已登录（onboarding 已跑通）

- **平台**：https://fal.ai
- **登录态**：✅ 已登录（Google OAuth，账号 yongtaog767@gmail.com / 永涛）
- **登录方式**：Google OAuth
- **onboarding**：已自动跑通（For myself → Build with Code → 跳过可选），直接进 dashboard
- **免费额度现状**：**$0.00 无免费额度**（Current balance $0.00，Pay as you go 档，无新户赠送 credits，Auto top-up 关）
- **API key**：已创建 `0729930a-••••••••`（2026-08-10，tag=API，完整值在 dashboard 复制，需用时进 API Keys 页取）
- **价值**：聚合 1000+ 生成式模型 API（生图/视频/音频/3D：Seedance、Flux、Kling、Wan、GPT Image 等），serverless 调用；**但纯付费，无免费额度，启动成本高**
- **待办**：无（已登录可用）；要用需充值，暂不适合免费资源库
- **登录技巧（记给后续复用）**：Google OAuth 双跳（accountchooser `role=link` 卡片需 eval 点击 → consent 点 Continue）；onboarding 是卡片式单选（H3/H4 标题 + 父级 `.group` 卡片可点击），最后一步可选直接跳过

---

# 汇报（四段式）· opencode 包 5 完成

## 1. 模块 × 验收项

| 平台 | 验收 | 状态 |
|------|------|------|
| Cohere | 登录态 + onboarding | ⚠️ 已登录，onboarding 待人工点一次 Continue |
| Replicate | 登录态 + 免费档 + token | ✅ 已完成（GitHub OAuth，token r8_***，无卡） |
| Stability | 登录态 + 生图额度 + API key | ✅ 已完成（Google OAuth，25 credits，sk-Rt9***Qol） |
| fal.ai | 登录态 + onboarding + 免费额度 | ✅ 已完成（Google OAuth，onboarding 跑通，$0.00 无免费额度） |

## 2. 变更清单

- `结果/结果_opencode.md`：追加平台 3（Stability）、平台 4（fal.ai）记录 + 本汇报；Cohere/Replicate 前序会话已写入

## 3. 验证

- 3/4 完整可用：**Replicate、Stability、fal.ai**（已登录 + 可创建/已有 key）
- 1 个待人工：**Cohere** onboarding 表单最后一关需郭老师人工点 Continue（营销 checkbox 程序无法勾选）

## 4. 已知偏差

- fal.ai 确认**无任何免费额度**（新户 $0.00）——付费平台，不适合免费资源库，仅记录待充值
- Stability 25 credits 用完需购 credits（1000 起购）
- 所有 API key 完整值不写仓库（合规），需用时到对应 dashboard 复制
