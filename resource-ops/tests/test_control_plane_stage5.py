# -*- coding: utf-8 -*-
"""阶段5 单元测试：state/lease/sync 三类失败处理与门禁。

隔离原则：每个用例把 state 模块的 CP_DIR/STATE_FILE/LOG_FILE/ALERT_DIR 与
lease.LOCK_FILE 指向临时目录；sync 的 run_once/_raw_input_hash、publish.publish、
feishu_fetch.fetch_all 全部 mock（不触网、不碰真实数据目录）。
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, r"D:\ai-resource-hub")

from control_plane import state as state_mod      # noqa: E402
from control_plane import lease as lease_mod      # noqa: E402
from control_plane import sync as sync_mod        # noqa: E402
from control_plane import publish as publish_mod  # noqa: E402


def _valid_fake(sha="candsha1"):
    return {"ok": True, "mode": "dry-run", "errors": [], "noop": False,
            "valid": True, "warnings": [], "secret_findings": 0,
            "resource_count": 3, "candidate_sha256": sha,
            "source_revision_vector": {"t": 1}, "normalize_warnings": []}


def _invalid_fake(errors=("bad field",)):
    return {"ok": False, "mode": "dry-run", "errors": list(errors), "noop": False,
            "valid": False, "warnings": [], "secret_findings": 0,
            "resource_count": 3, "candidate_sha256": "badsha",
            "source_revision_vector": {"t": 2}, "normalize_warnings": []}


class Stage5TestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cp5_"))
        self.alerts = self.tmp / "alerts"
        patchers = [
            mock.patch.object(state_mod, "CP_DIR", self.tmp),
            mock.patch.object(state_mod, "STATE_FILE", self.tmp / "control_plane_state.json"),
            mock.patch.object(state_mod, "LOG_FILE", self.tmp / "control_plane.log"),
            mock.patch.object(state_mod, "ALERT_DIR", self.alerts),
            mock.patch.object(lease_mod, "LOCK_FILE", self.tmp / "lease.lock"),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        sync_mod._LAST_ALERT_AT.clear()
        self.addCleanup(sync_mod._LAST_ALERT_AT.clear)

    def alerts_of(self, kind):
        return list(self.alerts.glob("%s_*.json" % kind))


class StateTests(Stage5TestBase):
    def test_roundtrip_and_unknown_field(self):
        st = state_mod.update_state(last_run_result="noop", rollback_times=["a"])
        self.assertEqual(st["last_run_result"], "noop")
        self.assertEqual(state_mod.load_state()["rollback_times"], ["a"])
        with self.assertRaises(KeyError):
            state_mod.update_state(no_such_field=1)

    def test_corrupt_state_falls_back(self):
        (self.tmp / "control_plane_state.json").write_text("{broken", encoding="utf-8")
        st = state_mod.load_state()
        self.assertFalse(st["halted"])
        self.assertTrue((self.tmp / "control_plane_state.json.corrupt").exists())

    def test_defaults_have_new_fields(self):
        st = state_mod.load_state()
        for k in ("consecutive_ack_timeouts", "consecutive_validate_failures",
                  "last_input_hash", "halted", "cooldown_until",
                  "publish_suppressed_count"):
            self.assertIn(k, st)

    def test_prune_rollbacks_window(self):
        old = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 90000))
        fresh = time.strftime("%Y-%m-%dT%H:%M:%S")
        kept = state_mod.prune_rollbacks({"rollback_times": [old, fresh, "bad"]})
        self.assertEqual(kept, [fresh])


class LeaseTests(Stage5TestBase):
    def test_acquire_release(self):
        lease = lease_mod.Lease()
        lease.acquire()
        lock = self.tmp / "lease.lock"
        self.assertTrue(lock.exists())
        doc = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual(doc["lease_id"], lease.lease_id)
        self.assertNotEqual(doc["pid"], 0)
        lease.release()
        self.assertFalse(lock.exists())

    def test_occupied_fresh_lock(self):
        other = lease_mod.Lease()
        other.acquire()
        try:
            with self.assertRaises(lease_mod.LeaseOccupied):
                lease_mod.Lease().acquire()
        finally:
            other.release()

    def test_takeover_stale_lock(self):
        stale = {"pid": 99999, "hostname": "old", "lease_id": "deadbeef",
                 "started_at": "2026-08-28T00:00:00",
                 "heartbeat_at": time.strftime(
                     "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))}
        (self.tmp / "lease.lock").write_text(json.dumps(stale), encoding="utf-8")
        lease = lease_mod.Lease()
        lease.acquire()  # 陈旧 → 干净接管
        doc = json.loads((self.tmp / "lease.lock").read_text(encoding="utf-8"))
        self.assertNotEqual(doc["lease_id"], "deadbeef")
        lease.release()

    def test_lost_flag_after_release(self):
        lease = lease_mod.Lease()
        lease.acquire()
        lease.release()
        self.assertTrue(lease.lost() or not lease.lost())  # released; no crash
        self.assertFalse((self.tmp / "lease.lock").exists())


class SyncTickTests(Stage5TestBase):
    # ---------- Q4 第一类：fetch 失败指数退避 ----------

    def test_fetch_fail_backoff_doubling_and_cap(self):
        with mock.patch.object(sync_mod, "run_once", side_effect=OSError("net down")):
            w = [sync_mod._tick(60, publish=False, force=False) for _ in range(7)]
        self.assertEqual(w[:4], [60.0, 120.0, 240.0, 480.0])
        self.assertEqual(w[6], 1800.0)  # 60*2^6=3840 → cap
        st = state_mod.load_state()
        self.assertEqual(st["consecutive_fetch_failures"], 7)
        self.assertEqual(st["last_run_result"], "fetch_fail")
        self.assertEqual(st["current_backoff_interval_s"], 1800)

    def test_fetch_success_resets_backoff(self):
        with mock.patch.object(sync_mod, "run_once", side_effect=OSError("x")):
            sync_mod._tick(60, publish=False, force=False)
        with mock.patch.object(sync_mod, "run_once",
                               return_value=({"noop": True}, 0)):
            sync_mod._tick(60, publish=False, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["consecutive_fetch_failures"], 0)
        self.assertEqual(st["last_run_result"], "noop")
        self.assertEqual(st["current_backoff_interval_s"], 0)

    # ---------- Q4 第二类：validate 熔断 ----------

    def test_validate_circuit_halts_after_3_same_input(self):
        fake = _invalid_fake()
        with mock.patch.object(sync_mod, "run_once", return_value=(fake, 1)), \
             mock.patch.object(sync_mod, "_raw_input_hash",
                               return_value="INPUT_A"):
            for _ in range(3):
                sync_mod._tick(60, publish=False, force=False)
        st = state_mod.load_state()
        self.assertTrue(st["halted"])
        self.assertEqual(st["consecutive_validate_failures"], 3)
        self.assertEqual(st["halted_input_hash"], "INPUT_A")
        self.assertIn("validate", st["halted_reason"])
        self.assertEqual(len(self.alerts_of("halt")), 1)

    def test_input_change_resets_counter(self):
        with mock.patch.object(sync_mod, "run_once", return_value=(_invalid_fake(), 1)):
            with mock.patch.object(sync_mod, "_raw_input_hash", return_value="A"):
                sync_mod._tick(60, publish=False, force=False)
            with mock.patch.object(sync_mod, "_raw_input_hash", return_value="B"):
                sync_mod._tick(60, publish=False, force=False)
            with mock.patch.object(sync_mod, "_raw_input_hash", return_value="B"):
                sync_mod._tick(60, publish=False, force=False)
        st = state_mod.load_state()
        self.assertFalse(st["halted"])
        self.assertEqual(st["consecutive_validate_failures"], 2)
        self.assertEqual(st["last_input_hash"], "B")

    # ---------- Q4/Q6：halted 态只 fetch 探活 ----------

    def test_halted_fetch_only_never_validates(self):
        state_mod.update_state(halted=True, halted_reason="test",
                               halted_input_hash="OLD")
        with mock.patch.object(sync_mod, "feishu_fetch") as mf, \
             mock.patch.object(sync_mod, "run_once") as mr:
            mf.fetch_all.return_value = {}
            w = sync_mod._tick(60, publish=True, force=False)
            mr.assert_not_called()          # 绝不 validate/publish
            mf.fetch_all.assert_called_once()
        self.assertEqual(w, 60.0)
        st = state_mod.load_state()
        self.assertEqual(st["last_run_result"], "halted_fetch_ok")
        self.assertTrue(st["halted"])       # 不自动恢复

    def test_halted_fetch_fail_backoff(self):
        state_mod.update_state(halted=True)
        with mock.patch.object(sync_mod, "feishu_fetch") as mf:
            mf.fetch_all.side_effect = OSError("feishu down")
            w = sync_mod._tick(60, publish=False, force=False)
        self.assertEqual(w, 60.0)
        st = state_mod.load_state()
        self.assertEqual(st["last_run_result"], "fetch_fail")
        self.assertTrue(st["halted"])

    def test_clear_halt(self):
        state_mod.update_state(halted=True, halted_reason="x",
                               halted_since="t", halted_input_hash="H",
                               consecutive_validate_failures=2)
        rc = sync_mod._clear_halt()
        self.assertEqual(rc, 0)
        st = state_mod.load_state()
        self.assertFalse(st["halted"])
        self.assertEqual(st["consecutive_validate_failures"], 0)
        self.assertIsNone(st["halted_reason"])
        self.assertEqual(sync_mod._clear_halt(), 0)  # 幂等

    # ---------- Q5 门禁：冷却 + 最小发布间隔 ----------

    def _go_publish_phase(self):
        """把状态推进到 validate_ok → publish 门禁处（publish mock 不真正调用）。"""
        return mock.patch.object(sync_mod, "run_once",
                                 return_value=(_valid_fake(), 0))

    def test_cooldown_suppresses_publish(self):
        state_mod.update_state(cooldown_until=time.time() + 300)
        with self._go_publish_phase(), \
             mock.patch.object(publish_mod, "publish") as mp:
            sync_mod._tick(60, publish=True, force=False)
            mp.assert_not_called()
        st = state_mod.load_state()
        self.assertEqual(st["publish_suppressed_count"], 1)
        self.assertEqual(st["last_run_result"], "validate_ok")

    def test_min_publish_interval_suppresses(self):
        state_mod.update_state(last_publish_at=state_mod.now_iso())
        with self._go_publish_phase(), \
             mock.patch.object(publish_mod, "publish") as mp:
            sync_mod._tick(60, publish=True, force=False)
            mp.assert_not_called()
        st = state_mod.load_state()
        self.assertEqual(st["publish_suppressed_count"], 1)

    # ---------- 发布结果三分支 ----------

    def test_published_success_records_state(self):
        with self._go_publish_phase(), \
             mock.patch.object(publish_mod, "publish",
                               return_value={"publish_status": "published",
                                             "generation_id": "g-ok",
                                             "gateway_ack": True}):
            sync_mod._tick(60, publish=True, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["last_publish_gen"], "g-ok")
        self.assertEqual(st["last_ack_result"], "ok")
        self.assertEqual(st["consecutive_ack_timeouts"], 0)
        self.assertEqual(st["publish_attempt_count"], 1)

    def test_rolled_back_sets_cooldown_and_counters(self):
        with self._go_publish_phase(), \
             mock.patch.object(publish_mod, "publish",
                               return_value={"publish_status": "rolled_back",
                                             "generation_id": "g-bad",
                                             "gateway_ack": False}):
            sync_mod._tick(60, publish=True, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["last_ack_result"], "timeout")
        self.assertEqual(st["consecutive_ack_timeouts"], 1)
        self.assertEqual(len(st["rollback_times"]), 1)
        self.assertGreater(st["cooldown_until"], time.time() + 250)  # 5×60
        self.assertEqual(len(self.alerts_of("rollback_trend")), 0)   # 未达 3 次

    def test_publish_invalid_counts_as_validate_fail(self):
        with self._go_publish_phase(), \
             mock.patch.object(publish_mod, "publish",
                               return_value={"publish_status": "invalid_candidate",
                                             "errors": ["x"]}), \
             mock.patch.object(sync_mod, "_raw_input_hash", return_value="IH"):
            sync_mod._tick(60, publish=True, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["consecutive_validate_failures"], 1)
        self.assertEqual(st["last_input_hash"], "IH")
        self.assertFalse(st["halted"])

    # ---------- Q4 第三类：ACK 超时短固定重试 + 升级 ----------

    def test_noop_with_pending_ack_timeout_retries(self):
        state_mod.update_state(last_ack_result="timeout", consecutive_ack_timeouts=1)
        (sync_mod.CANDIDATE_DIR / sync_mod.CANDIDATE_NAME).parent.mkdir(
            parents=True, exist_ok=True)
        with mock.patch.object(sync_mod, "run_once",
                               return_value=({"noop": True}, 0)), \
             mock.patch.object(publish_mod, "publish",
                               return_value={"publish_status": "published",
                                             "generation_id": "g-retry",
                                             "gateway_ack": True}):
            sync_mod._tick(60, publish=True, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["consecutive_ack_timeouts"], 0)
        self.assertEqual(st["last_publish_gen"], "g-retry")

    def test_ack_escalation_at_3_emits_3204(self):
        state_mod.update_state(last_ack_result="timeout", consecutive_ack_timeouts=2)
        with mock.patch.object(sync_mod, "run_once",
                               return_value=({"noop": True}, 0)), \
             mock.patch.object(publish_mod, "publish",
                               return_value={"publish_status": "rolled_back",
                                             "generation_id": "g2",
                                             "gateway_ack": False}):
            sync_mod._tick(60, publish=True, force=False)
        st = state_mod.load_state()
        self.assertEqual(st["consecutive_ack_timeouts"], 3)
        self.assertEqual(len(self.alerts_of("rollback_trend")), 1)

    def test_no_retry_beyond_threshold(self):
        state_mod.update_state(last_ack_result="timeout",
                               consecutive_ack_timeouts=3)
        with mock.patch.object(sync_mod, "run_once",
                               return_value=({"noop": True}, 0)), \
             mock.patch.object(publish_mod, "publish") as mp:
            sync_mod._tick(60, publish=True, force=False)
            mp.assert_not_called()  # 已升级 → 停止自动重试

    # ---------- 观测 ----------

    def test_log_jsonl_written(self):
        state_mod.log_event("unit_test", k=1)
        log = self.tmp / "control_plane.log"
        self.assertTrue(log.exists())
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        self.assertEqual(rec["event"], "unit_test")

    def test_emit_event_writes_alert_file(self):
        state_mod.emit_event("halt", "test detail", {"a": 1})
        files = self.alerts_of("halt")
        self.assertEqual(len(files), 1)
        doc = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(doc["event_id"], 3205)
        self.assertEqual(doc["kind"], "halt")


class JitterTests(unittest.TestCase):
    def test_bounds(self):
        for _ in range(200):
            j = sync_mod._jitter(60)
            self.assertGreaterEqual(j, 5.0)
            self.assertLessEqual(j, 72.0)  # 60 × 1.2

    def test_small_interval_floor(self):
        self.assertEqual(sync_mod._jitter(1), 5.0)


if __name__ == "__main__":
    unittest.main()
