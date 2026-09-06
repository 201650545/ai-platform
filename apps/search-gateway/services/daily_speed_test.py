# -*- coding: utf-8 -*-
"""每日渠道测速（daily speed test）：对编排组内全部 (渠道, 模型) 对实测 token 速度。

由 Windows 计划任务每天 00:05 触发，独立于 :3100 网关进程运行；
复用 channels._urlopen（含渠道代理），但直接打上游、不走 chat_completion，
不写入 rate_limit/quota 台账，不污染真实用量（与 capability_verify 同一原则）。

产出：
  data/search_gateway/speed_tests/YYYY-MM-DD.json   当日快照（按编排组聚类）
  data/search_gateway/speed_tests/history.jsonl     逐行追加，供趋势页读取

每条记录：{channel, model, groups, ok, ttft_s, gen_s, tok_s, total_s, completion_tokens, error}
  ttft_s  = 发请求到首字节到达（非流式近似为总连接+排队+生成时长，记 total 减半近似不可靠，故
            非流式只记 total；对支持 stream 的渠道另测一次 stream 版取真实 TTFT）
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import channels  # noqa: E402

DATA_DIR = channels.DATA_DIR
OUT_DIR = os.path.join(DATA_DIR, "speed_tests")

# 测速请求参数：小而稳——max_tokens 控制时长，temperature 0 减少随机
PING = [{"role": "user", "content": "用中文写一句关于秋天的话，至少30个字。"}]
MAX_TOKENS = 120
TIMEOUT = 60


def iter_pairs():
    """从 routing.json + unified_models.json 取 (channel, model, group) 三元组，按 (渠道,模型) 去重。"""
    unified = channels.load_unified()
    routing = channels.load_routing().get("routing", {})
    pairs = {}
    for gname, g in unified.items():
        members = g.get("members") or {}
        r = routing.get(gname) or {}
        order = r.get("order") or list(members.keys())
        disabled = set(r.get("disabled") or [])
        for cid in order:
            if cid in disabled or cid not in members:
                continue
            key = (cid, members[cid])
            pairs.setdefault(key, {"channel": cid, "model": members[cid], "groups": []})["groups"].append(gname)
    return list(pairs.values())


def speed_test_one(channel_id, model, stream=False):
    """单次测速。返回指标 dict。流式取真实 TTFT；非流式只记总时长。"""
    ch = channels.CHANNELS.get(channel_id) or {}
    url = (ch.get("base_url") or "").rstrip("/") + "/chat/completions"
    if not url.startswith("http"):
        return {"ok": False, "error": "渠道无 base_url"}
    payload = {
        "model": model, "messages": PING, "max_tokens": MAX_TOKENS,
        "temperature": 0, "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + (channels.get_key(channel_id) or ""),
        "User-Agent": ch.get("ua", "unified-ai-gateway/1.0"),
    }, method="POST")

    t0 = time.perf_counter()
    ttft = None
    usage_tokens = None
    n_chars = 0
    try:
        with channels._urlopen(req, timeout=TIMEOUT, channel_id=channel_id) as resp:
            if stream:
                # SSE 流：首个含内容的 chunk 计 TTFT；usage 行取 completion_tokens
                buf = b""
                while True:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if chunk in (b"\n", b"\r"):
                        line = buf.strip()
                        buf = b""
                        if line.startswith(b"data:") and ttft is None:
                            ttft = time.perf_counter() - t0
                        if line.startswith(b"data:") and b'"usage"' in line:
                            try:
                                usage_tokens = (json.loads(line[5:].strip()).get("usage") or {}).get("completion_tokens")
                            except Exception:  # noqa: BLE001
                                pass
                        if line == b"data: [DONE]":
                            break
            else:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                content = msg.get("content") or ""
                if not content and isinstance(msg.get("reasoning_content"), str):
                    content = msg["reasoning_content"]  # 推理型模型正文常落在 reasoning_content
                n_chars = len(content)
                usage_tokens = (data.get("usage") or {}).get("completion_tokens")
        total = time.perf_counter() - t0
        if usage_tokens is None:
            usage_tokens = max(1, n_chars // 2)  # 无 usage 时按 2 字符/token 粗估
        tok_s = round(usage_tokens / total, 1) if total > 0 and (stream or n_chars) else None
        return {
            "ok": True,
            "ttft_s": round(ttft, 2) if ttft is not None else None,
            "total_s": round(total, 2),
            "tok_s": tok_s,
            "completion_tokens": usage_tokens,
        }
    except urllib.error.HTTPError as he:
        detail = ""
        try:
            detail = he.read().decode("utf-8", "ignore")[:200]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"HTTP {he.code} {detail}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def run_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs = iter_pairs()
    results = []
    print(f"[speed] {date.today()} 共 {len(pairs)} 个 (渠道,模型) 对")
    for p in pairs:
        cid, model = p["channel"], p["model"]
        rec = {"channel": cid, "model": model, "groups": p["groups"], "ts": time.strftime("%H:%M:%S")}

        # 先非流式测吞吐；再流式测 TTFT（流式渠道大多支持；失败不致命）
        m1 = speed_test_one(cid, model, stream=False)
        rec.update(m1)
        if m1.get("ok"):
            m2 = speed_test_one(cid, model, stream=True)
            if m2.get("ok") and m2.get("ttft_s") is not None:
                rec["ttft_s"] = m2["ttft_s"]
            # 吞吐以非流式为准（流式含首包等待，偏高）

        results.append(rec)
        mark = "OK" if rec.get("ok") else "FAIL"
        tok = rec.get("tok_s")
        ttft = rec.get("ttft_s")
        print(f"  [{mark}] {cid:<14} {model:<44} tok_s={tok} ttft={ttft} total={rec.get('total_s')} {rec.get('error','')}")

    snapshot = {
        "date": str(date.today()),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "max_tokens": MAX_TOKENS,
        "results": results,
    }
    day_path = os.path.join(OUT_DIR, f"{date.today()}.json")
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "history.jsonl"), "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({"date": str(date.today()), **r}, ensure_ascii=False) + "\n")
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"[speed] 完成：{ok_n}/{len(results)} 成功 → {day_path}")
    return snapshot


if __name__ == "__main__":
    run_all()
