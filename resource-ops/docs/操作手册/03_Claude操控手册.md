# 操作手册 03 · Claude（Anthropic）操控

> 用途：用 Claude.ai（Anthropic 官网）免费版 Claude Sonnet 5 做第二意见/交叉校验
> 版本：2026-08-10 实测 ｜ 账号：XiaoGuo（已绑定 GitHub，Free plan）｜ GitHub 已绑定可免登录提问

---

## 1. 打开方式（关键：新标签，不覆盖）

```bash
opencli browser claude open "https://claude.ai"        # 首次打开
opencli browser claude tab new                         # 后续：开新标签，避免覆盖其他站
opencli browser claude select <page>                   # 切到目标标签
```

⚠️ **不要**在一个正在流式输出的标签（如 GPT 镜像站）里直接 open claude.ai——会覆盖并打断原会话。用 `tab new` 开独立标签。

## 2. 模型与思考程度

- 免费版可用：**Claude Sonnet 5**（High 思考程度可开）
- 进入 claude.ai 后，确认模型选择器已选 Sonnet 5；思考程度（effort）调 High
- 提示词用**链接式完整版**（给 GitHub 仓库/文件 URL 让它实读，而非内嵌摘要）

## 3. 提问

- 粘贴问诊提示词到输入框（长文本用 base64+eval 注入，规则同 01 手册 §4）
- 提示词末尾注明输出格式（结论/建议/风险/实施步骤/需确认）

## 4. 监控完成（Claude 专属判定）

⚠️ claude.ai 的对话区**不在 `<main>`** 里，`extract` 因侧边栏动态内容永远不稳定，不能用 total_chars 判定。

完成判定用 body 文本：
```js
(()=>({responding:document.body.innerText.includes("Claude is responding")}))()
```
- 轮询每 5–10s：`responding:true` = 还在生成
- **连续 3 次 `responding:false`** = 生成完成

## 5. 提取回复 + 落档

- `extract` 拿整页 content，从 "You said:" 截到免责声明区间
- 完整回复保存到 `docs/ai-advice/`（文件名含日期+对象），关键结论提炼后更新方案

---

## 附：Anthropic 小任务要点（郭老师原话）

- "测 Claude Sonnet 5，免费，思考程度开高"
- "GitHub 已经绑定了，你直接提问"
- "提完要开新的标签，不要覆盖原有标签"
