# -*- coding: utf-8 -*-
"""Groq 全目录探针：catalog + access + billing + perf 实测 → run 文件。

与 probe_cloudflare 同架构（probe_reducer 单写者）：
- catalog：GET /openai/v1/models（免费返回全量，0 消耗）
- access/billing/perf：每模型一次真实 chat 调用（TPM/RPM 免费档消耗极小）
- 预算闸：按"次"记（免费档 1000 次/天），单轮全目录 ≈ 1 次/模型
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channels  # noqa: E402  复用 DATA_DIR + keys
import probe_reducer  # noqa: E402

KEY = (channels.load_channels().get("keys") or {}).get("groq", "") \
    if hasattr(channels, "load_channels") else None
if not KEY:
    with open(os.path.join(channels.DATA_DIR, "channels.json"), encoding="utf-8") as f:
        KEY = (json.load(f).get("keys") or {}).get("groq", "")
BASE = "https://api.groq.com/openai/v1"

BUDGET_FILE = os.path.join(probe_reducer.DATA_DIR, "probe_budget_groq.json")
BUDGET_CALLS_PER_DAY = 60  # 探针预算：60 次调用/天（免费档 1K 次/天的 6%）
PROBE_PROFILE = "chat-120-v1"
PROMPT = "Count from 1 to 40, one number per line, nothing else."

# 探测白名单：目录可能含 whisper/tts/guard 等非 chat 模型，只探这些 kind
CHAT_PATTERNS = ("whisper", "tts", "guard", "prompt-guard", "embed", "playai",
                 "distil-whisper", "annotated", "orpheus")


def is_chat_model(mid):
    low = mid.lower()
    return not any(p in low for p in CHAT_PATTERNS)


def _op():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _headers(extra=None):
    # Groq 前置 CF 挡无 User-Agent 请求（403），必须带 UA
    h = {"Authorization": f"Bearer {KEY}", "User-Agent": "groq-probe/1.0"}
    h.update(extra or {})
    return h


def _budget_check(n=1):
    """记账式预算闸：按次计。"""
    st = probe_reducer._load_json(BUDGET_FILE, {})
    today = time.strftime("%Y-%m-%d")
    if st.get("date") != today or st.get("channel") != "groq":
        st = {"date": today, "channel": "groq", "spent": 0}
    if st["spent"] >= BUDGET_CALLS_PER_DAY:
        return False, st
    st["spent"] += n
    probe_reducer._atomic_write_json(BUDGET_FILE, st)
    return True, st


def fetch_catalog():
    req = urllib.request.Request(f"{BASE}/models", headers=_headers())
    with _op().open(req, timeout=30) as r:
        d = json.load(r)
    return [m.get("id") for m in (d.get("data") or []) if m.get("id")]


def probe_access(model):
    """一次真实调用测 access + perf（Groq 免费档不按 token 计费，记 TPM 即可）。"""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 200, "temperature": 0,
    }).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body,
                                 headers=_headers({"Content-Type": "application/json"}))
    t0 = time.time()
    try:
        with _op().open(req, timeout=90) as r:
            d = json.load(r)
        dt_ms = (time.time() - t0) * 1000
        u = d.get("usage", {}) or {}
        out_tok = u.get("completion_tokens") or 0
        in_tok = u.get("prompt_tokens")
        tok_s = round(out_tok / (dt_ms / 1000), 1) if dt_ms > 0 and out_tok else None
        return {"ok": True, "status": r.status, "in_tok": in_tok, "out_tok": out_tok,
                "tok_s": tok_s, "ms": round(dt_ms)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code,
                "err": e.read().decode("utf-8", "replace")[:160]}
    except Exception as e:
        return {"ok": False, "status": None, "err": f"{type(e).__name__}: {e}"[:160]}


def main(dry_run=False):
    try:
        catalog = fetch_catalog()
    except Exception as e:
        print(f"catalog fetch failed: {e}")
        return
    print(f"catalog: {len(catalog)} models ({sum(1 for m in catalog if is_chat_model(m))} chat)")
    budget = probe_reducer._load_json(BUDGET_FILE, {})
    today = time.strftime("%Y-%m-%d")
    spent = budget.get("spent", 0) if budget.get("date") == today else 0
    print(f"budget: {spent}/{BUDGET_CALLS_PER_DAY} calls spent today")

    st = {"spent": spent}
    runs = 0
    for m in catalog:
        chat = is_chat_model(m)
        # catalog run：全目录都记（0 消耗）
        if not dry_run:
            probe_reducer.emit_run("groq", m, "catalog", {"state": "listed", "http_status": 200},
                                   writer="groq_catalog_probe")
            runs += 1
        if not chat:
            if dry_run:
                print(f"  [skip] {m} (non-chat)")
            continue
        r = probe_access(m)
        # access 判定
        if r["ok"]:
            access = {"state": "available", "http_status": r["status"], "confidence": 1.0}
            billing = {"class_": "free", "billing_model": "rate_limited",
                       "meter_unit": "requests", "free_allowance": "TPM/RPM tiered"}
            perf = {"ok": True, "tok_s": r["tok_s"], "total_ms": r["ms"],
                    "completion_tokens": r["out_tok"]}
        elif r["status"] == 429:
            access = {"state": "available", "http_status": 429, "confidence": 0.8}
            billing = {"class_": "free", "billing_model": "rate_limited",
                       "meter_unit": "requests", "free_allowance": "TPM/RPM tiered"}
            perf = None
        elif r["status"] in (400, 404):
            access = {"state": "unknown", "http_status": r["status"], "confidence": 0.5}
            billing = None
            perf = None
            catalog_state = {"state": "retired", "http_status": r["status"]}
        elif r["status"] == 401:
            print(f"  auth failed (401) — key expired? stop.")
            return
        else:
            access = {"state": "unknown", "http_status": r["status"], "confidence": 0.3}
            billing = None
            perf = None
        okb, st = _budget_check()
        if not okb:
            print(f"budget exhausted at {m}: {st['spent']}/{BUDGET_CALLS_PER_DAY}")
            break
        if dry_run:
            print(f"  [dry] {m}: access={access['state']} tok_s={r.get('tok_s')}")
            continue
        probe_reducer.emit_run("groq", m, "access", access, writer="groq_catalog_probe")
        if billing:
            probe_reducer.emit_run("groq", m, "billing", billing, writer="groq_catalog_probe")
        if perf:
            probe_reducer.emit_run("groq", m, "perf", perf, writer="groq_catalog_probe")
        runs += 3 if perf else (2 if billing else 1)
        print(f"  [{access['state']}] {m:<45} tok_s={r.get('tok_s')} ms={r.get('ms') or '-'}"
              + (f" err={r.get('err', '')[:60]}" if not r["ok"] else ""))
        time.sleep(0.4)
    print(f"emitted {runs} runs; budget spent {st['spent']}/{BUDGET_CALLS_PER_DAY}")
    if not dry_run:
        res = probe_reducer.run_full()
        print(f"reducer: {res}")


if __name__ == "__main__":
    main(dry_run=("--dry" in sys.argv))
