# -*- coding: utf-8 -*-
"""任务C：建关联字段
表4实例→表3能力(所属能力) / 表4实例→表2凭证(凭证ID) / 表2凭证→表1账号(所属账号)
数据来源：_task_c_mapping.json（主字段值 → record_id）
"""
import json, subprocess, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
HERE = os.path.dirname(os.path.abspath(__file__))
T1, T2, T3, T4 = "tblsrXWXX8GQ9hx4", "tblRoOrNBJHlB4je", "tbllAPtPd68uDTTj", "tbl8bKuwqP0Wl4d1"

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"  EXIT {p.returncode}: {p.stderr[:800]}"); return None
    try: return json.loads(p.stdout)
    except Exception:
        print("  RAW:", p.stdout[:600]); return None

def batch_update(table_id, updates, name):
    body = {"update_records": updates}
    tmp = os.path.join(HERE, "_upd.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-update", "--base-token", BASE_TOKEN,
             "--table-id", table_id, "--as", "user", "--json", "@_upd.json")
    ok = d and d.get("ok")
    print(f"[{name}] 更新 {len(updates)} 条:", "OK" if ok else (json.dumps(d, ensure_ascii=False)[:400] if d else "无返回"))
    return ok

def main():
    with open(os.path.join(HERE, "_task_c_mapping.json"), encoding="utf-8") as f:
        M = json.load(f)
    accounts = M["accounts"]      # account_id → rid
    credentials = M["credentials"]  # credential_id → rid
    capabilities = M["capabilities"]  # capability_id → rid
    instances = M["instances"]    # instance_id → rid

    # 实例 → 能力（cap-xxx-01 → cap-xxx）
    upd1 = {}
    for inst_id, inst_rid in instances.items():
        cap_id = inst_id[:-3]  # 去掉 -01
        if cap_id in capabilities:
            upd1[inst_rid] = {"所属能力": [{"id": capabilities[cap_id]}]}
        else:
            print(f"  ✗ 实例 {inst_id} 缺能力 {cap_id}")
    batch_update(T4, upd1, "实例→能力")

    # 实例 → 凭证（只有 5 个有 key 的）
    INST2CRED = {
        "cap-siliconflow-01": "siliconflow-main",
        "cap-deepseek-01": "deepseek-main",
        "cap-zhipu-01": "zhipu-main",
        "cap-openrouter-01": "openrouter-main",
        "cap-huggingface-01": "huggingface-main",
    }
    upd2 = {}
    for inst_id, cred_id in INST2CRED.items():
        if inst_id in instances and cred_id in credentials:
            upd2[instances[inst_id]] = {"凭证ID": [{"id": credentials[cred_id]}]}
            print(f"  关联 {inst_id} → {cred_id}")
        else:
            print(f"  ✗ 缺 {inst_id} 或 {cred_id}")
    batch_update(T4, upd2, "实例→凭证")

    # 凭证 → 账号
    CRED2ACC = {
        "siliconflow-main": "acc-siliconflow-1",
        "deepseek-main": "acc-deepseek-1",
        "zhipu-main": "acc-zhipu-1",
        "openrouter-main": "acc-openrouter-1",
        "huggingface-main": "acc-huggingface-1",
    }
    upd3 = {}
    for cred_id, acc_id in CRED2ACC.items():
        if cred_id in credentials and acc_id in accounts:
            upd3[credentials[cred_id]] = {"所属账号": [{"id": accounts[acc_id]}]}
            print(f"  关联 {cred_id} → {acc_id}")
        else:
            print(f"  ✗ 缺 {cred_id} 或 {acc_id}")
    batch_update(T2, upd3, "凭证→账号")

if __name__ == "__main__":
    main()
