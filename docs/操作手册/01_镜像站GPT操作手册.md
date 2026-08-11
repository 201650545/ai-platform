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

## 4. 注入长提示词（关键：base64 + native setter）

> ⚠️ 提示词长、含双引号/中文，直接 `type` 会因 Windows 命令行解析失败。
> ⚠️ `prompt-textarea` 是 `<textarea>`（React 受控），`execCommand('insertText')` 对它无效，必须用 **native value setter + input 事件**。

在本地（PowerShell）：
```powershell
# 提取提示词（若在 markdown 代码块里）
$c = Get-Content "提示词文件.md" -Raw -Encoding UTF8
$m = [regex]::Match($c, '```\r?\n([\s\S]*?)\r?\n```'); $p = $m.Groups[1].Value
$b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p))

# 注入（eval 外层双引号、内部单引号）
$js = "(()=>{const b=atob('$b');const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);const s=new TextDecoder().decode(u);const el=document.querySelector('[name=prompt-textarea]');const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;setter.call(el,s);el.dispatchEvent(new Event('input',{bubbles:true}));return el.value.length;})()"
opencli browser <session> eval $js   # 返回 字符长度 即成功
```

注入后校验：
```js
(()=>{const el=document.querySelector('[name=prompt-textarea]');return JSON.stringify({head:el.value.slice(0,40),tail:el.value.slice(-40)});})()
```

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

---

## 附：opencli eval 传参引号规则（本次踩坑）

| 场景 | 正确写法 |
|------|---------|
| eval 传 JS | PowerShell **外层双引号**，JS **内部全部单引号**（选择器用 `'[...]'`） |
| JS 含双引号 | 会拆散参数（报 `too many arguments` / `Invalid left-hand side`），避免 |
| 页面加载中 state | 报 `getAttribute null` → 等几秒再 `state` |
| 长文本 | 一律 base64，勿直接塞命令行 |
