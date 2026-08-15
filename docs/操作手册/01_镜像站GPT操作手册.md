# 操作手册 01 · 镜像站 GPT（问达宝）操控

> 用途：给任何执行 Agent / 新对话看，按此操作即可用镜像版 ChatGPT（GPT-5.6）提问、接收回复、落档
> 版本：2026-08-10 实测版 ｜ 操作者：opencode（DeepSeek-V4 flash）实测记录
> ⚠️ 镜像站界面/账号池/域名会变，本手册记录的是当日实测有效路径；执行时以页面实际为准

---

## 1. 入口与账号池

- 问达宝首页：`https://ai.wendabao-f.net`（2026-08-10 起页面提示旧域名停用，重定向回带 `utm_source` 的地址；新域名 `ai.wendabao.net` 可能作为后续入口）
- 页面列出 **ChatGPT Plus 镜像账号池**（卡片式），账号会动态变化：
  - `GPT-5 ⑲ / ⑫ / ㉓ / ⑪ / ⑨ / ㊾ / ⑰` —— 健康 Plus（本日实测可用）
  - `受限 ⑩/㊽/②/⑮/⑬/⑭/㊼` —— isHealthy=false，登录可能异常
  - `GPT-5 ⑯/⑱` —— Free 档 / Plus 失效
- **选号原则**：优先选 `isHealthy=true` 的 Plus 账号。旧号会降级（如 vip-15 曾健康，后变"受限 ⑮"），不要依赖固定账号。

## 2. 登录进入镜像（关键：localStorage 登录法）

> window.open 拦截/模拟点击弹窗不可靠，改用读 localStorage 构造登录 URL 直接导航。

1. 在问达宝页确认账号池：`eval` 读 `localStorage.getItem('panelAccountList')`，找 `isHealthy:true` 且 `badge:'PLUS'` 的 `carID`（如 `vip-19`）。
2. 读登录 token：`localStorage.getItem('authToken')`（JWT，敏感值不落文件/仓库）。
3. 构造并导航：
   ```js
   (()=>{const t=localStorage.getItem('authToken');
     location.href='https://vip-19.67673.live/api/v2/plus-login?account=vip-19&jwt='+encodeURIComponent(t);
     return 'navigating';})()
   ```
4. 等 6–10 秒，`get url` 确认跳到 `https://vip-19.67673.live/`，即进入真实 ChatGPT Plus 界面（有左侧 Chat history、New chat 按钮）。

## 3. 选模型 · GPT-5.6 Thinking·Extended

1. 找模型下拉：`find --text "Auto"`（输入框旁 pill，class `__composer-pill`）→ `click` 打开菜单。
2. 菜单项（用 `find --testid` 定位）：
   - `Auto` — `model-switcher-gpt-5-6`
   - **`Thinking•Extended`** — `model-switcher-gpt-5-6-thinking`（本手册目标模式）
   - effort 按钮 — `model-switcher-gpt-5-6-thinking-thinking-effort`（aria-label="Effort"，显示当前思考程度）
   - `GPT-5.6 Luna` — `model-switcher-gpt-5-6-t-mini`（轻量档，勿选）
   - `Configure...` — `model-configure-modal`
3. 点 `Thinking•Extended` 选中；composer 显示 `Extended` 按钮即已生效。

## 4. 注入长提示词（关键：base64 + 双模式注入）

> ⚠️ 提示词长、含双引号/中文，直接 `type` 会因 Windows 命令行解析失败。
> ⚠️ **编辑器有两种形态，注入方法完全不同**（2026-08-10 实测踩坑）：
> - 新版：真正编辑器是 `#prompt-textarea[contenteditable=true]` 的 **DIV**，`[name=prompt-textarea]` 是**隐藏 fallback textarea**（`offsetParent===null`）。→ 用 `execCommand('insertText')`。
> - 旧版：编辑器是 `<textarea>` 本身。→ 用 native value setter。
> **判定**：先查 `document.querySelector('[contenteditable=true]')`，存在即 contenteditable 模式。

在本地（PowerShell）：
```powershell
# 提取提示词（若在 markdown 代码块里）
$c = Get-Content "提示词文件.md" -Raw -Encoding UTF8
$m = [regex]::Match($c, '```\r?\n([\s\S]*?)\r?\n```'); $p = $m.Groups[1].Value
$b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p))

# 注入（eval 外层双引号、内部单引号）——contenteditable 模式（首选）
$js = "(()=>{const b=atob('$b');const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);const s=new TextDecoder().decode(u);const el=document.querySelector('#prompt-textarea[contenteditable=true]')||document.querySelector('[contenteditable=true]');el.focus();el.innerHTML='';document.execCommand('insertText',false,s);return JSON.stringify({len:el.innerText.length,tail:(el.innerText||'').slice(-30)});})()"
opencli browser <session> eval $js

# 若上面 len≈0（textarea 模式），改用 native setter：
$js2 = "(()=>{const b=atob('$b');const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);const s=new TextDecoder().decode(u);const el=document.querySelector('[name=prompt-textarea]');const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;setter.call(el,s);el.dispatchEvent(new Event('input',{bubbles:true}));return el.value.length;})()"
opencli browser <session> eval $js2
```

注入后校验（contenteditable 看 innerText / textarea 看 value），并确认**发送按钮出现**：
```js
(()=>{const ce=document.querySelector('[contenteditable=true]');const ta=document.querySelector('[name=prompt-textarea]');const send=document.querySelector('[data-testid=send-button]');return JSON.stringify({ceLen:ce?(ce.innerText||'').length:0,taLen:ta?(ta.value||'').length:0,sendBtn:!!send,disabled:send?send.disabled:null});})()
```
⚠️ 发送按钮（`[data-testid=send-button]`）不出现 = React 没感知内容（通常因为注入方式不对），此时发不出。

## 5. 发送 + 监控完成

- 发送：`eval` 点 `[data-testid=send-button]`。
- **生成状态判定**（后台轮询，每 10s 一次）：
  ```js
  (()=>{const gen=document.querySelector('[data-testid=stop-button],button[aria-label*=Stop]');
        const msgs=document.querySelectorAll('[data-message-author-role]');
        return JSON.stringify({stop:!!gen,roles:msgs.length});})()
  ```
  - `stop:true` = 生成中（Thinking·Extended 思考阶段较长，user 消息先出现、assistant 后渲染）
  - `stop:false` 且 `roles>=2`（出现 assistant）= 生成完成
- 提取回复：`extract` 拿整页 content，或遍历 `[data-message-author-role=assistant]` 取文本。

## 6. 落档

- 完整回复保存到 `docs/ai-advice/`（文件名含日期+问诊对象），关键结论提炼后更新对应方案/表格。
- 凭证值（authToken/JWT、API key）一律不落文件、不写仓库、不外发。

## 7. 已知问题与兜底（2026-08-10 实测）

### 7.1 含多个 GitHub 链接的提示词 → Deep Research 渲染失败 → 空回复
- **现象**：user 消息完整发出，assistant 消息 0 字符；页面出现搜索来源块（`:::` 列表）和 "Show more"；`stop` 按钮消失后无任何回答。
- **实测**：vip-19 实例，Extended×2 + Auto×1 三次全部空回复（提示词含 5 个 GitHub 链接）。判断为该实例对多链接提示词自动触发 Deep Research，但 research 结果渲染失败。
- **判定**：`eval` 检查 `[data-message-author-role=assistant]` 的 `innerText.length` 是否 0 + 页面有无搜索来源文本。
- **兜底**：**转 Claude**（见 03 手册）——claude.ai 无此问题，Sonnet 5 High 免费可用。

### 7.2 部分实例模型菜单打不开
- vip-12 等实例点击 Auto pill 后菜单不弹出（popover 渲染异常）。vip-19 重登后也可能偶发。
- **对策**：换健康账号重登，或直接用默认 Auto 模式（不强求 Extended）。

### 7.3 账号池会漂移
- 健康账号（isHealthy:true）名单随镜像站维护变化；已见 vip-15 由健康降为"受限"。
- 每次操作先读 `panelAccountList` 重新确认，勿依赖固定账号。

---


---

## 8. 详细步骤（2026-08-15 实测精化版，含全部踩坑细节）

> 上一版是「大概流程」。本节是逐步可复制的详细操作，含每个环节的确切命令/表达式与坑。执行时仍以页面实际为准（账号池/域名会变）。

### 8.1 完整流程一览（一步步照做）

**① 打开问答宝账号池**
```bash
node "D:\opencli-app\dist\src\main.js" browser n8hh7hyn open "https://ai.wendabao-f.net/?utm_source=hidden-ncn"
# 等待 5 秒（页面 SPA 加载）
```

**② 读账号池，选健康 Plus 账号**
```js
// eval：列出 isHealthy=true 且 badge=PLUS 的 carID（如 vip-11 / vip-19 / vip-48）
(()=>{const raw=localStorage.getItem('panelAccountList');if(!raw)return JSON.stringify({err:'no panel'});try{const list=JSON.parse(raw);const ok=list.filter(a=>a.isHealthy===true&&(a.badge||a.plan)==='PLUS').map(a=>({carID:a.carID,badge:a.badge||a.plan}));return JSON.stringify({total:list.length,healthy:ok.slice(0,6)})}catch(e){return JSON.stringify({err:e.message})}})()
```
> 选号原则：优先 isHealthy=true 的 Plus。账号池会漂移（上次健康下次可能失效），每次先读。

**③ localStorage 登录法导航到目标实例**
```js
// 替换 vip-11 为你选的账号。注意：此 URL 含 jwt，**不落盘、不写记忆、不外发**
(()=>{const t=localStorage.getItem('authToken');if(!t)return 'NO_TOKEN';location.href='https://vip-11.67673.live/api/v2/plus-login?account=vip-11&jwt='+encodeURIComponent(t);return 'NAVIGATING'} )()
```
> 导航后等 10-12 秒（页面重载慢），再 `browser state` 确认 URL 变为 `https://vip-11.67673.live/`。
> ⚠️ 若 state 报 `getAttribute null` = 页面还在加载，等几秒再查（手册附录已有）。

**④ 设置 Thinking•Extended（关键！模型菜单点击必须用完整事件序列）**

> ⚠️⚠️ **这是「点不动」的根因（2026-08-15 实测）**：ChatGPT 的模型菜单是自定义下拉框，监听 pointer/mouse down+up。**el.click() 或简单 dispatchEvent(click) 都不会弹菜单**（opencli 的 `click <ref>` 也常失败，因为它的 nativeClick 可能被 fallback 或坐标在文字上）。必须用 **pointerdown→mousedown→pointerup→mouseup→click 完整序列 + 真实坐标**，且目标要指向 **Auto 文字右侧的向下箭头 svg**（不是 Auto 文字本身）。

```js
// ① 点 Auto pill 里的箭头 svg（完整事件序列）
(()=>{const b=Array.from(document.querySelectorAll('button')).find(x=>x.querySelector('span')&&x.querySelector('span').textContent.trim()==='Auto');if(!b)return 'no auto';const svg=b.querySelector('svg');const el=svg||b;const r=el.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;const opts={bubbles:true,cancelable:true,composed:true,clientX:x,clientY:y,button:0,buttons:1,pointerId:1,pointerType:'mouse',isPrimary:true,view:window};for(const[type,Ctor]of[['pointerdown',PointerEvent],['mousedown',MouseEvent],['pointerup',PointerEvent],['mouseup',MouseEvent],['click',MouseEvent]]){el.dispatchEvent(new Ctor(type,opts))}return 'arrow clicked'})()
```

```js
// ② 等 3 秒后点 Thinking•Extended（同样用完整事件序列；testid=model-switcher-gpt-5-6-thinking）
(()=>{const el=document.querySelector('[data-testid=model-switcher-gpt-5-6-thinking]');if(!el)return 'not found';const r=el.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;const opts={bubbles:true,cancelable:true,composed:true,clientX:x,clientY:y,button:0,buttons:1,pointerId:1,pointerType:'mouse',isPrimary:true,view:window};for(const[type,Ctor]of[['pointerdown',PointerEvent],['mousedown',MouseEvent],['pointerup',PointerEvent],['mouseup',MouseEvent],['click',MouseEvent]]){el.dispatchEvent(new Ctor(type,opts))}return 'thinking selected'})()
```

```js
// ③ 验证 composer 已显示 Extended（= Thinking•Extended 生效，思考程度已是 Extended）
(()=>{const spans=Array.from(document.querySelectorAll('span')).filter(s=>s.textContent.trim()==='Extended'&&s.childElementCount===0);return JSON.stringify({extended:spans.length>0})})()
```

> 坑：部分实例（vip-19 等）模型菜单可能整体打不开（点了无反应）→ 换健康账号重登（手册 §7.2）。「有无 Auto pill」因实例而异：vip-11 有 pill，vip-13/48 可能没有（默认模型）。

**⑤ 注入提示词（base64 + contenteditable insertText）**

> ⚠️ 提示词尽量用**内嵌版**（把 GitHub 链接内容直接贴进正文，只留 1 个主链接）——**多链接提示词会触发 Deep Research 空回复**（手册 §7.1）：user 消息发出但 assistant 只有 "Show more"，0 字回复。内嵌版实测可靠。

```bash
# PowerShell：读提示词文件 → base64
$c = Get-Content "提示词文件.md" -Raw -Encoding UTF8
$b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($c))
```

```js
// eval 注入到 contenteditable（外层双引号、JS 内单引号；base64 串嵌入）
(()=>{const b=atob('BASE64');const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);const s=new TextDecoder().decode(u);const ce=document.querySelector('#prompt-textarea[contenteditable=true]')||document.querySelector('[contenteditable=true]');ce.focus();ce.innerHTML='';document.execCommand('insertText',false,s);return JSON.stringify({len:ce.innerText.length})})()
```
> 校验 len>0 且尾部正确；若 len=0 说明是 textarea 模式（少见），改用 native value setter（手册 §4）。

**⑥ 发送**
```js
(()=>{const s=document.querySelector('[data-testid=send-button]');if(s&&!s.disabled){s.click();return 'sent'};return JSON.stringify({send:!!s,disabled:s?s.disabled:null})})()
```

**⑦ 等待生成 + 提取回复（轮询脚本有坑，见 8.2）**

### 8.2 轮询/提取的坑（2026-08-15 实测）

- **轮询探针可能误判**：用 `[data-testid=stop-button]` 探针轮询时，若某次 eval 探针报错（execFileSync 抛异常被 catch），脚本会误跳过真正完成的瞬间；或 stop 按钮选择器不匹配导致一直显示生成中。**内容其实已生成**。
- **正确做法**：不要只信轮询的 stop 状态。等待一段时间后**直接提取 assistant 消息**确认：
```js
// 提取最后一条 assistant 完整文本（无内容 = 空回复/还在生成）
(()=>{const msgs=document.querySelectorAll('[data-message-author-role=assistant]');const last=msgs[msgs.length-1];return last?(last.innerText||last.textContent||'').trim():''})()
```
- **空回复判定**：assistant 长度 0 或只有 "Show more" + 引用标记（GitHub +N）= 空回复（Deep Research 触发）→ 换内嵌版提示词重试，或转 Claude。
- **推荐流程**：发送后直接 sleep 90-120 秒（Thinking•Extended 通常 2-5 分钟），再提取；若 0 字再等再试，不用复杂轮询。

### 8.3 opencli eval 传参引号规则（沿用 + 补充）

| 场景 | 正确写法 |
|------|---------|
| eval 传 JS | PowerShell **外层双引号**，JS **内部全部单引号**（选择器用 `'[...]'`） |
| JS 含双引号 | 会拆散参数，避免 |
| 页面加载中 state | 报 getAttribute null → 等几秒再 state |
| 长文本/复杂 JS | 一律写 .mjs 临时脚本用 execFileSync 调 opencli（比 PowerShell 内联可靠），用完删除 |
| 完整事件序列 | 模型菜单等自定义下拉必须 pointerdown/mousedown/pointerup/mouseup/click 全发，单 click 无效 |
