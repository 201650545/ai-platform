# 操作手册 02 · Open CLI 浏览器操控

> 用途：所有执行 Agent 用 Open CLI 操控已打开的日常 Chrome（永涛登录态）做调研/验证/领取
> 版本：2026-08-10 实测 ｜ opencli v1.8.6（@jackwener/opencli，npm 全局）｜ 浏览器扩展 v1.0.22

---

## 1. 命令结构（新版，session 是必需位置参数）

```bash
opencli browser <session> <command> [options]
```

- 复用**同一个 session 名**跨多次调用 → 保持标签页/状态存活
- 换一个 session 名 → 隔离另一路并行浏览器操作
- 例：`opencli browser work open <url>` / `opencli browser work state`

## 2. 子命令速查

| 命令 | 用途 | 例 |
|------|------|-----|
| `open <url>` | 打开 URL | `opencli browser work open https://replicate.com` |
| `state` | 页面结构：URL/title/交互元素（带 `[N]` 编号） | `opencli browser work state` |
| `extract` | 页面转 markdown（长页分段） | `opencli browser work extract` |
| `eval <js>` | 页面执行 JS，返回 JSON | `eval "JSON.stringify({a:1})"` |
| `find --text/--testid/--css <x>` | 语义定位，返回 `ref` 编号 | `find --text "Sign in"` / `find --testid send-button` |
| `click <target>` | 点击（传 find 的 ref 编号或选择器） | `click 42` |
| `type <target> <text>` | 点选并输入 | `type` 长文本勿用（见坑位） |
| `fill` | 精确设置输入值并校验 | `fill` |
| `keys <key>` | 按键 | `keys Enter` |
| `tab list/new/close` | 标签管理（list 只列会话绑定标签） | `tab new` 开新标签不覆盖 |
| `get url/title/text` | 页面属性 | `get url` / `get title` |
| `wait <type> <value>` | 等待选择器/文本/时间 | `wait text "Success"` |
| `screenshot [path]` | 截图 | `screenshot shot.png` |
| `network` | 抓网络请求 shape | `network` |
| `bind/unbind` | 绑定/解绑当前 Chrome 标签 | 首次使用 `bind` |
| `close` | 释放会话标签租约 | `close` |

## 3. 标准工作流

### 3.1 判断登录态
```bash
opencli browser <s> open <url>          # 打开平台
opencli browser <s> state               # 看页面元素
opencli browser <s> extract | Select-String -Pattern "Sign in|Profile|Settings"   # PowerShell 过滤
opencli browser <s> eval "<js>"         # 页面 JS（点按钮等）
```

### 3.2 定位并点击元素
1. `state` 看交互元素编号，或 `find --text "..."` 语义定位
2. `click <ref>` 点击；返回 `{clicked:true}` 即成功

### 3.3 注入长文本（base64 + native setter）
⚠️ 长文本含双引号/中文，`type` 会因 Windows 命令行解析失败。用 base64：
```powershell
$b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($text))
$js = "(()=>{const b=atob('$b');const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);const s=new TextDecoder().decode(u);const el=document.querySelector('[name=prompt-textarea]');const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;setter.call(el,s);el.dispatchEvent(new Event('input',{bubbles:true}));return el.value.length;})()"
opencli browser <s> eval $js
```
（textarea 是 React 受控组件 → native setter + input 事件；execCommand 只对 contenteditable 有效）

### 3.4 后台监控等待完成
用 `run_in_background` 轮询：
```powershell
for($i=0;$i -lt 120;$i++){ Start-Sleep 10; $r = opencli browser <s> eval "<完成判定JS>" 2>$null; Write-Output "t=$i $r"; if($r -match "<完成特征>"){ break } }
```
- **GPT 镜像站**：`stop` 按钮消失 + `[data-message-author-role]` 出现 assistant
- **Claude**：`document.body.innerText.includes("Claude is responding")` 连续 3 次 false

## 4. 关键坑位（实测）

| 坑 | 表现 | 对策 |
|----|------|------|
| **eval 引号** | JS 含双引号 → `too many arguments` / `Invalid left-hand side` | PowerShell **外层双引号**、JS **内部全单引号**；选择器用 `'[attr=x]'` |
| **长文本 type** | Windows 命令行解析失败 | 一律 base64 + eval 注入 |
| **页面加载中 state** | `getAttribute null` 报错 | 等 3–8 秒再 state |
| **tab list 只见绑定标签** | `window.open` 弹的新标签不在列表 | 用 localStorage 构造 URL 直接导航（见 01 手册 §2） |
| **两会话共用一标签** | 互相覆盖打断流式 | 并行任务用 `tab new` 或独立 session |
| **session 失效** | 状态停在 about:blank | 重新 `open` 目标 URL 恢复 |

## 5. 执行边界（调研/验证类任务通用）

- 能 **Google 登录** → 自动点（OAuth 弹窗用 eval 模拟点击，见各站登录技巧）
- 需**手机号 / 微信扫码** → 不自动操作，记入「待永涛登录清单」（平台名+方式）
- 有**账号密码** → 备注提示永涛设置（避免短信验证收费）
- **凭证值**（token/key/JWT）→ 绝不写仓库/文件，需用时到对应 dashboard 复制
- 每平台记录：登录态/登录方式/免费额度/价值/待办，写回验证记录
- 完成后**四段式汇报**：模块×验收项 / 变更清单 / 验证 / 已知偏差
