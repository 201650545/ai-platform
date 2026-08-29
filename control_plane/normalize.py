"""Normalize：飞书 raw 快照 → Canonical Resource Model。

确定性：同一输入 → 完全相同的 resources 输出（P4.1 验收判据 2）。
映射决策：
  - resource_id = 资源实例表.instance_id（稳定唯一，不依赖飞书行号）
  - channel     = 能力表.adapter_id（稳定渠道 slug）
  - unified_model = 能力表.逻辑模型
  - upstream_model = 实例表.实际模型名
  - credential_ref = 按「平台名」join 账号资产汇总：
      在用 且 LOGGED_IN → cred:{account_id}
      否则 → cred:pending:{instance_id}（P4.3 前不会真正被解析）
  - status     = 实例表.状态 映射（待验证/额度耗尽 → paused，冷却中 → draining，失效 → disabled）
  - capabilities 一律 unknown（fail-closed，P4.6 才外移能力矩阵）
"""
import json
import re
from pathlib import Path

from .config import RAW_DIR

_RPM_RE = re.compile(r"(\d+)\s*rpm", re.IGNORECASE)

_INSTANCE_STATUS = {
    "可用": "active",
    "待验证": "paused",
    "额度耗尽": "paused",
    "冷却中": "draining",
    "失效": "disabled",
}

_CAP_STATUS = {
    "可用": "active",
    "暂停": "paused",
    "待验证": "paused",
    "失效": "disabled",
}

_SKIP_TABLES = {"模型资源总表"}  # channel_intel 仅做 revision 追踪，P4.1 不编译进资源


def _slug(s):
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def _link_ids(v):
    """链接字段 [{'id': 'rec...'}] → ['rec...']"""
    if not isinstance(v, list):
        return []
    return [x.get("id") for x in v if isinstance(x, dict) and x.get("id")]


def _first(v):
    """select 字段 ['可用'] → '可用'"""
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _parse_rpm(v):
    if not v:
        return None
    m = _RPM_RE.search(str(v))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _expiry_iso(v):
    """额度到期日 → ISO 字符串或 None。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        import datetime
        if v > 10 ** 12:
            return datetime.datetime.fromtimestamp(
                v / 1000, tz=datetime.timezone.utc).isoformat(timespec="seconds")
        return str(int(v))
    return str(v).strip() or None


def _normalize_platform(platform):
    """平台名 → 账号表 join 键。实例表『阿里云百炼』↔ 账号表『阿里云百炼』直接匹配。"""
    return (platform or "").strip()


def _load_raw(table_name):
    name = {
        "资源实例表": "instances",
        "资源能力规格表": "capabilities",
        "账号资产汇总": "accounts",
        "模型资源总表": "channels",
    }[table_name]
    p = RAW_DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"缺少 raw 快照: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _build_resource(cap, inst, account):
    instance_id = inst["fields"].get("instance_id") or "unknown"
    channel = cap["fields"].get("adapter_id") or _slug(cap["fields"].get("资源名称")) or "unknown"
    unified = cap["fields"].get("逻辑模型")
    upstream = inst["fields"].get("实际模型名")
    cap_status = _first(cap["fields"].get("状态"))
    inst_status = _first(inst["fields"].get("状态"))

    status = _INSTANCE_STATUS.get(inst_status, "paused")
    if status == "active" and cap_status not in ("可用", None):
        status = _CAP_STATUS.get(cap_status, status)

    credential_ref, credential_pending = None, True
    if account is not None:
        acct_status = _first(account["fields"].get("状态"))
        sess_status = _first(account["fields"].get("会话状态"))
        if acct_status == "在用" and sess_status == "LOGGED_IN":
            credential_ref = f"cred:{account['fields'].get('account_id')}"
            credential_pending = False
    if credential_ref is None:
        credential_ref = f"cred:pending:{instance_id}"

    r = {
        "resource_id": instance_id,
        "channel": channel,
        "unified_model": unified or "",
        "upstream_model": upstream or "",
        "credential_ref": credential_ref,
        "credential_pending": credential_pending,
        "status": status,
        "expiry_at": _expiry_iso(inst["fields"].get("额度到期日")),
        "limits": {
            "rpm": _parse_rpm(inst["fields"].get("限速")),
            "rpd": None,
            "concurrency": None,
        },
        "capabilities": {
            "tools": "unknown",
            "vision": "unknown",
            "json_schema": "unknown",
        },
        "source_record_id": inst["record_id"],
        "source": {
            "instance_id": instance_id,
            "capability_id": cap["fields"].get("capability_id"),
            "capability_status": cap_status,
            "instance_status": inst_status,
            "category": _first(cap["fields"].get("类别")),
            "调用方式": _first(cap["fields"].get("调用方式")),
            "认证方案": _first(cap["fields"].get("认证方案")),
            "free_desc": cap["fields"].get("免费额度描述"),
        },
    }
    return r


def normalize_all():
    """读取 raw 快照 → 返回 resources 列表 + 摘要。"""
    caps_raw = _load_raw("资源能力规格表")
    insts_raw = _load_raw("资源实例表")
    accts_raw = _load_raw("账号资产汇总")

    cap_by_id = {r["record_id"]: r for r in caps_raw["records"]}
    inst_by_id = {r["record_id"]: r for r in insts_raw["records"]}
    acct_by_platform = {}
    for r in accts_raw["records"]:
        key = _normalize_platform(_first(r["fields"].get("平台名称")))
        if key:
            acct_by_platform[key] = r

    resources, warnings = [], []
    cap_without_inst, inst_without_cap = set(), set()
    seen_inst_ids = set()

    for cap in caps_raw["records"]:
        inst_ids = _link_ids(cap["fields"].get("实例列表"))
        if not inst_ids:
            cap_without_inst.add(cap["fields"].get("capability_id"))
            continue
        for inst_id in inst_ids:
            inst = inst_by_id.get(inst_id)
            if inst is None:
                warnings.append(f"能力 {cap['fields'].get('capability_id')} 引用不存在的实例 {inst_id}")
                continue
            platform = inst["fields"].get("平台")
            account = acct_by_platform.get(_normalize_platform(platform))
            if account is None:
                warnings.append(
                    f"实例 {inst['fields'].get('instance_id')} 平台「{platform}」在账号资产汇总无匹配账号，"
                    f"credential 未解析")
            rid = inst["fields"].get("instance_id")
            if rid in seen_inst_ids:
                warnings.append(f"实例 {rid} 被多能力引用，已去重")
                continue
            seen_inst_ids.add(rid)
            resources.append(_build_resource(cap, inst, account))

    # 实例存在但未被任何能力引用 → 遗漏告警
    referenced = _referenced_inst_ids(caps_raw["records"])
    for r in insts_raw["records"]:
        if r["record_id"] not in referenced:
            inst_without_cap.add(r["fields"].get("instance_id"))

    summary = {
        "resources": resources,
        "warnings": warnings,
        "cap_without_inst": sorted(cap_without_inst),
        "inst_without_cap": sorted(inst_without_cap),
    }
    return summary


def _referenced_inst_ids(cap_records):
    ids = set()
    for cap in cap_records:
        ids.update(_link_ids(cap["fields"].get("实例列表")))
    return ids
