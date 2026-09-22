# -*- coding: utf-8 -*-
"""付费渠道余额每日巡检（2026-09-22，郭老师全局规则：一切付费/限额渠道 20% 警戒线，
剩余≤20% 自动停 + 通知）。与 ArkQuotaScan 同思路：opencli 驱动日常 Chrome 抓控制台。

覆盖：
- MiMo：platform.xiaomimimo.com/console/finance/balance → 页面内 fetch /api/v1/balance
- zscc：api.zscc.in/wallet → 解析「订阅套餐」区「总额度: ¥X/¥T · 剩余 ¥R」（SVIP 订阅额度才是
  -cc 模型实际扣的池子；钱包充值余额 -0.004 与计费无关，勿再采。9-22 郭老师纠偏）

动作：回写 data/quota_guard.json 各渠道 balance.remaining（热加载即生效）；
剩余 ≤warn 线时追加 data/渠道警报.log（=通知郭老师）。浏览器未就绪/未登录也写警报。
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(r"D:\项目\ai-hub\search_gateway")
DATA = BASE / "data"
ALERT_LOG = DATA / "渠道警报.log"
GUARD = DATA / "quota_guard.json"
OPENCLI = r"C:\Users\郭永涛\AppData\Roaming\npm\opencli.cmd"

MIMO_PAGE = "https://platform.xiaomimimo.com/console/finance/balance"
ZSCC_PAGE = "https://api.zscc.in/wallet"


def ocli(*args, timeout=90):
    r = subprocess.run([OPENCLI, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.stdout or ""


def ocli_eval(js, timeout=90):
    out = ocli("browser", "main", "eval", js, timeout=timeout).strip()
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        i, j = out.find("{"), out.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(out[i:j + 1])
            except Exception:  # noqa: BLE001
                pass
        return out


def alert(msg):
    line = "[%s] [余额警戒] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def get_mimo_balance():
    ocli("browser", "main", "open", MIMO_PAGE, "--window", "background")
    time.sleep(8)
    val = ocli_eval("async () => { const r = await fetch('/api/v1/balance', {credentials:'include'}); const j = await r.json(); return {ok: j.code===0, balance: j.data && j.data.balance}; }")
    if isinstance(val, dict) and val.get("ok"):
        return float(val["balance"])
    return None


def get_zscc_balance():
    """返回 {"total": 订阅总额度, "remaining": 剩余额度}；解析自 wallet 页订阅套餐区。"""
    ocli("browser", "main", "open", ZSCC_PAGE, "--window", "background")
    time.sleep(8)
    val = ocli_eval("() => { const t = document.body.innerText; const i = t.indexOf('总额度:'); const seg = i>=0 ? t.slice(i, i+200) : ''; const m = seg.match(/总额度:\\s*¥[\\d,.]+\\/¥([\\d,.]+)\\s*·\\s*剩余\\s*¥([\\d,.]+)/); return {raw: m ? {total: m[1], remaining: m[2]} : null, seg: seg.slice(0, 100)}; }")
    if isinstance(val, dict) and val.get("raw"):
        try:
            return {"total": float(val["raw"]["total"].replace(",", "")),
                    "remaining": float(val["raw"]["remaining"].replace(",", ""))}
        except ValueError:
            return None
    print("zscc 订阅额度解析失败，页面片段：%s" % (val.get("seg") if isinstance(val, dict) else val))
    return None


def main():
    balances = {}
    try:
        b = get_mimo_balance()
        if b is not None:
            balances["mimo"] = b
    except Exception as exc:  # noqa: BLE001
        alert("MiMo 余额抓取失败：%s" % exc)
    try:
        b = get_zscc_balance()
        if b is not None:
            balances["zscc"] = b
    except Exception as exc:  # noqa: BLE001
        alert("zscc 余额抓取失败：%s" % exc)

    if not balances:
        alert("失败：本次余额巡检一无所获——Chrome 未运行或站点未登录")
        return 1

    guard = json.loads(GUARD.read_text(encoding="utf-8-sig"))
    chs = guard.get("channels", {})
    breaches = []
    for cid, payload in balances.items():
        ch = chs.get(cid)
        if not ch or "balance" not in ch:
            continue
        bal = ch["balance"]
        old = bal.get("remaining")
        if isinstance(payload, dict):  # zscc 订阅口径：总额度+剩余一起回写
            if payload.get("total"):
                bal["total"] = payload["total"]
            remaining = payload["remaining"]
        else:
            remaining = payload
        bal["remaining"] = remaining
        if "total" in bal and bal["total"]:
            pct = remaining / float(bal["total"]) * 100
            if pct <= 20:
                breaches.append("%s 余额 ¥%s（剩 %.1f%%，≤20%% 警戒线，闸门自动停）" % (cid, remaining, pct))
        elif remaining <= float(bal.get("warn_below", 0)):
            breaches.append("%s 余额 ¥%s（≤ 警戒下限 ¥%s）" % (cid, remaining, bal.get("warn_below")))
        print("%s: %s → %s" % (cid, old, remaining))
    with open(GUARD, "w", encoding="utf-8", newline="\n") as f:
        json.dump(guard, f, ensure_ascii=False, indent=1)
    if breaches:
        alert("警戒线触发：%s" % "；".join(breaches))
    print("余额巡检完成：%s" % balances)
    return 0


if __name__ == "__main__":
    sys.exit(main())
