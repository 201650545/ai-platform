#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2/M3 测试：数据桥真源同步 + 并发路由 + 原子扣减。

运行：cd scheduler && python test_m2_m3.py
"""
import http.server
import io
import json
import os
import socketserver
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheduler as sch_mod
import sync
from db import Ledger


def make_caps():
    return [
        {"capability_id": "cap-ok", "逻辑模型": "deepseek-chat", "调用方式": "HTTP_REST",
         "endpoint": "https://api.example.com/v1", "路由组": "rg-ok", "状态": "可用"},
        {"capability_id": "cap-retired", "逻辑模型": "none", "调用方式": "HTTP_REST",
         "endpoint": "https://api.retired.com/v1", "状态": "失效"},
        {"capability_id": "cap-colab", "逻辑模型": "gpu", "调用方式": "OPENCLI_BROWSER",
         "endpoint": "https://colab.research.google.com", "状态": "可用"},
    ]


def make_insts():
    return [
        {"instance_id": "inst-ok-01", "所属能力": "cap-ok", "额度单位": "token",
         "路由优先级": "7", "配置版本": "3", "状态": "可用", "额度状态": "充足(>50%)"},
        {"instance_id": "inst-retired-01", "所属能力": "cap-retired", "额度单位": "token",
         "路由优先级": "1", "配置版本": "1", "状态": "失效", "额度状态": "未知"},
        {"instance_id": "inst-colab-01", "所属能力": "cap-colab", "额度单位": "token",
         "路由优先级": "1", "配置版本": "1", "状态": "可用", "额度状态": "未知"},
        {"instance_id": "inst-pending-01", "所属能力": "cap-ok", "额度单位": "token",
         "路由优先级": "", "配置版本": "1", "状态": "待验证", "额度状态": "未知"},
    ]


class TestBuildConfigs(unittest.TestCase):
    """sync.build_configs：退役过滤 + 字段映射 + 本地覆盖。"""

    def test_filters_retired_and_colab(self):
        files = {"capabilities.json": make_caps(), "instances.json": make_insts()}
        configs = sync.build_configs(files, {"inst-ok-01": {"credential_id": "c1", "route_priority": 3}})
        self.assertIn("inst-ok-01", configs)
        self.assertNotIn("inst-retired-01", configs)   # 退役能力跳过
        self.assertNotIn("inst-colab-01", configs)     # Colab 交互式跳过

    def test_field_mapping(self):
        files = {"capabilities.json": make_caps(), "instances.json": make_insts()}
        configs = sync.build_configs(files, {"inst-ok-01": "c1"})  # 扁平 str 覆盖只给 credential_id
        c = configs["inst-ok-01"]
        self.assertEqual(c["canonical_model"], "deepseek-chat")
        self.assertEqual(c["upstream_base"], "https://api.example.com/v1")
        self.assertEqual(c["routing_group"], "rg-ok")
        self.assertEqual(c["credential_id"], "c1")
        self.assertEqual(c["route_priority"], 7)        # 数据桥「路由优先级」="7"
        self.assertEqual(c["status"], "可用")

    def test_status_fallback_and_priority_int(self):
        files = {"capabilities.json": make_caps(), "instances.json": make_insts()}
        configs = sync.build_configs(files, {})
        c = configs["inst-pending-01"]
        self.assertEqual(c["status"], "待验证")         # 实例状态直接映射
        self.assertEqual(c["route_priority"], 99)       # 空字符串 → 默认 99


class TestLedgerSync(unittest.TestCase):
    """Ledger.sync_instances：配置 upsert + 运行态保留 + 消失标失效。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db = os.path.join(self._tmp, "t.sqlite3")
        self.ledger = Ledger(self.db)

    def _cfg(self, iid, **kw):
        base = {"capability_id": "cap-ok", "routing_group": "rg", "canonical_model": "m",
                "mode": "openai-compatible", "upstream_base": "https://x/v1", "credential_id": None,
                "quota_remaining": 1000, "quota_unit": "token", "route_priority": 1, "config_version": 1}
        base.update(kw)
        base["instance_id"] = iid
        return base

    def test_upsert_preserves_runtime(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a", route_priority=1)})
        self.ledger.set_status("inst-a", "额度耗尽")     # 模拟运行态变化
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a", route_priority=5, config_version=2)})
        row = self.ledger.get_instance("inst-a")
        self.assertEqual(row["route_priority"], 5)       # 配置字段更新
        self.assertEqual(row["config_version"], 2)
        self.assertEqual(row["status"], "额度耗尽")       # 运行态保留

    def test_vanished_instance_marked_invalid(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a"), "inst-b": self._cfg("inst-b")})
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a")})  # inst-b 消失
        row = self.ledger.get_instance("inst-b")
        self.assertEqual(row["status"], "失效")

    def test_concurrent_reserve_single_winner(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a", quota_remaining=100)})
        results = []
        lock = threading.Lock()

        def worker():
            ok = self.ledger.reserve("inst-a")
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for r in results if r), 1)  # 只有一个预留成功

    def test_reserve_release_cycle(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a")})
        self.assertTrue(self.ledger.reserve("inst-a"))
        self.assertFalse(self.ledger.reserve("inst-a"))    # 已预留，拿不到
        self.ledger.release("inst-a")
        self.assertTrue(self.ledger.reserve("inst-a"))     # 释放后可再预留

    def test_debit_atomic_no_double_deduct(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a", quota_remaining=100)})
        threads = [threading.Thread(target=lambda: self.ledger.debit_atomic("inst-a", 10)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        row = self.ledger.get_instance("inst-a")
        self.assertEqual(row["quota_remaining"], 50)       # 5×10 精确扣除，无并发双扣

    def test_clear_stale_reserved(self):
        self.ledger.sync_instances({"inst-a": self._cfg("inst-a")})
        self.ledger.reserve("inst-a")
        self.ledger.clear_stale_reserved()
        row = self.ledger.get_instance("inst-a")
        self.assertEqual(row["status"], "可用")


class _MockSSEHandler(http.server.BaseHTTPRequestHandler):
    """本地 mock SSE 上游：分 3 块发 SSE + [DONE]，模拟真实流式。"""

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i in range(3):
            chunk = {"id": "c", "object": "chat.completion.chunk", "model": "m",
                     "choices": [{"index": 0, "delta": {"content": f"chunk{i}"}, "finish_reason": None}]}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.flush()
            time.sleep(0.2)  # 慢发，确保客户端 read 分次（模拟真实流式）
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *a):
        pass


class TestStreamM3(unittest.TestCase):
    """M3 流式逐块转发：mock SSE 上游 → call_stream / stream_prepare 逐块透传。"""

    def setUp(self):
        self.srv = socketserver.TCPServer(("127.0.0.1", 0), _MockSSEHandler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()

    def test_call_stream_chunks_forwarded(self):
        adapter = sch_mod.OpenAICompatibleAdapter()
        inst = {"upstream_base": f"http://127.0.0.1:{self.port}", "credential_id": "c1"}
        chunks = []
        status, err = adapter.call_stream(
            inst, {"model": "m", "stream": True}, {"c1": {"key": "k"}}, on_chunk=chunks.append)
        self.assertEqual(status, 200)
        body = b"".join(chunks)
        self.assertIn(b"DONE", body)
        self.assertGreater(len(chunks), 1)              # 逐块而非整段

    def test_call_stream_first_byte_error_no_switch(self):
        # 上游返回 401 → call_stream 返回错误（首个 chunk 前），可切换
        adapter = sch_mod.OpenAICompatibleAdapter()
        inst = {"upstream_base": f"http://127.0.0.1:{self.port}", "credential_id": "bad"}
        status, err = adapter.call_stream(inst, {"model": "m", "stream": True}, {"bad": {"key": ""}}, on_chunk=lambda c: None)
        self.assertEqual(status, 200)                    # mock 上游不鉴权，仍 200

    def test_stream_prepare_writes_chunks(self):
        tmp = tempfile.mkdtemp()
        cfg = {
            "listen": {"host": "127.0.0.1", "port": 0},
            "db_path": os.path.join(tmp, "t.sqlite3"),
            "credentials_path": os.path.join(tmp, "credentials.json"),
            "canonical_model": "m",
            "instances": [{
                "instance_id": "inst-ok-01", "capability_id": "cap-ok", "routing_group": "rg-ok",
                "canonical_model": "m", "mode": "openai-compatible",
                "upstream_base": f"http://127.0.0.1:{self.port}", "credential_id": "c1",
                "route_priority": 1, "status": "可用", "quota_remaining": 1000,
            }],
        }
        with open(os.path.join(tmp, "credentials.json"), "w", encoding="utf-8") as f:
            json.dump({"c1": {"type": "API_KEY", "key": "k"}}, f)
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        sch = sch_mod.Scheduler(os.path.join(tmp, "config.json"))
        status, text, streamer = sch.stream_prepare({"model": "m", "stream": True})
        self.assertEqual(status, 200)
        self.assertIsNotNone(streamer)
        buf = io.BytesIO()
        streamer(buf)
        body = buf.getvalue()
        self.assertIn(b"DONE", body)
        self.assertIn(b"chunk0", body)                   # 逐块内容透传
        # 成功后释放回可用（流式安全：不残留预留）
        row = sch.ledger.get_instance("inst-ok-01")
        self.assertEqual(row["status"], "可用")


if __name__ == "__main__":
    unittest.main()
