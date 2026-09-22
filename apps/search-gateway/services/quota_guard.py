# -*- coding: utf-8 -*-
"""额度警戒闸门（2026-09-22，郭老师三项指令：额度梳理/路由防超额/20% 警戒线）。

背景：火山方舟（ark）免费额度=每模型一次性 token 包，超出即按量扣费；实测
点名 model=doubao-seed-evolving 会被 legacy 路由直接打到 ark、model=doubao-*
会落到 zenmux 付费模型。本闸门在 capability/resource 之后、key/配额之前做
本地判定，把不可放行的候选直接从回落链里剔除。

数据真源 data/quota_guard.json（mtime 热加载，改完即生效无需重启）。语义：
- channels[cid].policy:
    "allowlist" = 仅 models 表内且未触发警戒线的模型放行（未登记=拒）
    "deny_all"  = 该渠道聊天路由全拒（生图等专用通路不经此闸门，不受影响）
- models[model].remaining / total：剩余比例 ≤ warn_pct%（缺省 20）→ 自动判停，
  即便 blocked 字段没写 true；额度在方舟控制台人工刷新后更新本文件即可。
- channels[cid].allow_source = 相对 data/ 的快照文件名（如 zenmux_free_models.json），
  取其 models[].id 作为动态白名单（每日巡检自动保鲜）。
- 本模块只认 guard 配置里登记过的渠道；未登记渠道零干预。
- 读不到文件/坏 JSON：内存里保留 last-good；从无 last-good 时对登记渠道
  fail-closed（宁可拒掉也不开付费口子），未登记渠道照常放行。
"""

import json
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(BASE_DIR), "data"))
GUARD_FILE = os.path.join(DATA_DIR, "quota_guard.json")

_lock = threading.Lock()
_stat = None          # (mtime_ns, size)
_doc = None           # last-good 解析结果


def _load():
    global _stat, _doc
    try:
        st = os.stat(GUARD_FILE)
        cur = (st.st_mtime_ns, st.st_size)
    except OSError:
        return _doc
    with _lock:
        if cur == _stat and _doc is not None:
            return _doc
        try:
            with open(GUARD_FILE, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if not isinstance(doc, dict) or not isinstance(doc.get("channels"), dict):
                raise ValueError("channels 非对象")
            _stat, _doc = cur, doc
        except Exception:  # noqa: BLE001 — 坏文件保持 last-good
            _stat = cur
    return _doc


def _warn_pct(ch, doc):
    v = ch.get("warn_pct", doc.get("warn_pct", 20))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 20.0


def _allow_via_snapshot(ch, model):
    """allow_source 快照白名单：models[].id 精确匹配（大小写敏感，与上游目录一致）。"""
    src = ch.get("allow_source")
    if not src:
        return False
    try:
        with open(os.path.join(DATA_DIR, src), "r", encoding="utf-8") as f:
            snap = json.load(f)
        for m in snap.get("models", []):
            if m.get("id") == model:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def blocked(cid, model):
    """返回 None=放行；否则 (reason, cid) 说明为何拒。只管 guard 配置登记的渠道。"""
    doc = _load()
    if doc is None:
        return None  # 未部署过 guard 文件 → 未登记渠道语义，零干预
    ch = doc.get("channels", {}).get(cid)
    if ch is None:
        return None
    model = (model or "").strip()
    policy = ch.get("policy")
    if policy == "deny_all":
        return ("guard_deny_all", cid)
    if policy == "allowlist":
        models = ch.get("models") or {}
        if model not in models and not _allow_via_snapshot(ch, model):
            return ("guard_not_allowlisted", cid)
        rec = models.get(model)
        if rec is not None:
            try:
                total = float(rec.get("total") or 0)
                remaining = float(rec.get("remaining", total) or 0)
            except (TypeError, ValueError):
                return ("guard_bad_record", cid)
            # 最低额度门槛（郭老师 2026-09-22「必须要大于250万才考虑」）：
            # 总免费额度 ≤ min_total 的模型即使登记也拒，防止小额度包烧穿
            min_total = ch.get("min_total")
            if min_total is not None and total <= float(min_total):
                return ("guard_below_min_total", cid)
            if rec.get("blocked") is True or (total > 0 and remaining / total <= _warn_pct(ch, doc) / 100.0):
                return ("guard_quota_warnline", cid)
        return None
    return None  # 未知 policy 不拦，避免配置笔误打断主链路


def status_payload():
    """只读观测（/api/quota-guard）：不含密钥，含渠道策略与模型剩余比例。"""
    doc = _load()
    if doc is None:
        return {"loaded": False, "file": GUARD_FILE}
    out = {"loaded": True, "updated": doc.get("updated"), "warn_pct": doc.get("warn_pct", 20),
           "channels": {}}
    for cid, ch in doc.get("channels", {}).items():
        entry = {"policy": ch.get("policy"), "note": ch.get("note"),
                 "allow_source": ch.get("allow_source"), "models": {}}
        for m, rec in (ch.get("models") or {}).items():
            try:
                total = float(rec.get("total") or 0)
                remaining = float(rec.get("remaining", total) or 0)
                pct = round(remaining / total * 100, 1) if total > 0 else None
            except (TypeError, ValueError):
                pct = None
            entry["models"][m] = {"remaining_pct": pct,
                                  "blocked": bool(rec.get("blocked")) or
                                  (pct is not None and pct <= _warn_pct(ch, doc))}
        out["channels"][cid] = entry
    return out
