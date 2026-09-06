# GPT 镜像站送审流程（运行手册 · 固定加速版）

> **状态**：v1 起草（2026-09-03）。用户拍板固定流程 4 步 + 提速要点；待本轮实时送审（子 Agent）返回实际卡点后合入加严。
> **用途**：向 GPT 镜像站（AI问答宝账号池 → vip-XX 镜像）以 **Extended** 模式送评审 / 问架构。
> **铁律**：能不复探就不复探（选择器已固化，直接照抄）；一个任务 ≤3 轮；同一对话 ≤40 轮不新开；发前把上下文 push GitHub 让 GPT 强读。
> **提问闸门（不可绕过）**：任何问题**发出的前一个动作必须是确认模型 pill = "Extended"**。刷新会重置回 Auto，**每次都要重切再发**；在 **Auto/默认** 模式下直接提问 = 违规，该子 Agent 直接判不合格。慢 ≠ 着急，宁可多花 10 秒切好再发，也别浪费一轮。

## 一、固定 4 步流程（用户拍板）

1. **开池 + 一眼定位账号**：打开 wendabao 账号池页。定位**绿色圆点=活跃**的 Plus 账号卡；受限（灰/红）直接跳过，**别点它**。这是目前最慢的一环——把「找可用账号」从一个个试，改成**先扫一眼绿色卡再点**。
2. **点击 + 秒跳镜像**：点 `innerText` 以 **"GPT-5"** 开头的第一个 `.n-card span`（**不是** Plus 徽章按钮——那只会刷新账号池列表）。点击会触发 `window.open('...plus-login?...')` 被 Chrome 弹窗拦截吞掉 → **破法**：先 eval 劫持 `window.open = function(u){window.__openUrl=u;return null;}`，再点 span，然后本标签 `location.href = window.__openUrl` 跳转。几秒内到位。
3. **扫聊天记录定窗口**：到 vip-XX 镜像后：①**同一评审主题之前聊过 → 复用原窗口**（GPT 保上下文，质量更高、不用等新 Extended 预热）；②**全新主题 → 立即新开 tab 不犹豫**。
4. **切 Extended**：pill = `button.__composer-pill`（文本 Auto）→ **只能** eval 合成完整指针序列点开（opencli 原生 click / 键盘 ArrowDown 打不开 Radix 菜单）→ 在 `[role=menuitemradio]` 里选 **"Thinking• Extended"** → **pill 文本变 "Extended" 才生效**。刷新会重置回 Auto，每次都要重切。

## 二、提速要点（把「慢」的根源堵掉）

慢的根源：**每次重探 DOM + opencli 原生 click 打不开 Radix 菜单**。破法：

- **选择器一次固化写死**，后续直接照抄，绝不重复 find/探测（这是本次提速的最大杠杆）。
- 所有菜单/按钮点击**一律合成完整指针事件序列**（`pointerover→pointermove→pointerdown→mousedown→pointerup→mouseup→click`，带 `pointerId/pointerType`，坐标取 `getBoundingClientRect` 中心）。不碰原生 click、不碰键盘导航。
- 注入中文文本：优先 `opencli browser <s> fill`；不行再 base64+`atob`+`TextDecoder` 解码后 eval 注入。
- **监控 15s 一把**；Extended 思考 1-3 分钟才出字，深度问题总时长可达 15 分钟——出了流式字就别喊停（`streaming:true len:0` 属正常）；上一轮没结束**绝不发下一轮**（会打断）。
- 提示词要**精简**：长提示词镜像站响应慢/易断。上下文让 GPT 从仓库读，窗口里只写「请读 <repo/path> 后…」。

## 三、选择器速查表（已实测固定，版本敏感）

| 目标 | 选择器 / 判定 |
|---|---|
| 账号卡 Plus | `.n-card span`，innerText 首 "GPT-5"，绿色点=活跃 |
| 弹窗拦截破法 | 劫持 `window.open` 存 `__openUrl` → 点 span → `location.href = __openUrl` |
| 模型 pill | `button.__composer-pill`（文本 Auto→Extended） |
| Extended 菜单项 | `[role=menuitemradio]` → "Auto" / "Thinking• Extended" / "GPT-5.6 Luna" |
| 发送 | `[data-testid=send-button]` |
| 停止（流式中） | `[data-testid=stop-button]` |
| 回答 | `[data-message-author-role=assistant]` 最后一条 |
| composer（历史对话页） | **contenteditable**（`wcDTda_fallbackTextarea` 是 0×0，别注进去）→ 优先 fill，失败 focus+`execCommand('insertText')` |
| 新对话页 composer | textarea（placeholder "Ask anything"）→ 原生 value setter + input 事件 |

## 三·五 固化一键脚本法（2026-09-04 实测，零→Extended ≤15s）

> 用两段固化脚本替代逐段手点，快 5–6 倍（74s→9.6s）。脚本在 `docs/runbooks/scripts/evalA_jump.js` 与 `evalB_ext.js`，直接 `opencli browser n8hh7hyn eval "$(cat <脚本>)"`。不复探。

```
opencli browser n8hh7hyn tab new "https://ai.wendabao-f.net/?utm_source=hidden-ncn"   # 新标签
sleep 2
opencli browser n8hh7hyn eval "$(cat scripts/evalA_jump.js)"    # A：卡0 GPT-5 → 劫持window.open → location.href 跳 vip-XX
opencli browser n8hh7hyn eval "$(cat scripts/evalB_ext.js)"     # B：自同步等 hydration → 开 pill → 选 Thinking•Extended → 验 pill=Extended
```

- **evalA_jump.js**：只取 `.n-card[0]` 的 GPT-5 span，劫持 `window.open` 存 `__openUrl`，点后 `location.href=__openUrl` 秒跳镜像。（账号池当前全卡活跃，缺省取卡 0；若将来受限卡变多，回到扫描绿色点。）
- **evalB_ext.js**：**全自动含内部 await 轮询**（无固定 sleep）：
  1. 等 `location.host` 落到 `67673.live`；
  2. **hydration 闸门**：等 `button.__composer-pill` 文本从占位 `Model` 变成可操作 `Auto`/`Extended`（**关键：占了 "Model" 就点必扑空**，这是跨实例最大坑）；
  3. 完整指针序列+原生 `.click()` 开菜单，自旋重试 ≤3 次；
  4. `[role=menuitemradio]` 里选 `Thinking• Extended`；
  5. 等 pill 文本=`Extended` 返回 `{ok:true, after:'Extended'}`。
- **同吃 evalB**：新对话(/，textarea)与旧对话(/c/…，contenteditable)的 composer 都是 `button.__composer-pill`，B 直接复用；进旧对话后照跑 B 即可。
- **实测**：T1 13.9s(暴露 hydration 坑)、T2 9.6s、T3 14s(新+旧双验证)全 `ok:true`。
- **提问闸门不变**：B 返回 `ok:true` 才可发；每次发送共用 B 复核，刷新/换对话回 Auto 就连跑 B。

## 四、账号与窗口纪律

- 受限就点右上角「**切换账号**」换**活跃**卡，别卡死在受限账号。
- **共享标签页纪律**：`tab create` 自开标签页操作，**绝不占用别人的标签**（别的 Agent/用户也在用这个日常 Chrome）。
- 进入镜像统一走 opencli 连**日常 Chrome**（profile `n8hh7hyn` default，daemon 19825），不是新实例。

## 四·五、子 Agent 执行纪律（2026-09-03 用户拍板，防重探/防重置）

> 用户当场反馈：①子 Agent「从打开到提问整 2–3 分钟才找到搜索框」；②「每次执行完把老标签关了 → 每次新子 Agent → 全流程重跑」。子 Agent 走本流程必须：

1. **写死、一次到位**：选择器 / localStorage 登录 / 完整指针事件序列**一律照抄本节+§三速查表**，**不复探 DOM、不重编选择器**。从打开到注入发送应在 **1 分钟内**到位。慢的根源只有两处——重探 + 挨个试账号；两者都要靠"先扫健康卡 + 选择器照抄"消掉。
2. **不关标签/会话**：上一轮完成**保留绑定 tab 与 opencli 会话不动**。下一个任务在**同一聊天框继续输入**（遵守每任务 ≤3 轮、每窗口 ≤12 轮），**绝不因拉新子 Agent 重跑全流程**。
3. opencli 会话名用 `n8hh7hyn`，新任务先 `tab list` 找一个**已绑定的旧 tab 直接 state 确认可用**，没有再建——不要无脑新开又能空 session。
4. **提问闸门（强闸，优先级最高）**：**每次发问前**——无论是否刚切过——先检查顶部 pill 文本：是 "Extended" 才能发；是 "Auto" 就必须按 §4 重切 Extended 再发。刷新/回历史/换窗口都会重置回 Auto，**没有例外、没有"刚才切过"这种想当然**。Auto 提问横竖都是白烧一轮，切好再发永远对。

## 五、发问前置（每次必做）

- 上下文 push 到目标 GitHub 仓（`git -c http.proxy=http://127.0.0.1:7890 push`），提示词写「请先读 <repo>/<path> 后再…」。
- 精确列出要读的文件路径清单，别只给仓库根或单个链接。

## 六、红线

- 任何 secret/凭证值**不回显、不入仓、不进输出**。
- `financial-security-plan` 永不公开（个人财务档案）。
- 评审未过 → 零代码改动；方案拍板后才动仓库。

## 关联

- 流程出处/历史坑：`.claude` 记忆 [[workflow-gpt-repo-sync]]
- 背景：ai-platform × Obsidian 重构（`docs/design/ai-platform-obsidian-rfc.md`）