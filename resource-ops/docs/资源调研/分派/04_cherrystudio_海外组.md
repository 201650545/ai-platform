# 任务包 4 · cherry studio · 海外组

> 派发方：主 Agent（opencode）｜日期：2026-08-10
> 背景仓库：`D:\项目\ai-resource-hub`
> 交接书（执行规则主文档）：`docs/资源调研/调研任务交接_2026-08-10.md`（**先读**）
> 总览（回写规范/进度登记）：`docs/资源调研/分派/00_总览_2026-08-10.md`

## 一、你负责的平台（4 个）

| # | 平台 | 说明 |
|---|------|------|
| 1 | GitHub Models | `/marketplace/models` 已 404，需找正确入口（Copilot 内 Models / github.com/settings/copilot） |
| 2 | Google Colab | 谷歌登录，免费 T4 GPU |
| 3 | Together.ai | 谷歌登录，开源模型免费档 |
| 4 | Mistral La Plateforme | 谷歌登录，新户免费额度 |

## 二、执行环境

- opencli 控制已登录 Chrome（profile `n8hh7hyn`）：
  - `opencli browser n8hh7hyn open <url>` — 打开页面
  - `opencli browser n8hh7hyn state` — 看页面交互元素（找登录按钮/账号菜单）
  - `opencli browser n8hh7hyn extract` — 提取页面 markdown（判断登录态时用 PowerShell 过滤关键字更省：`Select-String -Pattern "Sign in|Profile|Settings"`）
  - `opencli profile list` — 查 profile
- 判断登录态：页面出现「Sign in / 登录」= 未登录；出现用户名/账号菜单/Profile/Settings = 已登录

## 三、执行规则（郭老师三条指令，必须遵守）

1. **能谷歌登录的平台 → 自动点谷歌登录**（Google OAuth，点后确认是否登录成功）
   - 本组 4 个平台均可走 Google OAuth，Chrome 已登录 Google → 应能自动通过
2. **需要手机号 / 微信扫码 → 不自动操作**，记录到「待办」
3. **有账号密码登录 → 备注提示郭老师**设置账号密码

> ⚠️ **并发注意**：海外组与包 5 共用同一已登录 Chrome，别与包 5 同时开浏览器抢 tab。

## 四、每平台记录格式（写回自己文件）

```
## 平台 1 · GitHub Models ✅/❌
- 平台：URL
- 登录态：✅/❌（判断依据）
- 登录方式：Google OAuth / 手机短信 / 微信扫码 / 账号密码
- 免费额度现状：具体额度/余额/代金券
- 价值：对资源库有什么用
- 待办：需要人做什么
```

## 五、结果回写

- **只写**：`docs/资源调研/结果/结果_cherrystudio.md`（追加平台记录）
- 完成后在 `docs/资源调研/分派/00_总览_2026-08-10.md`「进度登记表」你的行打 ✅

## 六、完成后汇报（四段式，写在结果文件末尾）

1. **模块 × 验收项**：探测了哪些平台、每平台是否完成
2. **变更清单**：写了哪个结果文件、改了什么
3. **验证**：哪些已登录、哪些待郭老师登录
4. **已知偏差**：没跑通的平台、猜测、待确认点
