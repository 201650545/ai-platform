# GPT 镜像站送审流程（运行手册 · 固定加速版）

> **状态**：v1 起草（2026-09-03）。用户拍板固定流程 4 步 + 提速要点；待本轮实时送审（子 Agent）返回实际卡点后合入加严。
> **用途**：向 GPT 镜像站（AI问答宝账号池 → vip-XX 镜像）以 **Extended** 模式送评审 / 问架构。
> **铁律**：能不复探就不复探（选择器已固化，直接照抄）；一个任务 ≤3 轮；同一对话 ≤40 轮不新开；发前把上下文 push GitHub 让 GPT 强读。

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

## 四、账号与窗口纪律

- 受限就点右上角「**切换账号**」换**活跃**卡，别卡死在受限账号。
- **共享标签页纪律**：`tab create` 自开标签页操作，**绝不占用别人的标签**（别的 Agent/用户也在用这个日常 Chrome）。
- 进入镜像统一走 opencli 连**日常 Chrome**（profile `n8hh7hyn` default，daemon 19825），不是新实例。

## 五、发问前置（每次必做）

- 上下文 push 到目标 GitHub 仓（`git -c http.proxy=http://127.0.0.1:7890 push`），提示词写「请先读 <repo>/<path> 后再…」。
- 精确列出要读的文件路径清单，别只给仓库根或单个链接。

## 六、红线

- 任何 secret/凭证值**不回显、不入仓、不进输出**。
- `financial-security-plan` 永不公开（个人财务档案）。
- 评审未过 → 零代码改动；方案拍板后才动仓库。

## 关联

- 流程出处/历史坑：`.claude` 记忆 [[workflow-gpt-repo-sync]]
- 背景：ai-platform × Obsidian 重构（`docs/设计/ai-platform-obsidian-rfc.md`）