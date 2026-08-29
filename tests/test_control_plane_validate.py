# -*- coding: utf-8 -*-
"""validate 8 类错误 + compile 确定性 单元测试（P4.1/P4.2 边界）。

运行: python tests/test_control_plane_validate.py
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from control_plane.validate import validate_candidate  # noqa: E402
from control_plane.compile import build_candidate  # noqa: E402


def make_resource(**overrides):
    r = {
        "resource_id": "cap-test-01",
        "channel": "testchan",
        "unified_model": "test-model",
        "upstream_model": "https://api.test.com/v1/test",
        "credential_ref": "cred:acc-test-1",
        "status": "active",
        "expiry_at": None,
        "limits": {"rpm": 30, "rpd": None, "concurrency": None},
        "capabilities": {"tools": "unknown", "vision": "unknown", "json_schema": "unknown"},
        "source_record_id": "rec_test_1",
    }
    r.update(overrides)
    return r


def make_candidate(resources=None, schema_version=1, **top):
    c = {
        "schema_version": schema_version,
        "generation_id": "20260829T000000Z-abcdef12",
        "generated_at": "2026-08-29T00:00:00+08:00",
        "source": {"type": "feishu_base", "table_revisions": {"资源实例表": 54}},
        "resources": resources if resources is not None else [make_resource()],
    }
    c.update(top)
    return c


class TestValidateValidFixture(unittest.TestCase):
    def test_valid_candidate_passes(self):
        res = validate_candidate(make_candidate())
        self.assertTrue(res["valid"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["secret_findings"], [])
        self.assertEqual(res["resource_count"], 1)


class TestSchema(unittest.TestCase):
    def test_unsupported_schema_version(self):
        res = validate_candidate(make_candidate(schema_version=99))
        self.assertFalse(res["valid"])
        self.assertTrue(any("schema_version" in e for e in res["errors"]))

    def test_missing_top_field(self):
        c = make_candidate()
        del c["resources"]
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("resources" in e for e in res["errors"]))

    def test_missing_required_resource_field(self):
        c = make_candidate([make_resource()])
        del c["resources"][0]["channel"]
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("channel" in e for e in res["errors"]))

    def test_resources_not_list(self):
        res = validate_candidate(make_candidate(resources="nope"))
        self.assertFalse(res["valid"])


class TestIdentity(unittest.TestCase):
    def test_duplicate_resource_id(self):
        c = make_candidate([make_resource(), make_resource()])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("重复" in e for e in res["errors"]))

    def test_empty_channel_or_model(self):
        c = make_candidate([make_resource(channel="")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("channel/unified_model 为空" in e for e in res["errors"]))

    def test_same_channel_model_cred_conflict(self):
        c = make_candidate([
            make_resource(resource_id="cap-test-01"),
            make_resource(resource_id="cap-test-02"),
        ])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("冲突" in e for e in res["errors"]))


class TestReference(unittest.TestCase):
    def test_bad_credential_ref_format(self):
        c = make_candidate([make_resource(credential_ref="sk-somethingraw")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("credential_ref 格式非法" in e for e in res["errors"]))

    def test_missing_credential_ref_field(self):
        c = make_candidate([make_resource()])
        del c["resources"][0]["credential_ref"]
        res = validate_candidate(c)
        self.assertFalse(res["valid"])


class TestSecretBoundary(unittest.TestCase):
    def test_sk_key_blocked(self):
        c = make_candidate([make_resource(credential_ref="cred:acc-1")])
        c["resources"][0]["upstream_model"] = "sk-proj-abcdef1234567890abcdef"
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(res["secret_findings"])

    def test_jwt_blocked(self):
        c = make_candidate([make_resource()])
        c["resources"][0]["unified_model"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(res["secret_findings"])

    def test_bearer_blocked(self):
        c = make_candidate([make_resource()])
        c["resources"][0]["credential_ref"] = "Bearer abcdefghijklmnopqrstuvwxyz123456"
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(res["secret_findings"])


class TestLimits(unittest.TestCase):
    def test_zero_or_negative(self):
        c = make_candidate([make_resource(limits={"rpm": 0, "rpd": None, "concurrency": None})])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("limits" in e for e in res["errors"]))

    def test_non_integer(self):
        c = make_candidate([make_resource(limits={"rpm": 1.5, "rpd": None, "concurrency": None})])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("limits" in e for e in res["errors"]))


class TestCapability(unittest.TestCase):
    def test_invalid_capability_state(self):
        c = make_candidate([make_resource(capabilities={"tools": "maybe"})])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("capabilities" in e for e in res["errors"]))


class TestLifecycle(unittest.TestCase):
    def test_invalid_status(self):
        c = make_candidate([make_resource(status="expired-now")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])

    def test_invalid_expiry(self):
        c = make_candidate([make_resource(expiry_at="not-a-date")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("expiry_at" in e for e in res["errors"]))

    def test_disabled_marked_routable(self):
        c = make_candidate([make_resource(status="disabled", eligible_hint=True)])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("disabled" in e for e in res["errors"]))


class TestSecurity(unittest.TestCase):
    def test_non_local_http_endpoint(self):
        c = make_candidate([make_resource(upstream_model="http://api.evil.com/v1")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("http://" in e for e in res["errors"]))

    def test_file_uri(self):
        c = make_candidate([make_resource(unified_model="file:///etc/passwd")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])

    def test_env_injection(self):
        c = make_candidate([make_resource(upstream_model="https://api.test.com/${ENV_SECRET}")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])
        self.assertTrue(any("注入" in e for e in res["errors"]))

    def test_control_chars(self):
        c = make_candidate([make_resource(channel="bad\x07chan")])
        res = validate_candidate(c)
        self.assertFalse(res["valid"])


class TestCompileDeterminism(unittest.TestCase):
    def test_same_input_same_hash(self):
        revs = {"资源实例表": 54, "资源能力规格表": 39}
        resources = [make_resource(), make_resource(resource_id="cap-test-02")]
        _, h1 = build_candidate(revs, resources)
        _, h2 = build_candidate(revs, resources)
        self.assertEqual(h1, h2)

    def test_revision_change_changes_hash(self):
        resources = [make_resource()]
        _, h1 = build_candidate({"资源实例表": 54}, resources)
        _, h2 = build_candidate({"资源实例表": 55}, resources)
        self.assertNotEqual(h1, h2)

    def test_content_change_changes_hash(self):
        _, h1 = build_candidate({"资源实例表": 54}, [make_resource()])
        _, h2 = build_candidate({"资源实例表": 54}, [make_resource(status="paused")])
        self.assertNotEqual(h1, h2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
