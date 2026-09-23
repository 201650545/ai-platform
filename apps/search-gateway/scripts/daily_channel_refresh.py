# -*- coding: utf-8 -*-
"""已定渠道每日刷新（郭老师 2026-09-21 指示：所有已定规则的渠道每天自动刷新）

计划任务 ChannelDailyRefresh 每天 00:23 跑本脚本，内容：
  ① 已定渠道的编排成员真调实测（复用 probe_free_channels/probe_access + reducer 入册）
  ② zenmux + openrouter 免费名单巡检（快照 JSON + 新增/下架 diff 日志）
  ③ zscc/deepseek-v4.1-flash-cc 失效 → data/渠道警报.log（郭老师规则：失效必须提醒，禁自行替换）

已定渠道清单真源 = 渠道编排规则.md；本脚本内 SETTLED 同步维护。
只调免费模型，不触碰付费。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
sys.path.insert(0, os.path.join(BASE, "services"))

import channels  # noqa: E402
import probe_reducer  # noqa: E402
import probe_free_channels as pfc  # noqa: E402

# 已定渠道清单：直接读 model_routes.json 的全部三档成员（自动同步，改编排无需改本脚本）
ROUTES = os.path.join(DATA, "model_routes.json")
ALERT_LOG = os.path.join(DATA, "渠道警报.log")
PROXY = "http://127.0.0.1:7890"
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def settled_members():
    d = json.load(open(ROUTES, encoding="utf-8"))
    out = []
    for tier in sorted(d.get("routes", {})):
        for m in (d["routes"][tier] or {}).get("members") or []:
            cid, mdl = m.get("channel"), m.get("model")
            if cid and mdl and (cid, mdl) not in out:
                out.append((cid, mdl))
    return out


def log_alert(msg):
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{NOW}] {msg}\n")


def probe_settled():
    # 连续失败追踪（2026-09-23 郭老师指令「渠道死了必须报」）：任一成员连续 2 晚
    # 实测失败 → 渠道警报.log（第 1 晚只记 state 不报警，防瞬时 429 误报）。
    state_path = os.path.join(DATA, "daily_probe_state.json")
    state = {}
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
    results = []
    for cid, model in settled_members():
        r = pfc.probe_access(cid, model)
        ok = bool(r.get("ok"))
        probe_reducer.emit_run(cid, model, "access",
                               {"state": "available" if ok else "unavailable",
                                "http_status": r.get("status")},
                               writer="daily_channel_refresh")
        results.append((cid, model, ok))
        print(f"[probe] {cid}/{model}: {'OK' if ok else 'FAIL ' + str(r.get('error') or r.get('status'))[:80]}")
        key = f"{cid}|{model}"
        streak = 0 if ok else state.get(key, {}).get("streak", 0) + 1
        state[key] = {"streak": streak, "last": NOW,
                      "err": str(r.get('error') or r.get('status'))[:80]}
        if streak >= 2:
            log_alert(f"编排成员连续 {streak} 天实测失败：{cid}/{model}"
                      f"（{state[key]['err']}）——请检查渠道/模型是否下架，是否移出编排待拍板")
            print("!!! 渠道警报已写入:", ALERT_LOG)
        if (cid, model) == ("zscc", "deepseek-v4.1-flash-cc") and not ok:
            log_alert(f"ZSCC V4.1-cc 实测失败（http={r.get('status')}）——郭老师规则：须提醒拍板，勿自行替换！")
            print("!!! 渠道警报已写入:", ALERT_LOG)
    json.dump(state, open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return results


def fetch_json(url):
    for mode in ("direct", "proxy"):
        try:
            if mode == "proxy":
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
            else:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"[{mode}] {url[:60]} failed: {e}")
    return None


def free_scan(name, url, extract_ids):
    d = fetch_json(url)
    if not d:
        print(f"[{name}] fetch failed")
        return
    models = extract_ids(d)
    snap_path = os.path.join(DATA, f"{name}_free_models.json")
    log_path = os.path.join(DATA, f"{name}_free_models.log")
    old = set()
    if os.path.exists(snap_path):
        try:
            old = {m.get("id") for m in json.load(open(snap_path, encoding="utf-8")).get("models", [])}
        except Exception:  # noqa: BLE001
            pass
    new = {m["id"] for m in models}
    line = f"[{NOW}] {name} free={len(models)}"
    if new - old:
        line += " | 新增: " + ", ".join(sorted(new - old))
    if old - new:
        line += " | 下架: " + ", ".join(sorted(old - new))
    json.dump({"checked_at": NOW, "count": len(models), "models": models},
              open(snap_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def main():
    print(f"== 每日渠道刷新 {NOW} ==")
    probe_settled()

    def zenmux_models(d):
        out = []
        for m in d.get("data") or []:
            pr = m.get("pricings") or {}

            def v(k):
                a = pr.get(k) or [{}]
                return (a[0] or {}).get("value")
            if v("prompt") == 0 and v("completion") == 0 and v("input_cache_read") == 0:
                out.append({"id": m.get("id"), "display_name": m.get("display_name"),
                            "context_length": m.get("context_length")})
        return out

    def or_models(d):
        out = []
        for m in d.get("data") or []:
            pr = m.get("pricing") or {}

            def v(k):
                try:
                    return float(pr.get(k) or 0)
                except Exception:  # noqa: BLE001
                    return 0.0
            if v("prompt") == 0 and v("completion") == 0:
                out.append({"id": m.get("id"), "display_name": m.get("name"),
                            "context_length": m.get("context_length")})
        return out

    free_scan("zenmux", "https://zenmux.ai/api/v1/models", zenmux_models)
    free_scan("openrouter", "https://openrouter.ai/api/v1/models", or_models)
    print("== done ==")


if __name__ == "__main__":
    main()
