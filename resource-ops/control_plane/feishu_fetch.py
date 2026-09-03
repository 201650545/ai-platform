"""Feishu fetch：通过 lark-cli（用户身份）拉取 allowlist 表 → raw 快照 + revision。

设计 §1.1：只有控制平面访问飞书；:3100 不接触飞书、不持有飞书 token。
字段级投影保证敏感列（如 需人工登录URL/验证指纹）根本不进入 Python 对象。
"""
import json
import subprocess
from pathlib import Path

from .config import (
    LARK_CLI, BASE_TOKEN, TABLES, allowed_fields, ensure_runtime_dirs,
    RAW_DIR, STATE_DIR,
)

PAGE_SIZE = 200


def run_lark(args):
    cmd = [LARK_CLI, "base", *args, "--as", "user"]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(
            f"lark-cli 失败 returncode={proc.returncode}\n"
            f"cmd={' '.join(cmd)}\nstderr={proc.stderr[-800:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"lark-cli 输出非 JSON: {e}\nstdout={proc.stdout[:500]}") from e


def _envelope_to_records(envelope):
    """envelope → (records: [{record_id, fields}], rev)。"""
    d = (envelope or {}).get("data") or {}
    fields = d.get("fields") or []
    rows = d.get("data") or []
    ids = d.get("record_id_list") or []
    records = []
    for i, row in enumerate(rows):
        fld = {}
        for j in range(min(len(fields), len(row))):
            if row[j] not in (None, "", [], {}):
                fld[fields[j]] = row[j]
        records.append({
            "record_id": ids[i] if i < len(ids) else None,
            "fields": fld,
        })
    return records, d.get("rev")


def fetch_table(table_name, cfg):
    """拉取一张表的全部记录（分页）。返回 {records, rev, table_id}。"""
    args = [
        "+record-list", "--base-token", BASE_TOKEN,
        "--table-id", cfg["table_id"], "--limit", str(PAGE_SIZE), "--format", "json",
    ]
    for f in allowed_fields(table_name):
        args += ["--field-id", f]
    all_records, rev, offset = [], None, 0
    while True:
        resp = run_lark(args + ["--offset", str(offset)])
        if not resp.get("ok"):
            raise RuntimeError(f"record-list 失败: {json.dumps(resp, ensure_ascii=False)[:400]}")
        records, cur_rev = _envelope_to_records(resp)
        all_records.extend(records)
        rev = cur_rev if cur_rev is not None else rev
        d = resp.get("data") or {}
        if not d.get("has_more"):
            break
        offset += len(records)
    return {"records": all_records, "rev": rev, "table_id": cfg["table_id"]}


def fetch_all():
    """拉取全部 allowlist 表，写 raw 快照。不写 state（由 sync 层做 revision 去重）。

    返回 {table_name: {rev, record_count, table_id}}（revision vector）。
    """
    ensure_runtime_dirs()
    vector = {}
    for table_name, cfg in TABLES.items():
        result = fetch_table(table_name, cfg)
        payload = {
            "table": table_name,
            "table_id": cfg["table_id"],
            "kind": cfg["kind"],
            "rev": result["rev"],
            "fetched_at": None,  # 快照内不写时间戳，保证同 rev 快照字节级可复现
            "record_count": len(result["records"]),
            "records": result["records"],
        }
        (RAW_DIR / f"{_slug(table_name)}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        vector[table_name] = {
            "rev": result["rev"],
            "record_count": len(result["records"]),
            "table_id": cfg["table_id"],
        }
    return vector


def _slug(name):
    return {
        "资源实例表": "instances",
        "资源能力规格表": "capabilities",
        "账号资产汇总": "accounts",
        "模型资源总表": "channels",
    }[name]


def _state_path():
    return STATE_DIR / "feishu_revisions.json"


def read_state():
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_state(vector):
    # 只存 rev 向量（revision 去重）；不存时间戳，保证 no-op 判定可复现
    compact = {k: v["rev"] for k, v in vector.items()}
    (STATE_DIR / "feishu_revisions.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
