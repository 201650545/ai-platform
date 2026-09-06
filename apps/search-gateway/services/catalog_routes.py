# -*- coding: utf-8 -*-
"""
GPT 三拆重构（2026-09-05）：把网关配置按职责拆成三份，落地"显式备用链"。

  ① model_catalog.json   —— 产品目录：用户看到什么（对外命名空间）
  ② model_routes.json    —— 路由：怎么走（primary + backup + fallback_policy）
  ③ channel_registry.json—— 渠道状态：资源状态（运行态，默认关闭）

设计要点（对齐 GPT Extended 评审）：
  - alias 是产品契约，route 是技术实现，channel 是资源状态，三份独立。
  - fallback 是"显式能力"，默认 disabled，需要时对单模型打开，绝不做隐式轮动。
  - 三个文件均走 mtime 感知缓存（复用 channels._cached_json），外部改动自动热重载免重启。
  - 本模块只读三拆配置；与现状 routing/unified 兼容——若某 alias 未在三拆里定义，
    回落到原有 model_providers 逻辑，保证本轮重构不破坏现役行为。
"""
import os

import channels as _ch

# 三个配置文件统一放在子项目 data/ 下
_FILE_MAP = {
    "catalog": os.path.join(_ch.DATA_DIR, "model_catalog.json"),
    "routes": os.path.join(_ch.DATA_DIR, "model_routes.json"),
    "registry": os.path.join(_ch.DATA_DIR, "channel_registry.json"),
}


def _load(tag):
    """mtime 感知加载三拆配置；缺文件/损坏 → 空 dict，不阻断。"""
    try:
        return _ch._cached_json(_FILE_MAP[tag])
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- ① 产品目录
def catalog():
    """model_catalog.json：{ alias: {display, billing, tier, use, ...} }。"""
    return _load("catalog")


def catalog_entry(alias):
    return catalog().get(alias)


def all_aliases():
    return list(catalog().keys())


# ---------------------------------------------------------------- ② 路由（显式备用链）
def routes():
    """model_routes.json：{ alias: {primary:{channel,model}, backup:[...], fallback_policy:{...}} }。"""
    return _load("routes")


def route_for(alias):
    """某 alias 的路由；不存在 → None。返回结构含 primary/backup/fallback_policy。"""
    return routes().get(alias)


def primary_of(alias):
    r = route_for(alias)
    return (r or {}).get("primary")


def backup_chain(alias):
    r = route_for(alias)
    return (r or {}).get("backup") or []


def fallback_enabled(alias):
    """显式备用链开关：默认关。仅当该 alias 显式声明 fallback_policy.enabled=true 才开。"""
    r = route_for(alias)
    if not r:
        return False
    pol = r.get("fallback_policy") or {}
    return bool(pol.get("enabled"))


# ---------------------------------------------------------------- ③ 渠道状态
def registry():
    """channel_registry.json：{ channel_id: {enabled, credential_status, last_success, quota, health} }。

    文件带 schema_version/generated_at/note 头，渠道在 channels 子键下；拆包返回 {channel_id:...}。
    """
    d = _load("registry")
    if isinstance(d, dict) and isinstance(d.get("channels"), dict):
        return d["channels"]
    return d


def channel_state(channel_id):
    return registry().get(channel_id)


def channel_enabled(channel_id):
    """渠道开关：reg 未定义该渠道时不拦截（回落到现状）；显式 enabled=false 才禁用。"""
    st = channel_state(channel_id)
    if st is None:
        return True
    return st.get("enabled", True)


# ---------------------------------------------------------------- 对外只读汇总（前端/诊断）
def summary():
    """把三份配置合成一份便于查看/前端展示的只读快照（不改写文件）。"""
    return {
        "catalog": catalog(),
        "routes": routes(),
        "registry": registry(),
        "counts": {
            "aliases": len(all_aliases()),
            "routes": len(routes()),
            "channels": len(registry()),
        },
    }