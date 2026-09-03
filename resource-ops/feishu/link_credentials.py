# -*- coding: utf-8 -*-
"""把表4 资源实例的「凭证ID」关联到表2 凭证池对应凭证
匹配：SiliconFlow→siliconflow-main / 智谱→zhipu-main / HF→huggingface-main
"""
import json, subprocess, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
HERE = os.path.dirname(os.path.abspath(__file__))

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"EXIT {p.returncode}: {p.stderr[:800]}")
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        print("RAW:", p.stdout[:600])
        return None

def primary_map(table_id):
    """主字段值 → record_id"""
    p = subprocess.run([NODE, RUN_JS, "base", "+record-list", "--base-token", BASE_TOKEN,
                        "--table-id", table_id, "--page-size", "100", "--format", "json", "--as", "user"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(p.stdout)
    data = d.get("data", {})
    m = {}
    for row, rid in zip(data.get("data", []), data.get("record_id_list", [])):
        v = row[0] if row else None
        if isinstance(v, list):
            v = v[0] if v else None
        m[str(v)] = rid
    return m

# 实例 resource_id → 凭证 credential_id
INST2CRED = {
    "api_siliconflow_deepseek-01": "siliconflow-main",
    "api_zhipu_glm4-01": "zhipu-main",
    "gpu_huggingface_zerogpu-01": "huggingface-main",
}

def main():
    inst = primary_map("tbl8bKuwqP0Wl4d1")   # instance_id → rid
    cred = primary_map("tblRoOrNBJHlB4je")    # credential_id → rid
    print("凭证映射:", json.dumps(cred, ensure_ascii=False))
    updates = {}
    for inst_id, cred_id in INST2CRED.items():
        if inst_id in inst and cred_id in cred:
            updates[inst[inst_id]] = {"凭证ID": [{"id": cred[cred_id]}]}
            print(f"  关联 {inst_id} → {cred_id}: OK")
        else:
            print(f"  ✗ 缺 {inst_id} 或 {cred_id}")
    if updates:
        tmp = os.path.join(HERE, "_cred_link.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"update_records": updates}, f, ensure_ascii=False)
        d = lark("base", "+record-batch-update", "--base-token", BASE_TOKEN,
                 "--table-id", "tbl8bKuwqP0Wl4d1", "--as", "user", "--json", "@_cred_link.json")
        print("写入结果:", "OK" if d and d.get("ok") else json.dumps(d, ensure_ascii=False)[:400])

if __name__ == "__main__":
    main()
