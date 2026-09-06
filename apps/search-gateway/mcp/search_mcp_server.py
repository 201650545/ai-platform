# -*- coding: utf-8 -*-
# ============================================================
# AI 搜索网关 MCP server —— 把 search_gateway(:3000) 的搜索能力封装成标准 MCP 工具，
# 供任何支持 MCP 的 Agent（TRAE / Claude Code / DeepSeek harness / opencode 等）直接调用。
#
# 暴露工具：
#   gateway.search       多 AI 搜索引擎并发检索，返回结构化正文 + 来源（引擎侧完成检索）
#   gateway.aggregate    搜索 → 内容池 → LLM 整理 → 生成 HTML 报告，返回报告地址 + 引擎状态
#   gateway.health       引擎会话连通性
#   gateway.history      搜索历史（可选，可降级）
#
# 运行方式（stdio，MCP 客户端用 command 拉起即可）：
#   <mcp_dir>\.venv\Scripts\python.exe <mcp_dir>\search_mcp_server.py
# ============================================================
import os
import sys
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 上游 search_gateway 地址，可用环境变量覆盖（LAN 部署时指向局域网 IP）
GATEWAY_BASE = os.environ.get(
    "SEARCH_GATEWAY_BASE", os.environ.get("SEARCH_GATEWAY_URL", "http://127.0.0.1:3000")
)
DEFAULT_TIMEOUT = float(os.environ.get("SEARCH_GATEWAY_TIMEOUT", "120"))

mcp = FastMCP("AI 搜索网关", instructions=(
    "封装本地 AI 搜索网关（元宝/Kimi/秘塔/豆包等真实 AI 搜索引擎并发检索）的能力。"
    "search 返回各引擎结构化回答与来源，适合让 Agent 自行加工整理；"
    "aggregate 让网关完成『搜索→内容池→LLM 整理→HTML 报告』整条链路后返回报告地址。"
    "health 用于探测引擎会话是否就绪。"
))


def _client():
    # trust_env=False：本地网关直连，避免读到 Windows 系统代理把 localhost 请求转成 502
    return httpx.Client(base_url=GATEWAY_BASE, timeout=DEFAULT_TIMEOUT, trust_env=False)


@mcp.tool()
def search(
    query: str,
    engines: Optional[str] = None,
) -> str:
    """用多家真实 AI 搜索引擎并发检索一个问题，返回各引擎的回答正文（结构化 json）与来源 URL。

    - query: 要搜索/检索的问题（中文优先，引擎为国内 AI 搜索）。
    - engines: 可选，用逗号分隔的引擎 id 子集（yuanbao/kimi/metaso/doubao），默认全部。
    """
    params = {"q": query}
    if engines:
        params["engines"] = engines
    try:
        with _client() as c:
            r = c.get("/api/search_json", params=params)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        return f"{{'status': 'err', 'error': '无法连接搜索网关 {GATEWAY_BASE}：{e}'}}"
    except Exception as e:  # noqa: BLE001
        return f"{{'status': 'err', 'error': '{e}'}}"


@mcp.tool()
def aggregate(query: str, engines: Optional[str] = None) -> str:
    """整条『搜索 → 内容池 → LLM 整理 → HTML 报告』链路。返回 run_id、HTML 报告地址与各引擎状态（不内联正文）。

    - query: 检索问题。
    - engines: 可选，逗号分隔的引擎子集。
    """
    params = {"q": query}
    if engines:
        params["engines"] = engines
    try:
        with _client() as c:
            r = c.get("/api/search_aggregate", params=params)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        return f"{{'status': 'err', 'error': '无法连接搜索网关 {GATEWAY_BASE}：{e}'}}"
    except Exception as e:  # noqa: BLE001
        return f"{{'status': 'err', 'error': '{e}'}}"


@mcp.tool()
def health() -> str:
    """探测 4 大 AI 搜索引擎会话的连通状态（connected / disconnected）。"""
    try:
        with _client() as c:
            r = c.get("/api/health", timeout=15)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        return f"{{'status': 'err', 'error': '无法连接搜索网关 {GATEWAY_BASE}：{e}'}}"
    except Exception as e:  # noqa: BLE001
        return f"{{'status': 'err', 'error': '{e}'}}"


@mcp.tool()
def history(limit: int = 20) -> str:
    """返回最近 N 条搜索历史（q + 时间 + 引擎结果摘要）。网关未记录时可能为空。"""
    try:
        with _client() as c:
            r = c.get("/api/history", params={"limit": max(1, min(int(limit), 100))}, timeout=15)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        return f"{{'status': 'err', 'error': '无法连接搜索网关 {GATEWAY_BASE}：{e}'}}"
    except Exception as e:  # noqa: BLE001
        return f"{{'status': 'err', 'error': '{e}'}}"


if __name__ == "__main__":
    # stdio 模式：MCP 客户端通过命令行拉起本进程
    mcp.run(transport="stdio")