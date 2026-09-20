# -*- coding: utf-8 -*-
"""Cloudflare Workers AI 全目录探针：catalog + access + billing 实测 → run 文件。

预算闸（GPT 评审坑②）：探针自身消耗 neurons 计入 probe_budget，一天内超预算即停。
免费档 10,000 neurons/天；单模型探一次 ≈ cost_sample（neurons 计量）。
编排消费由 probe_reducer → model_probes.json 承担；本脚本只产事实。
"""
import re
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_reducer  # noqa: E402

# 凭据走环境变量（CF_ACCOUNT_ID / CF_API_TOKEN），2026-09-20 起代码不再内嵌
# （GitHub push protection 会拦 Cloudflare API token；密钥本身在 data/channels.json keys 区维护）
ACC = os.environ.get("CF_ACCOUNT_ID", "")
KEY = os.environ.get("CF_API_TOKEN", "")
if not ACC or not KEY:
    try:
        _ch = json.load(open(os.path.join(probe_reducer.DATA_DIR, "channels.json"), encoding="utf-8"))
        _cc = _ch.get("custom_channels", {}).get("cloudflare", {})
        if not ACC:
            # account_id 内嵌在 base_url 路径里（…/accounts/<id>/ai/v1）
            _m = re.search(r"/accounts/([0-9a-f]{32})", _cc.get("base_url", ""))
            ACC = _m.group(1) if _m else ""
        KEY = KEY or _ch.get("keys", {}).get("cloudflare", "")
    except Exception:
        pass
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/v1"

BUDGET_FILE = os.path.join(probe_reducer.DATA_DIR, "probe_budget.json")
BUDGET_NEURONS_PER_DAY = 1500.0  # 探针预算：≤15% 免费额度（GPT 评审建议 ≤~15%）
PROBE_PROFILE = "chat-120-v1"    # 固定 workload：~120 输出 token（与 9-19 实测同 profile）
PROMPT = "Count from 1 to 40, one number per line, nothing else."


def _op():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _budget_check(cost):
    """记账式预算闸：超支返回 False。"""
    st = probe_reducer._load_json(BUDGET_FILE, {})
    today = time.strftime("%Y-%m-%d")
    if st.get("date") != today or st.get("channel") != "cloudflare":
        st = {"date": today, "channel": "cloudflare", "spent": 0.0}
    if st["spent"] >= BUDGET_NEURONS_PER_DAY:
        return False, st
    st["spent"] = round(st["spent"] + cost, 3)
    probe_reducer._atomic_write_json(BUDGET_FILE, st)
    return True, st


def fetch_catalog():
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/models/search?per_page=200"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
    with _op().open(req, timeout=30) as r:
        d = json.load(r)
    out = []
    for m in (d.get("result") or []):
        if ((m.get("task") or {}).get("name")) == "Text Generation":
            out.append(m.get("name"))
    return [x for x in out if x]


def probe_access(model):
    """一次真实调用测 access + 计量 cost_sample（含 neurons）。"""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 200, "temperature": 0,
    }).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with _op().open(req, timeout=90) as r:
            d = json.load(r)
        dt = (time.time() - t0) * 1000
        u = d.get("usage", {}) or {}
        neurons = u.get("neurons")
        out_tok = u.get("completion_tokens") or 0
        in_tok = u.get("prompt_tokens")
        tok_s = round(out_tok / (dt / 1000), 1) if dt > 0 and out_tok else None
        return {"ok": True, "status": r.status, "neurons": neurons,
                "in_tok": in_tok, "out_tok": out_tok, "tok_s": tok_s, "ms": round(dt)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code,
                "err": e.read().decode("utf-8", "replace")[:160]}
    except Exception as e:
        return {"ok": False, "status": None, "err": f"{type(e).__name__}: {e}"[:160]}


def main(dry_run=False):
    # 1) 目录
    try:
        catalog = fetch_catalog()
    except Exception as e:
        print(f"catalog fetch failed: {e}")
        return
    print(f"catalog: {len(catalog)} text models")
    budget = probe_reducer._load_json(BUDGET_FILE, {})
    today = time.strftime("%Y-%m-%d")
    spent = budget.get("spent", 0.0) if budget.get("date") == today else 0.0
    print(f"budget: {spent}/{BUDGET_NEURONS_PER_DAY} neurons spent today")

    runs = 0
    st = {"spent": spent}
    for m in catalog:
        ok, st = True, {"spent": spent}
        r = probe_access(m)
        # access 判定
        if r["ok"]:
            access = {"state": "available", "http_status": r["status"], "confidence": 1.0}
            neurons = r["neurons"] or 0.0
            billing = {
                "class_": "free", "billing_model": "metered", "meter_unit": "neurons",
                "cost_sample": {"probe_profile": PROBE_PROFILE, "meter_value": neurons,
                                "input_tokens": r["in_tok"], "output_tokens": r["out_tok"]},
            }
            perf = {"ok": True, "tok_s": r["tok_s"], "total_ms": r["ms"],
                    "completion_tokens": r["out_tok"]}
        elif r["status"] in (403,):
            access = {"state": "paid_required", "http_status": 403, "confidence": 0.95}
            billing = {"class_": "paid", "billing_model": "unknown"}
            perf = None
            neurons = 0.0
        elif r["status"] in (400, 404):
            access = {"state": "unknown", "http_status": r["status"], "confidence": 0.5}
            billing = None
            catalog_state = {"state": "retired", "http_status": r["status"]}
            perf = None
            neurons = 0.0
        else:
            access = {"state": "unknown", "http_status": r["status"], "confidence": 0.3}
            billing = None
            perf = None
            neurons = 0.0
        # 预算闸：成功响应才有真实 neurons 消耗
        if neurons > 0:
            okb, st = _budget_check(neurons)
            if not okb:
                print(f"budget exhausted at {m}: {st['spent']}/{BUDGET_NEURONS_PER_DAY}")
                break
        if dry_run:
            print(f"  [dry] {m}: access={access['state']} neurons={neurons}")
            continue
        probe_reducer.emit_run("cloudflare", m, "catalog",
                               {"state": "listed", "http_status": 200},
                               writer="cf_catalog_probe")
        probe_reducer.emit_run("cloudflare", m, "access", access, writer="cf_catalog_probe")
        if billing:
            probe_reducer.emit_run("cloudflare", m, "billing", billing, writer="cf_catalog_probe")
        if r["status"] in (400, 404):
            probe_reducer.emit_run("cloudflare", m, "catalog", catalog_state,
                                   writer="cf_catalog_probe")
        if perf:
            probe_reducer.emit_run("cloudflare", m, "perf", perf, writer="cf_catalog_probe")
        runs += 4 if perf else 3
        print(f"  [{access['state']}] {m:<50} neurons={neurons or '-'} tok_s={r.get('tok_s')}")
        time.sleep(0.4)
    print(f"emitted {runs} runs; budget spent {st['spent']}/{BUDGET_NEURONS_PER_DAY}")
    if not dry_run:
        res = probe_reducer.run_full()
        print(f"reducer: {res}")


if __name__ == "__main__":
    main(dry_run=("--dry" in sys.argv))
