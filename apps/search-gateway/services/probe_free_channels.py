# -*- coding: utf-8 -*-
"""免费档通用探针：catalog + access + billing + perf → run 文件（probe_reducer 单写者）。

铁律：**绝不探测付费渠道**。白名单硬编码，仅 FREE_CHANNELS 内渠道可跑。
- OpenRouter 只允许调 `:free` 后缀模型（非 free 模型是付费的，碰一下都不行）
- ark 跳过图像模型（seedream），agnes 跳过 image/video，只探 chat
- 每渠道独立预算闸（按次），每模型每轮 1 次调用
- 对非 OpenAI 兼容失败/特殊渠道会如实记 unknown，绝不改配置、绝不重试轰炸
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channels  # noqa: E402
import probe_reducer  # noqa: E402

# ===== 禁测红线：以下渠道绝不允许被本脚本探测（付费/充值/订阅） =====
FORBIDDEN = {"deepseek", "opencode", "tokenrhythm", "zenmux", "ark-coding"}
# ===== 本脚本可测的白名单（全部免费档） =====
FREE_CHANNELS = ["agnes", "ark", "bai", "gmi", "longcat", "mistral", "modelscope",
                 "nvidia", "openrouter", "sensetime", "siliconflow", "xiaohongshu",
                 "zhipu", "zscc"]

PROBE_PROFILE = "chat-120-v1"
PROMPT = "Count from 1 to 40, one number per line, nothing else."
PER_CALL_DELAY = 0.5

# 每渠道探针预算（次/天）
BUDGET_CALLS_PER_DAY = {
    "default": 40,
    "openrouter": 60, "mistral": 80, "modelscope": 80,
    "bai": 100, "gmi": 120, "nvidia": 140, "siliconflow": 140, "zscc": 140,
}  # 大目录渠道按"全目录扫一遍+余量"设（每模型每轮 1 次）

# 非 chat 模型排除（探 catalog 不探 access）
SKIP_PATTERNS = ("image", "video", "seedream", "seedance", "tts", "whisper",
                 "guard", "embed", "embedding", "rerank", "ocr", "asr",
                 "doubao-seedream", "agnes-image", "agnes-video", "speech")

# OpenRouter：只准 :free
def _or_allowed(m):
    return m.endswith(":free")


def catalog_fetchers():
    """各渠道目录获取器。None = 无目录接口（用配置 models 列表）。"""
    def _get(url, key):
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {key}", "User-Agent": "gateway-probe/1.0"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30) as r:
            d = json.load(r)
        return d

    def _openai_list(cid, path="/models"):
        key = channels.get_key(cid)
        base = channels.CHANNELS[cid]["base_url"].rstrip("/")
        try:
            d = _get(base + path, key)
        except Exception as e:
            print(f"  [{cid}] catalog fetch failed: {e}")
            return None
        data = d.get("data") if isinstance(d, dict) else d
        return [m.get("id") if isinstance(m, dict) else m for m in (data or []) if m]

    return {
        # 标准 OpenAI 兼容目录
        "bai": lambda: _openai_list("bai"),
        "gmi": lambda: _openai_list("gmi"),
        "mistral": lambda: _openai_list("mistral"),
        "modelscope": lambda: _openai_list("modelscope"),
        "nvidia": lambda: _openai_list("nvidia"),
        "openrouter": lambda: [m for m in (_openai_list("openrouter") or [])
                               if _or_allowed(m)],
        "siliconflow": lambda: _openai_list("siliconflow"),
        "zhipu": lambda: _openai_list("zhipu"),
        "zscc": lambda: _openai_list("zscc"),
        # 无目录接口或目录不含计费信息：用配置列表
        "agnes": None, "ark": None, "longcat": None,
        "sensetime": None, "xiaohongshu": None,
    }


def budget_file(cid):
    return os.path.join(probe_reducer.DATA_DIR, f"probe_budget_{cid}.json")


def budget_check(cid, n=1):
    st = probe_reducer._load_json(budget_file(cid), {})
    today = time.strftime("%Y-%m-%d")
    if st.get("date") != today or st.get("channel") != cid:
        st = {"date": today, "channel": cid, "spent": 0}
    cap = BUDGET_CALLS_PER_DAY.get(cid, BUDGET_CALLS_PER_DAY["default"])
    if st["spent"] >= cap:
        return False, st
    st["spent"] += n
    probe_reducer._atomic_write_json(budget_file(cid), st)
    return True, st


def probe_access(cid, model):
    """1 次 chat 调用测 access + perf。"""
    key = channels.get_key(cid)
    base = channels.CHANNELS[cid]["base_url"].rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 200, "temperature": 0,
    }).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": "gateway-probe/1.0"})
    t0 = time.time()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
            d = json.load(r)
        dt_ms = (time.time() - t0) * 1000
        u = d.get("usage", {}) or {}
        out_tok = u.get("completion_tokens") or 0
        tok_s = round(out_tok / (dt_ms / 1000), 1) if dt_ms > 0 and out_tok else None
        return {"ok": True, "status": r.status, "out_tok": out_tok,
                "tok_s": tok_s, "ms": round(dt_ms)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code,
                "err": e.read().decode("utf-8", "replace")[:120]}
    except Exception as e:
        return {"ok": False, "status": None, "err": f"{type(e).__name__}: {e}"[:120]}


def is_chat_model(m):
    low = m.lower()
    return not any(p in low for p in SKIP_PATTERNS)


def main(dry_run=False, only=None):
    for cid in (only or FREE_CHANNELS):
        if cid in FORBIDDEN:
            print(f"!! FORBIDDEN channel {cid} — skip (付费渠道禁测)")
            continue
        if cid not in FREE_CHANNELS:
            print(f"!! {cid} not in free whitelist — skip")
            continue
        ch = channels.CHANNELS.get(cid)
        if not ch or not channels.get_key(cid):
            print(f"[{cid}] no channel config or key — skip")
            continue
        print(f"== {cid} ({ch.get('base_url')}) ==")
        fetcher = catalog_fetchers().get(cid)
        catalog = fetcher() if fetcher else list(ch.get("models", []))
        if catalog is None:
            continue
        print(f"  catalog: {len(catalog)} models")
        runs = 0
        for m in catalog:
            chat = is_chat_model(m)
            if not dry_run:
                probe_reducer.emit_run(cid, m, "catalog",
                                       {"state": "listed", "http_status": 200},
                                       writer="free_channels_probe")
                runs += 1
            if not chat:
                if dry_run:
                    print(f"  [skip] {m} (non-chat)")
                continue
            r = probe_access(cid, m)
            if r["ok"]:
                access = {"state": "available", "http_status": r["status"], "confidence": 1.0}
                billing = {"class_": "free", "billing_model": "rate_limited",
                           "meter_unit": "requests"}
                perf = {"ok": True, "tok_s": r["tok_s"], "total_ms": r["ms"],
                        "completion_tokens": r["out_tok"]}
            elif r["status"] == 429:
                access = {"state": "available", "http_status": 429, "confidence": 0.8}
                billing = {"class_": "free", "billing_model": "rate_limited",
                           "meter_unit": "requests"}
                perf = None
            elif r["status"] == 402 or r["status"] == 403:
                # 免费渠道上出现 402/403 = 该模型需付费/无权限，如实记 paid_required
                access = {"state": "paid_required", "http_status": r["status"], "confidence": 0.9}
                billing = {"class_": "paid", "billing_model": "unknown"}
                perf = None
            elif r["status"] in (400, 404):
                access = {"state": "unknown", "http_status": r["status"], "confidence": 0.5}
                billing = None
                perf = None
                if not dry_run:
                    probe_reducer.emit_run(cid, m, "catalog",
                                           {"state": "retired", "http_status": r["status"]},
                                           writer="free_channels_probe")
            else:
                access = {"state": "unknown", "http_status": r["status"], "confidence": 0.3}
                billing = None
                perf = None
            okb, st = budget_check(cid)
            if not okb:
                print(f"  budget exhausted ({cid}): {st['spent']}")
                break
            if dry_run:
                print(f"  [dry] {m}: {access['state']} tok_s={r.get('tok_s')}")
                continue
            probe_reducer.emit_run(cid, m, "access", access, writer="free_channels_probe")
            if billing:
                probe_reducer.emit_run(cid, m, "billing", billing, writer="free_channels_probe")
            if perf:
                probe_reducer.emit_run(cid, m, "perf", perf, writer="free_channels_probe")
            runs += 3 if perf else (2 if billing else 1)
            tail = f" tok_s={r['tok_s']} ms={r['ms']}" if r["ok"] else f" err={r.get('err', '')[:60]}"
            print(f"  [{access['state']}] {m:<55}{tail}")
            time.sleep(PER_CALL_DELAY)
        print(f"  emitted {runs} runs")
    if not dry_run:
        res = probe_reducer.run_full()
        print(f"reducer: {res}")


if __name__ == "__main__":
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1].split(",")
    main(dry_run=("--dry" in sys.argv), only=only)
