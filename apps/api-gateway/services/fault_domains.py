# -*- coding: utf-8 -*-
"""故障域熔断（RFC v2 F · P0）：共享 egress 代理挂时整组短路，消灭 30s+ 串行死亡链。

每个渠道的 proxy 字段（channels.CHANNELS[cid]["proxy"]）定义一个共享 egress 故障域。
无 proxy 的渠道属 DIRECT 域，永不熔断。熔断是**反应式**的（无需后台探测线程）：
代理渠道在回退循环里发生传输/超时失败 → mark_failure 计数，达阈值即置 trip_until；
trip 期间 is_tripped 短路该域内全部代理渠道，不发任何网络请求；冷却（trip_until
过期）后首请求恢复尝试，成功即 mark_success 清零。
有意区别于 upstream_outcome：那里把 TIMEOUT 标为 NON_BREAKER（避免误罚健康渠道），
但代理不可达是共享故障域信号，必须整域短路。这里只针对代理渠道的传输层失败，
上游自身的 5xx/超时不动故障域（那是渠道个体健康，走原有 per-channel breaker）。
"""
import os
import threading
import time
from urllib.parse import urlparse

import channels

FAULT_FILE = os.path.join(channels.DATA_DIR, "fault_domains.json")

# proxy_key -> {"ok": bool, "fail_streak": int, "trip_until": float}（monotonic 秒）
_state = {}
_lock = threading.Lock()

DEFAULTS = {
    "fail_streak_to_trip": 2,
    "trip_backoff_s": [5, 15, 60, 300],
    "request_deadline_s": 30,
    "promote_channels": [],  # 代理故障时升到链首的直连热备渠道（RFC v2 P1 B′）
}


def config():
    """mtime 感知热重载（复用 channels._cached_json），缺失回落默认。"""
    base = dict(DEFAULTS)
    cfg = channels._cached_json(FAULT_FILE) or {}
    for k in DEFAULTS:
        if k in cfg:
            base[k] = cfg[k]
    return base


def proxy_for(channel_id):
    """渠道的 egress 代理端点；无 proxy 返回 ""（DIRECT 域，永不熔断）。"""
    try:
        return (channels.CHANNELS.get(channel_id or "", {}) or {}).get("proxy", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def is_tripped(channel_id):
    """该渠道所在故障域是否熔断。DIRECT（无 proxy）永不熔断。"""
    proxy = proxy_for(channel_id)
    if not proxy:
        return False
    with _lock:
        st = _state.get(proxy)
        return bool(st) and time.monotonic() < st["trip_until"]


def mark_failure(channel_id):
    """代理渠道发生传输/超时失败：计数并（达阈值）熔断整域。"""
    proxy = proxy_for(channel_id)
    if not proxy:
        return
    cfg = config()
    streak_to_trip = cfg["fail_streak_to_trip"]
    backoff = cfg["trip_backoff_s"]
    with _lock:
        st = _state.setdefault(proxy, {"ok": True, "fail_streak": 0, "trip_until": 0})
        st["ok"] = False
        st["fail_streak"] = st.get("fail_streak", 0) + 1
        if st["fail_streak"] >= streak_to_trip:
            idx = min(st["fail_streak"] - streak_to_trip, len(backoff) - 1)
            st["trip_until"] = time.monotonic() + backoff[idx]
            st["fail_streak"] = 0  # 复位：冷却后首失败从第一档重新起跳


def mark_success(channel_id):
    """代理渠道成功：清零故障状态，立即恢复。"""
    proxy = proxy_for(channel_id)
    if not proxy:
        return
    with _lock:
        st = _state.setdefault(proxy, {"ok": True, "fail_streak": 0, "trip_until": 0})
        st["ok"] = True
        st["fail_streak"] = 0
        st["trip_until"] = 0


def any_proxy_tripped():
    """是否存在熔断中的代理故障域（共享 egress 挂了）。"""
    with _lock:
        now = time.monotonic()
        return any(k and now < st["trip_until"] for k, st in _state.items())


def _promote_ids(cfg):
    prom = cfg.get("promote_channels") or []
    return [c for c in prom if isinstance(c, str) and c]


def promote_on_proxy_down(chain):
    """代理故障域熔断时（RFC v2 B′·P1），把配置的直连热备渠道升到链首。

    共享 7890 挂时，sensetime / Cloudflare 直连等不依赖代理的渠道立即升 #1 救场；
    恢复后自动回落（按实时 trip 状态判定，无持久状态）。只升权**直连**渠道
    （web_serve 上代理的渠道没有意义）。正常态（无熔断）原样返回，零开销零副作用，
    不改变既有路由顺序。"""
    cfg = config()
    if not any_proxy_tripped():
        return chain
    chain = list(chain)
    for cid in _promote_ids(cfg):
        if proxy_for(cid):
            continue  # 只升直连渠道；没配代理的键无意义
        hit = [t for t in chain if t[0] == cid]
        if not hit:
            continue
        for t in hit:
            chain.remove(t)
        chain = hit + chain
    return chain


def group_by_proxy():
    """{proxy_key: [cid,...]}，DIRECT 归 ""。仅静态分组，不触发探测。"""
    groups = {}
    try:
        for cid in channels.ordered_channels():
            groups.setdefault(proxy_for(cid), []).append(cid)
    except Exception:  # noqa: BLE001
        pass
    return groups