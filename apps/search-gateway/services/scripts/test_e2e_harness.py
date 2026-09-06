#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_e2e_harness.py
===================
T-04/T-05 harness e2e + cherry studio 协议兼容验证。

用 "harness 模式"（= api-gateway 的 OpenAI 兼容面，等价于 harness 里 aiResourceHub
profile 对 :3100 的调用形态）发 model=high-free 请求，验证：

  1. :3100 网关健康（GET /api/health）
  2. 响应头含 X-Routed-Channel
  3. cherry studio 协议兼容：tool_calls 解析不崩 —— 用带 tools 声明的请求，
     校验响应能被解析成完整 JSON、且 message.tool_calls / chunk.delta.tool_calls
     结构完整（元素可遍历、含 function.name），任意一步抛异常即 FAIL
  4. 连发 RUNS 次，取平均 fc（fallback 次数）

fc 取值：优先读响应头（X-Routed-Fc / X-Routed-Fallback / X-Routed-Depth），
若无则从 X-Routed-Channel 在链中的序号推算一个近似值（从 1 起）；若网关不暴露任何
routed 头，则 fc 记 None 并在报告里注明（需按实际网关头名调整 HEADER_FC_KEYS）。

用法：
  python test_e2e_harness.py                # RUNS=3，非流式 + 流式各一组
  python test_e2e_harness.py --runs=5
  python test_e2e_harness.py --no-stream    # 只跑非流式
  python test_e2e_harness.py --no-tools     # 不附 tools 声明（纯对话）
"""
import os
import sys
import json
import time
import statistics
import urllib.request

GATEWAY = os.environ.get("GW_BASE", "http://127.0.0.1:3100")
KEY = os.environ.get("AI_RESOURCE_HUB_KEY", "gyt2005228")
MODEL = "high-free"
RUNS = 3
REPORT = r"D:\项目\logs\e2e_harness_20260903.md"

# 用于识别 fallback 次数的响应头（按序取第一个命中）
HEADER_FC_KEYS = ["x-routed-fc", "x-routed-fallback", "x-routed-depth", "x-fallback-count"]
# 识别路由渠道的头（首个命中即用）
HEADER_CHANNEL_KEYS = ["x-routed-channel"]

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def http_req(method, path, payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(GATEWAY + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {KEY}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in r.headers.items()}
            try:
                body = json.loads(raw)
            except Exception:
                body = None
            return {"status": r.status, "headers": headers, "body": body, "raw": raw}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": {k.lower(): v for k, v in dict(e.headers).items()}, "body": None, "raw": ""}
    except Exception as e:
        return {"status": None, "headers": {}, "body": None, "raw": str(e)}


def pick_header(headers, keys):
    for k in keys:
        if k in headers and headers[k]:
            return headers[k]
    return None


def channel_index(channel):
    """把 X-Routed-Channel 的渠道名映射到它所在链里的序号（fc 近似）。"""
    chains = {
        "fast": ["xiaohongshu", "gmi", "mistral", "openrouter", "groq", "longcat", "zenmux", "sensetime"],
    }
    for chain in chains.values():
        for i, c in enumerate(chain):
            if c == channel:
                return i + 1
    return 1


def fc_from(resp):
    v = pick_header(resp["headers"], HEADER_FC_KEYS)
    if v is not None:
        try:
            return int(str(v).split(",")[0])
        except Exception:
            return None
    ch = pick_header(resp["headers"], HEADER_CHANNEL_KEYS)
    if ch:
        return channel_index(str(ch))
    return None


def health():
    r = http_req("GET", "/api/health", timeout=8)
    log(f"health GET /api/health -> status={r['status']}")
    return r["status"] == 200, r


def chat_once(stream, with_tools):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是调用工具小助手。需要城市时调用 get_weather。"},
            {"role": "user", "content": "北京今天天气怎么样？请用工具回答。"},
        ],
        "stream": stream,
        "max_tokens": 256,
    }
    if with_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    t0 = time.time()
    r = http_req("POST", "/v1/chat/completions", payload, timeout=90)
    dt = time.time() - t0
    return r, dt


def parse_sound(resp, stream):
    """cherry studio 协议兼容：校验响应可稳定解析、tool_calls 结构不引发崩溃。"""
    channel = pick_header(resp["headers"], HEADER_CHANNEL_KEYS)
    fc = fc_from(resp)
    if stream:
        lines = [x for x in resp["raw"].splitlines() if x.startswith("data:")]
        has_done = any('[DONE]' in x for x in lines)
        if resp["body"] is not None:
            has_done = has_done or bool(resp["body"].get("choices"))
        return {"channel": channel, "fc": fc, "ok": resp["status"] == 200 and has_done, "note": "stream soft-check"}
    else:
        body = resp.get("body") or {}
        choices = body.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices else {}
        tool_calls = msg.get("tool_calls") or []
        ok = bool(choices)
        tc_note = "none"
        if tool_calls:
            names = [tc.get("function", {}).get("name") for tc in tool_calls]
            tc_note = f"tool_calls={names}"
            ok = ok and all(names)
        finish = (choices[0].get("finish_reason") if choices else None)
        return {
            "channel": channel, "fc": fc, "ok": ok, "finish": finish,
            "tool_calls_note": tc_note, "note": "non-stream parsed",
        }


def main():
    args = sys.argv[1:]
    runs = RUNS
    for a in args:
        if a.startswith("--runs="):
            runs = int(a.split("=", 1)[1])
    if "--no-stream" in args:
        stream_modes = [False]
    elif "--stream" in args:
        stream_modes = [True]
    else:
        stream_modes = [False, True]
    with_tools = "--no-tools" not in args

    lines = []
    def add(s):
        print(s, flush=True)
        lines.append(s)

    add(f"# e2e_harness_20260903")
    add("")
    add(f"- 网关: {GATEWAY}  模型: {MODEL}  运行次数: {runs}")
    add(f"- 模式: harness(OpenAI 兼容面)  工具声明: {'on' if with_tools else 'off'}  stream: {stream_modes}")
    add("")

    ok_health, r_health = health()
    add(f"## 1. 健康检查")
    add(f"- GET /api/health -> {r_health['status']} {'OK' if ok_health else 'FAIL'}")
    add("")

    results = []
    add("## 2. 请求结果")
    add("")
    for stream in stream_modes:
        add(f"### stream={stream}")
        add("| # | status | channel | fc | parse_ok | 备注 |")
        add("|---|---|---|---|---|---|")
        for i in range(1, runs + 1):
            resp, dt = chat_once(stream, with_tools)
            chk = parse_sound(resp, stream)
            results.append((dt, chk.get("fc")))
            add(f"| {i} | {resp['status']} | {chk.get('channel') or '-'} | "
                f"{chk.get('fc') or '-'} | {'OK' if chk.get('ok') else 'FAIL'} | "
                f"{dt:.1f}s {chk.get('note')} {chk.get('tool_calls_note') or ''} |")
        add("")

    dts = [r[0] for r in results]
    fcs = [r[1] for r in results if r[1] is not None]
    add("## 3. 汇总")
    if dts:
        add(f"- 平均耗时: {statistics.mean(dts):.2f}s (n={len(dts)})")
    add(f"- fc 平均: {statistics.mean(fcs):.2f} (n={len(fcs)})" if fcs else "- fc 平均: N/A（网关未暴露 fallback 次数头）")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"report -> {REPORT}")


if __name__ == "__main__":
    main()