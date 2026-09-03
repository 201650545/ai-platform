"""Compile：normalize 结果 → candidate.json（dry-run 产物，不 publish）。

确定性（P4.1 验收判据 2）：
  canonical_sha256 只覆盖 schema_version + table_revisions + resources（不含时间戳），
  同一 revision vector 连续编译哈希一致；generation_id/generated_at 仅作元数据。
"""
import datetime
import hashlib
import json
from pathlib import Path

from .config import CANDIDATE_DIR, REPORTS_DIR, ensure_runtime_dirs
from .validate import validate_candidate

CANDIDATE_FILE = CANDIDATE_DIR / "gateway_resources.candidate.json"
UTC8 = datetime.timezone(datetime.timedelta(hours=8))


def canonical_content(schema_version, table_revisions, resources):
    """参与哈希的确定性内容。"""
    return {
        "schema_version": schema_version,
        "table_revisions": dict(sorted(table_revisions.items())),
        "resources": resources,
    }


def build_candidate(table_revisions, resources, table_stats=None):
    """构造 candidate dict。返回 (candidate, canonical_sha256)。"""
    schema_version = 1
    content = canonical_content(schema_version, table_revisions, resources)
    canonical_sha256 = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    now = datetime.datetime.now(UTC8)
    candidate = {
        "schema_version": schema_version,
        "generation_id": f"{now.strftime('%Y%m%dT%H%M%SZ')}-{canonical_sha256[:8]}",
        "generated_at": now.isoformat(timespec="seconds"),
        "canonical_sha256": canonical_sha256,
        "source": {
            "type": "feishu_base",
            "table_revisions": dict(sorted(table_revisions.items())),
            "tables": table_stats or {},
        },
        "resources": resources,
    }
    return candidate, canonical_sha256


def write_candidate(candidate, canonical_sha256):
    ensure_runtime_dirs()
    CANDIDATE_FILE.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return CANDIDATE_FILE


def write_report(candidate, canonical_sha256, validate_result, warnings):
    ensure_runtime_dirs()
    report = {
        "generation_id": candidate["generation_id"],
        "canonical_sha256": canonical_sha256,
        "validate": validate_result,
        "normalize_warnings": warnings,
        "resource_count": len(candidate["resources"]),
    }
    path = REPORTS_DIR / f"validate-{canonical_sha256[:16]}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def run_compile(table_revisions, resources, warnings):
    """完整 compile 流程：构造 candidate → 写盘 → validate → report。

    返回 (candidate, canonical_sha256, validate_result)。
    """
    stats = {
        name: {"rev": meta["rev"], "record_count": meta["record_count"]}
        for name, meta in table_revisions.items()
    }
    candidate, canonical_sha256 = build_candidate(table_revisions, resources)
    validate_result = validate_candidate(candidate)
    write_candidate(candidate, canonical_sha256)
    write_report(candidate, canonical_sha256, validate_result, warnings)
    return candidate, canonical_sha256, validate_result
