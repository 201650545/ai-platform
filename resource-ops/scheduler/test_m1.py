#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1 三验收脚本（用 curl 测，符合交接包验收方式）
验收① 正常请求 → 路由到实例 A (mock-a-01)
验收② A 标 EXHAUSTED（额度耗尽）→ 自动切 B (mock-b-01)，事件留痕 FAILOVER
验收③ 请求另一模型 → 明确失败 404，拒绝偷换模型

辅助验收：A 上游返回 quota_exhausted → 自动标 EXHAUSTED 并切 B（不靠人工标）
          stream=true 流式透传正常
          events 记录 OK/FAILOVER/EXHAUSTED
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
DB = os.path.join(HERE, "test_m1.sqlite3")
PROC = None

PASS = 0
FAIL = 0


def curl(method, url, body=None):
    args = ["curl", "-s", "-w", "\n%{http_code}", "-X", method, "-H", "Content-Type: application/json"]
    if body is not None:
        args += ["-d", json.dumps(body, ensure_ascii=False)]
    args += [url]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout.strip()
    code = out.rsplit("\n", 1)[-1]
    payload = "\n".join(out.split("\n")[:-1])
    return int(code), payload


def check(name, cond, detail=""):
    global PASS, FAIL
    mark = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
    return cond


def wait_ready(timeout=15):
    for _ in range(timeout * 5):
        try:
            urllib.request.urlopen(f"{BASE}/healthz", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    global PROC, DB
    if os.path.exists(DB):
        os.remove(DB)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(DB + suffix):
            os.remove(DB + suffix)

    PROC = subprocess.Popen([sys.executable, os.path.join(HERE, "scheduler.py"),
                             "--port", str(PORT), "--db", DB],
                            cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    if not wait_ready():
        print("启动失败：", (PROC.stdout.read(2000) if PROC.stdout else "?"))
        sys.exit(1)
    print(f"== 调度器就绪 {BASE} ==")

    # ---------- 验收①：正常请求 → A ----------
    print("\n--- 验收① 正常请求 → 实例 A ---")
    code, body = curl("POST", f"{BASE}/v1/chat/completions",
                      {"model": "deepseek-v4-flash",
                       "messages": [{"role": "user", "content": "你好"}]})
    try:
        obj = json.loads(body)
        got_inst = obj.get("x_instance_id")
    except Exception:
        got_inst = None
    check("验收① 返回 200", code == 200, f"http={code}")
    check("验收① 命中实例 A", got_inst == "mock-a-01", f"instance={got_inst}")

    # ---------- 验收②：A 标 EXHAUSTED → 自动切 B ----------
    print("\n--- 验收② A 标 EXHAUSTED → 自动切 B ---")
    code, body = curl("POST", f"{BASE}/__admin/instances/mock-a-01/status",
                      {"status": "额度耗尽"})
    check("验收② 手动标 A 为额度耗尽", code == 200, f"http={code}")

    code, body = curl("POST", f"{BASE}/v1/chat/completions",
                      {"model": "deepseek-v4-flash",
                       "messages": [{"role": "user", "content": "再问一次"}]})
    try:
        obj = json.loads(body)
        got_inst = obj.get("x_instance_id")
    except Exception:
        got_inst = None
    check("验收② A 已耗尽仍返回 200", code == 200, f"http={code}")
    check("验收② 自动切到实例 B", got_inst == "mock-b-01", f"instance={got_inst}")

    # ---------- 验收③：请求另一模型 → 明确失败 ----------
    print("\n--- 验收③ 请求另一模型 → 明确失败（拒绝偷换模型）---")
    code, body = curl("POST", f"{BASE}/v1/chat/completions",
                      {"model": "gpt-5",
                       "messages": [{"role": "user", "content": "hi"}]})
    check("验收③ 返回 404", code == 404, f"http={code}")
    check("验收③ 报错含 model_not_found", "model_not_found" in body, body[:120])

    # ---------- 附加① 上游 quota_exhausted → 自动标 EXHAUSTED → FAILOVER → 切下一实例 ----------
    print("\n--- 附加① 上游 quota_exhausted 自动触发切换（不靠人工标）---")
    import copy
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    # 全新独立 DB + 两实例：C(priority 2, 报 quota_exhausted) 优先 → B(priority 3, 正常) 兜底
    aux_cfg = {
        "listen": {"host": "127.0.0.1", "port": PORT},
        "db_path": os.path.join(HERE, "test_m1_aux.sqlite3"),
        "credentials_path": os.path.join(HERE, "credentials.json"),
        "canonical_model": "deepseek-v4-flash",
        "instances": [
            {**copy.deepcopy(cfg["instances"][0]), "instance_id": "mock-c-01",
             "route_priority": 2, "mock_fail": "quota_exhausted"},
            {**copy.deepcopy(cfg["instances"][1]), "route_priority": 3},
        ],
    }
    tmp_cfg = os.path.join(HERE, "_test_cfg.json")
    with open(tmp_cfg, "w", encoding="utf-8") as f:
        json.dump(aux_cfg, f, ensure_ascii=False)
    # 清掉辅助 DB 确保全新 seed
    for p in (aux_cfg["db_path"], aux_cfg["db_path"] + "-wal", aux_cfg["db_path"] + "-shm"):
        if os.path.exists(p):
            os.remove(p)

    PROC.terminate()
    PROC.wait(timeout=5)
    PROC = subprocess.Popen([sys.executable, os.path.join(HERE, "scheduler.py"),
                             "--port", str(PORT), "--db", aux_cfg["db_path"], "--config", tmp_cfg],
                            cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    wait_ready()

    code, body = curl("POST", f"{BASE}/v1/chat/completions",
                      {"model": "deepseek-v4-flash",
                       "messages": [{"role": "user", "content": "谁有空"}]})
    try:
        obj = json.loads(body)
        got_inst = obj.get("x_instance_id")
    except Exception:
        got_inst = None
    check("附加① 触发切换后返回 200", code == 200, f"http={code}")
    check("附加① 自动切到实例 B", got_inst == "mock-b-01", f"instance={got_inst}")

    code, body = curl("GET", f"{BASE}/__admin/instances")
    try:
        rows = json.loads(body)
        c_status = next((r["status"] for r in rows if r["instance_id"] == "mock-c-01"), "?")
    except Exception:
        c_status = "?"
    check("附加① C 被自动标为额度耗尽", c_status == "额度耗尽", f"status={c_status}")

    # ---------- 附加②：stream=true 流式透传 ----------
    print("\n--- 附加② 流式透传（stream=true）---")
    code, body = curl("POST", f"{BASE}/v1/chat/completions",
                      {"model": "deepseek-v4-flash", "stream": True,
                       "messages": [{"role": "user", "content": "流式"}]})
    check("附加② 流式返回 200", code == 200, f"http={code}")
    check("附加② 含 [DONE]", "[DONE]" in body, body[:120])

    # ---------- 事件留痕 ----------
    print("\n--- 事件日志（最近 10 条）---")
    code, body = curl("GET", f"{BASE}/__admin/events")
    try:
        events = json.loads(body)
        for e in events[:10]:
            print(f"  {e['ts']}  {e['instance_id'] or '-':14} {e['model'] or '-':16} {e['kind']:14} {e['detail']}")
        kinds = [e["kind"] for e in events]
        check("事件含 OK", "OK" in kinds)
        check("事件含 FAILOVER", "FAILOVER" in kinds)
        check("事件含 EXHAUSTED", "EXHAUSTED" in kinds)
    except Exception as ex:
        print("事件解析失败:", ex)

    print(f"\n==== 结果：PASS={PASS} FAIL={FAIL} ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        if PROC and PROC.poll() is None:
            PROC.terminate()
            try:
                PROC.wait(timeout=5)
            except Exception:
                PROC.kill()
    sys.exit(rc)
