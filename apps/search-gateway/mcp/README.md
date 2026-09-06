# AI 搜索网关 MCP 接入说明

把 `search_gateway(:3000)` 的真实 AI 搜索能力封装成标准 MCP server，任何支持 MCP 的 Agent 都能直接调用——
在 Agent 里让 AI 自己「搜索 → 加工整理 → 给你看」，你不用手动开网页搜。

## 结构

```
mcp/
├── search_mcp_server.py   # MCP server 本体，暴露 4 个工具
├── _probe.py              # 自检脚本（python .venv\Scripts\python.exe _probe.py）
├── .venv/                 # 独立虚拟环境（Python 3.12，装了 mcp<2 + httpx）
├── mcp_config.json        # 通用注册配置（TRAE / Claude Code / Cursor 共用同一段）
└── README.md
```

## 暴露的工具

| 工具 | 作用 | 适用场景 |
|---|---|---|
| `search` | 4 家真实 AI 搜索引擎（元宝/Kimi/秘塔/豆包）并发检索，返回结构化正文+来源 | Agent 自行整理 |
| `aggregate` | 搜索→内容池→LLM 整理→HTML 报告整条链路，返回报告地址 | 想要成品报告 |
| `health` | 探测引擎会话连通性 | 排查 |
| `history` | 最近搜索历史 | 追溯 |

## Agent 怎么接

**通用（TRAE / Claude Code / Cursor / 任意 MCP 客户端）**——把 `mcp_config.json` 里的那段
`mcpServers` 注册进你的 Agent 的 MCP 配置即可（TRAE 在设置→MCP 里加自定义 server，
command 填 venv 的 python，args 填本 server 脚本路径）。

**作为 OpenAI 兼容 base_url（DeepSeek harness / Pi / Chatbox 等，不走 MCP）**：
```
Base URL : http://127.0.0.1:3000/v1
Model    : yuanbao-search     # 元宝真实检索，带引用
API Key  : 任意填写
```

## 运行前提

本 MCP 只是「转发层」，真正干活的 `search_gateway` 要在监听 :3000，且 4 个引擎浏览器会话已登录。
先 `python search_gateway.py`（或经 runtime.cli 启停）起来，`health` 全绿后再让 Agent 调搜索。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SEARCH_GATEWAY_BASE` | `http://127.0.0.1:3000` | 网关地址；局域网部署时指到 `http://<局域网IP>:3000` |

## 重装依赖（万一 .venv 坏）

```
"C:\Users\郭永涛\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install "mcp[cli]<2" httpx
```