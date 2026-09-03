# -*- coding: utf-8 -*-
"""把表4 资源实例的「所属能力」link 关联到表3 对应能力记录
匹配键：instance_id = resource_id + "-01"，capability_id = "cap-" + resource_id
"""
import json, subprocess, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
TABLE3 = "资源能力规格表"
TABLE4 = "资源实例表"
HERE = os.path.dirname(os.path.abspath(__file__))

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"EXIT {p.returncode}: {p.stderr[:1500]}")
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        print("RAW:", p.stdout[:800])
        return None

def dump_table(table_id):
    """返回 {主字段值: record_id} 映射，并附带全部记录原始列表。"""
    p = subprocess.run([NODE, RUN_JS, "base", "+record-list", "--base-token", BASE_TOKEN,
                        "--table-id", table_id, "--page-size", "100", "--format", "json", "--as", "user"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(p.stdout)
    data = d.get("data", {})
    rows = data.get("data", [])
    fields = data.get("fields", [])
    rid_list = data.get("record_id_list", [])
    idx = {}
    for row, rid in zip(rows, rid_list):
        # 每行是单元格数组，fields 给出顺序；主字段是第一个 field
        primary = row[0] if row else None
        if isinstance(primary, list):
            primary = primary[0] if primary else None
        idx[str(primary)] = rid
    return idx

def update_record(table_id, record_id, field_name, link_rids):
    body = {"update_records": {
        record_id: {field_name: [{"id": r} for r in link_rids]},
    }}
    tmp = os.path.join(HERE, "_link_update.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-update", "--base-token", BASE_TOKEN,
             "--table-id", table_id, "--as", "user", "--json", "@_link_update.json")
    return d

def main():
    # 表3 能力：capability_id → record_id
    cap_by_id = dump_table("tbllAPtPd68uDTTj")   # 主字段 capability_id
    print("表3 能力映射:", json.dumps(cap_by_id, ensure_ascii=False)[:300])

    # 表4 实例：instance_id → record_id
    inst_by_id = dump_table("tbl8bKuwqP0Wl4d1")  # 主字段 instance_id
    print("表4 实例映射:", json.dumps(inst_by_id, ensure_ascii=False)[:300])

    # 为每条实例关联对应能力
    updated = 0
    for inst_id, inst_rid in inst_by_id.items():
        resource = inst_id[:-3]  # 去掉 -01
        cap_id = "cap-" + resource
        if cap_id in cap_by_id:
            cap_rid = cap_by_id[cap_id]
            d = update_record("tbl8bKuwqP0Wl4d1", inst_rid, "所属能力", [cap_rid])
            ok = d and d.get("ok")
            print(f"  关联 {inst_id} → {cap_id}: {'OK' if ok else json.dumps(d, ensure_ascii=False)[:300]}")
            updated += int(bool(ok))
        else:
            print(f"  ✗ 未找到能力 {cap_id} 对应 {inst_id}")
    print(f"完成：关联 {updated}/{len(inst_by_id)} 条实例")

if __name__ == "__main__":
    main()
