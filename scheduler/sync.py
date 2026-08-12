#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2 数据桥真源同步器

读数据桥公开产物（instances.json + capabilities.json + manifest.json），
带 manifest 字节哈希校验（fail-closed），字段映射到调度器 SQLite
（配置字段 upsert，运行态 status/quota/cooldown 保留）。

凭证纪律：数据桥只提供 endpoint/路由组/状态等非敏感字段；凭证引用
（credential_id）来自本地 credential_map.json（安全平面），key 值仍只从
credentials.json 读取，绝不落库/日志。

用法:
  python sync.py            # 同步本地 public/（默认）
  python sync.py --remote   # 同步线上 GitHub Pages
  python sync.py --db db.sqlite3 --cred-map credential_map.json
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Ledger

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public")
REMOTE_BASE = "https://201650545.github.io/ai-resource-hub"
FILES = ["index.json", "capabilities.json", "instances.json", "schema.json"]
MANIFEST = "manifest.json"

# 数据桥「额度状态」区间 → 调度器 status（兜底；优先用实例「状态」字段）
STATUS_MAP = {
    "充足(>50%)": "可用",
    "中等(20-50%)": "可用",
    "偏低(<20%)": "可用",
    "耗尽": "额度耗尽",
    "未知": "待验证",
}

# 实例「状态」字段直接映射（表4 状态列，与调度器 status 同义）
INSTANCE_STATUS = {"可用", "待验证", "额度耗尽", "失效"}


def _read_files(source):
    """读 4 产物 + manifest，按字节 sha256 逐项校验（与数据桥 exporter 同口径）。"""
    def _get(name):
        if source == "remote":
            with urllib.request.urlopen(f"{REMOTE_BASE}/{name}", timeout=20) as r:
                return r.read()
        return open(os.path.join(DATA_DIR, name), "rb").read()

    try:
        manifest = json.loads(_get(MANIFEST).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        return None
    out = {}
    for name in FILES:
        try:
            body = _get(name)
        except Exception:
            return None
        declared = (manifest["files"].get(name) or {}).get("sha256")
        if not declared or hashlib.sha256(body).hexdigest() != declared:
            return None  # fail-closed：混搭/篡改 → 拒绝
        try:
            out[name] = json.loads(body.decode("utf-8"))
        except Exception:
            return None
    return out


def build_configs(files, overrides):
    """数据桥产物 → 调度器实例配置（字段映射见 M2_M3设计.md §3.1）。

    - 能力「状态」=失效（退役平台）→ 跳过，不进调度器。
    - status：优先用实例「状态」字段；空则用「额度状态」区间兜底。
    - route_priority：本地 overrides 优先（调度策略属本地），数据桥值次之，默认 99。
    - overrides 支持扁平 str（credential_id）或 dict（credential_id + route_priority）。
    """
    caps = {c.get("capability_id"): c for c in files["capabilities.json"] if isinstance(c, dict)}
    configs = {}
    for inst in files["instances.json"]:
        if not isinstance(inst, dict):
            continue
        iid = inst.get("instance_id")
        if not iid:
            continue
        cap = caps.get(inst.get("所属能力")) or {}
        if cap.get("状态") == "失效":
            continue  # 退役平台不进调度器
        mode = "openai-compatible" if cap.get("调用方式") == "HTTP_REST" else None
        if mode is None:
            continue  # OPENCLI_BROWSER（Colab 交互式）不进调度器
        ov = overrides.get(iid) or {}
        if isinstance(ov, str):
            ov = {"credential_id": ov}
        raw_status = inst.get("状态")
        if raw_status not in INSTANCE_STATUS:
            raw_status = STATUS_MAP.get(inst.get("额度状态"), "待验证")
        configs[iid] = {
            "capability_id": inst.get("所属能力"),
            "routing_group": cap.get("路由组") or inst.get("所属能力"),
            "canonical_model": cap.get("逻辑模型"),
            "mode": mode,
            "upstream_base": (cap.get("endpoint") or "").rstrip("/"),
            "credential_id": ov.get("credential_id"),       # 本地安全平面
            "status": raw_status,
            "quota_remaining": 0,                           # 本地安全平面初始；运行时扣减
            "quota_unit": inst.get("额度单位") or "token",
            "safety_margin": 0,
            "route_priority": ov.get("route_priority")
                or int(inst.get("路由优先级") or 99),         # 本地策略优先
            "config_version": int(inst.get("配置版本") or 1),
        }
    return configs


def _load_cred_map(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", action="store_true", help="从线上 GitHub Pages 同步（默认本地 public/）")
    ap.add_argument("--db", default="scheduler.sqlite3")
    ap.add_argument("--cred-map", default="credential_map.json")
    args = ap.parse_args()

    source = "remote" if args.remote else "local"
    files = _read_files(source)
    if not files:
        print("同步失败：数据桥产物不可用或 manifest 校验未过（fail-closed）", file=sys.stderr)
        sys.exit(1)

    cred_map = _load_cred_map(args.cred_map)
    configs = build_configs(files, cred_map)
    ledger = Ledger(args.db)
    ledger.sync_instances(configs)

    print(f"同步完成: {len(configs)} 实例（来源={source}）")
    for iid, c in sorted(configs.items()):
        cred = c.get("credential_id") or "-"
        print(f"  {iid:28s} model={c['canonical_model']:24s} prio={c['route_priority']:3d} "
              f"status={c['status']:8s} cred={cred}")


if __name__ == "__main__":
    main()
