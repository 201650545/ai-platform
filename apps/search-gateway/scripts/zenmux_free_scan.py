# -*- coding: utf-8 -*-
"""ZenMux 免费模型每日巡检（郭老师 2026-09-21 指示：白嫖 ZenMux Max 免费模型）

数据源: https://zenmux.ai/api/v1/models（公开、无需 key、实时更新）
页面入口: https://zenmux.ai/models?sort=newest&price_filter=free
免费判定: pricings.prompt / completion / input_cache_read 全部 value==0
产出:
  data/zenmux_free_models.json  最新快照（全量字段）
  data/zenmux_free_models.log   每日一行汇总 + 新增/下架差异
只读观测，不调用任何模型、不花钱。
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SNAP = os.path.join(DATA_DIR, "zenmux_free_models.json")
LOG = os.path.join(DATA_DIR, "zenmux_free_models.log")
URL = "https://zenmux.ai/api/v1/models"
PROXY = "http://127.0.0.1:7890"


def fetch():
    for mode in ("direct", "proxy"):
        try:
            if mode == "proxy":
                proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
                opener = urllib.request.build_opener(proxy_handler)
            else:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"[{mode}] failed: {e}")
    return None


def main():
    d = fetch()
    if not d:
        print("fetch failed entirely")
        sys.exit(1)
    models = d.get("data") or []
    free = []
    for m in models:
        pr = m.get("pricings") or {}

        def price(key):
            arr = pr.get(key) or [{}]
            return (arr[0] or {}).get("value")

        if price("prompt") == 0 and price("completion") == 0 and price("input_cache_read") == 0:
            free.append({
                "id": m.get("id"),
                "display_name": m.get("display_name"),
                "owned_by": m.get("owned_by"),
                "context_length": m.get("context_length"),
                "input_modalities": m.get("input_modalities"),
                "capabilities": m.get("capabilities"),
                "publish_time": m.get("publish_time"),
            })
    free.sort(key=lambda x: x["id"] or "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old_ids = set()
    if os.path.exists(SNAP):
        try:
            with open(SNAP, encoding="utf-8") as f:
                old_ids = {x.get("id") for x in json.load(f).get("models", [])}
        except Exception:  # noqa: BLE001
            pass
    new_ids = {x["id"] for x in free}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    with open(SNAP, "w", encoding="utf-8") as f:
        json.dump({"checked_at": now, "total_models": len(models), "count": len(free), "models": free},
                  f, ensure_ascii=False, indent=1)
    line = f"[{now}] free={len(free)}/{len(models)}"
    if added:
        line += " | 新增: " + ", ".join(added)
    if removed:
        line += " | 下架: " + ", ".join(removed)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)
    # 网关侧提醒文件（调度大脑/前端可读）
    print(json.dumps([x["id"] for x in free], ensure_ascii=False))


if __name__ == "__main__":
    main()
