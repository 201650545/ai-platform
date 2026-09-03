# -*- coding: utf-8 -*-
"""publish 原子发布单元测试（P4.2）。

覆盖：invalid fail-closed / 首发成功+ACK / 二次发布归档历史 / 幂等 noop_same_sha /
ACK 超时回滚（有前代/无前代）/ rollback_previous。

运行: python tests/test_control_plane_publish.py
（全程临时目录 + 本地 mock 状态端点，绝不触碰真实网关数据目录）
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def make_resource(**overrides):
    r = {
        "resource_id": "cap-pub-01",
        "channel": "pubchan",
        "unified_model": "pub-model",
        "upstream_model": "pub-upstream",
        "credential_ref": "cred:acc-pub-1",
        "status": "active",
        "expiry_at": None,
        "limits": {"rpm": 30, "rpd": None, "concurrency": None},
        "capabilities": {"tools": "unknown", "vision": "unknown", "json_schema": "unknown"},
        "source_record_id": "rec_pub_1",
    }
    r.update(overrides)
    return r


def make_candidate(gen, sha="0" * 64, **top):
    doc = {
        "schema_version": 1,
        "generation_id": gen,
        "generated_at": "2026-08-29T12:00:00+08:00",
        "canonical_sha256": sha,
        "source": {"tables": {"资源实例表": 1}},
        "limits_precedence": "shadow",
        "capabilities_precedence": "static",
        "resources": [make_resource()],
    }
    doc.update(top)
    return doc


class _StatusServer:
    """mock GET /api/resource-config/status：可设定返回的 active_generation_id。"""

    def __init__(self):
        self.serve_gen = {"v": None}
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"active_generation_id": outer.serve_gen["v"],
                                   "last_reload_status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):  # 静默
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self):
        return "http://127.0.0.1:%d/api/resource-config/status" % self.port

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="p42pub_")
        os.environ["GATEWAY_DATA_DIR"] = self.tmp
        self.srv = _StatusServer()
        import control_plane.publish as pub
        self.pub = pub
        # env 在 import 前已设，重载保证常量指向临时目录；再挂 mock 端点
        import importlib
        self.pub = importlib.reload(self.pub)
        self.pub.STATUS_URL = self.srv.url()
        self.live = Path(self.tmp) / "gateway_resources.json"
        self.hist = Path(self.tmp) / "resource_history"

    def tearDown(self):
        self.srv.stop()

    def write_candidate(self, doc):
        p = Path(self.tmp) / "cand.json"
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def test_01_invalid_candidate_fail_closed(self):
        bad = make_candidate("gen-x")
        bad["resources"][0]["status"] = "weird-status"
        out = self.pub.publish(self.write_candidate(bad), wait_ack=0.5)
        self.assertEqual(out["publish_status"], "invalid_candidate")
        self.assertFalse(self.live.exists())

    def test_02_unreadable_candidate(self):
        p = Path(self.tmp) / "broken.json"
        p.write_text("{not json", encoding="utf-8")
        out = self.pub.publish(str(p), wait_ack=0.5)
        self.assertEqual(out["publish_status"], "invalid_candidate")

    def test_03_first_publish_with_ack(self):
        self.srv.serve_gen["v"] = "gen-1"
        out = self.pub.publish(self.write_candidate(make_candidate("gen-1")), wait_ack=5)
        self.assertEqual(out["publish_status"], "published")
        self.assertTrue(out["gateway_ack"])
        self.assertEqual(out["generation_id"], "gen-1")
        self.assertIsNone(out["previous_generation_id"])
        self.assertTrue(self.live.exists())
        live_doc = json.loads(self.live.read_text(encoding="utf-8"))
        self.assertEqual(live_doc["generation_id"], "gen-1")
        self.assertFalse(self.hist.exists() and list(self.hist.glob("*.json")))

    def test_04_second_publish_archives_history(self):
        self.srv.serve_gen["v"] = "gen-1"
        self.pub.publish(self.write_candidate(make_candidate("gen-1")), wait_ack=5)
        self.srv.serve_gen["v"] = "gen-2"
        out = self.pub.publish(self.write_candidate(
            make_candidate("gen-2", sha="1" * 64)), wait_ack=5)
        self.assertEqual(out["publish_status"], "published")
        self.assertEqual(out["previous_generation_id"], "gen-1")
        archived = list(self.hist.glob("gen-1.json"))
        self.assertEqual(len(archived), 1, "旧 generation 应归档进 resource_history")
        live_doc = json.loads(self.live.read_text(encoding="utf-8"))
        self.assertEqual(live_doc["generation_id"], "gen-2")

    def test_05_noop_same_sha(self):
        self.srv.serve_gen["v"] = "gen-1"
        c = self.write_candidate(make_candidate("gen-1"))
        self.pub.publish(c, wait_ack=5)
        out = self.pub.publish(c, wait_ack=5)
        self.assertEqual(out["publish_status"], "noop_same_sha")
        self.assertTrue(out["gateway_ack"])

    def test_06_ack_timeout_rollback_with_previous(self):
        self.srv.serve_gen["v"] = "gen-1"
        self.pub.publish(self.write_candidate(make_candidate("gen-1")), wait_ack=5)
        prev_bytes = self.live.read_bytes()
        # ACK 永远不认新 generation → 发布后必须原子回滚到 gen-1
        self.srv.serve_gen["v"] = "gen-1"
        out = self.pub.publish(self.write_candidate(
            make_candidate("gen-2", sha="2" * 64)), wait_ack=1.0)
        self.assertEqual(out["publish_status"], "rolled_back")
        self.assertEqual(self.live.read_bytes(), prev_bytes, "回滚后 live 必须等于发布前字节")
        live_doc = json.loads(self.live.read_text(encoding="utf-8"))
        self.assertEqual(live_doc["generation_id"], "gen-1")

    def test_07_ack_timeout_no_previous(self):
        self.srv.serve_gen["v"] = "never-matches"
        out = self.pub.publish(self.write_candidate(make_candidate("gen-9")), wait_ack=1.0)
        self.assertEqual(out["publish_status"], "rolled_back_no_previous")
        self.assertFalse(self.live.exists(), "首发布失败不得残留半成品 live")

    def test_08_rollback_previous(self):
        self.srv.serve_gen["v"] = "gen-1"
        self.pub.publish(self.write_candidate(make_candidate("gen-1")), wait_ack=5)
        self.srv.serve_gen["v"] = "gen-2"
        self.pub.publish(self.write_candidate(
            make_candidate("gen-2", sha="1" * 64)), wait_ack=5)
        out = self.pub.rollback_previous()
        self.assertEqual(out["publish_status"], "rolled_back")
        self.assertEqual(out["generation_id"], "gen-1")
        self.assertEqual(out["previous_generation_id"], "gen-2")
        live_doc = json.loads(self.live.read_text(encoding="utf-8"))
        self.assertEqual(live_doc["generation_id"], "gen-1")

    def test_09_history_prune_keeps_20(self):
        self.srv.serve_gen["v"] = "gen-final"
        for i in range(24):
            self.pub.publish(self.write_candidate(
                make_candidate("gen-%02d" % i, sha=("%02d" % i) * 32)), wait_ack=0.2)
        files = list(self.hist.glob("*.json"))
        self.assertLessEqual(len(files), self.pub.HISTORY_KEEP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
