"""Candidate 校验：schema / identity / reference / secret / limits / capability / lifecycle / security。

fail-closed：任何一类错误都拒绝发布；unknown 能力不满足任何要求。
"""
import json
import math
import re

from .schema import SCHEMA, SID_PATTERN

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_-]{16,}", "sk- key"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}", "anthropic sk-ant key"),
    (r"AIza[A-Za-z0-9_-]{20,}", "google api key"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "jwt"),
    (r"Bearer [A-Za-z0-9._-]{20,}", "bearer token"),
    (r"-----BEGIN [A-Z ]+PRIVATE KEY-----", "private key"),
    (r"(?i)\b(api_key|apikey|access_token|client_secret|app_secret|password|token)\s*[=:]\s*['\"]?[A-Za-z0-9._-]{8,}", "credential-shaped field"),
]

CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DYN_INJECT = re.compile(r"\$\{[^}]*\}|%[A-Z_]{2,}%")
PATH_TRAVERSAL = re.compile(r"\.\.(\\|/)|^[A-Za-z]:[\\/]|^[\\/]")
HTTP_NON_LOCAL = re.compile(r"^http://(?!(127\.0\.0\.1|localhost)([:/]|$))")


def scan_secrets(text):
    findings = []
    for pat, desc in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            findings.append(desc)
    return findings


def _check_limits(errors, r):
    for key in ("rpm", "rpd", "concurrency"):
        v = r["limits"].get(key)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            errors.append(f"{r['resource_id']}: limits.{key} 非法（须正整数或 null）={v!r}")


def _check_capability(errors, r):
    for key in ("tools", "vision", "json_schema"):
        v = r["capabilities"].get(key)
        if v not in ("supported", "unsupported", "unknown"):
            errors.append(f"{r['resource_id']}: capabilities.{key} 非法状态={v!r}")


def _check_lifecycle(errors, r):
    status = r.get("status")
    if status not in ("active", "paused", "draining", "disabled", "quarantined"):
        errors.append(f"{r['resource_id']}: status 非法={status!r}")
    exp = r.get("expiry_at")
    if exp is not None and not re.match(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$", str(exp)):
        errors.append(f"{r['resource_id']}: expiry_at 非法={exp!r}")
    if status == "disabled" and r.get("eligible_hint"):
        errors.append(f"{r['resource_id']}: disabled 资源不得标记可路由")
    if status == "quarantined":
        if not (r.get("quarantine_reason") or "").strip():
            errors.append(f"{r['resource_id']}: quarantined 缺少 quarantine_reason（显式隔离必须可审计）")
        if r.get("eligible_hint"):
            errors.append(f"{r['resource_id']}: quarantined 资源不得标记可路由")


def _check_security(errors, warnings, r):
    up = r.get("upstream_model") or ""
    if HTTP_NON_LOCAL.search(up):
        errors.append(f"{r['resource_id']}: 非 localhost 上游使用 http://")
    for field, val in r.items():
        if not isinstance(val, str):
            continue
        if val.startswith("file://"):
            errors.append(f"{r['resource_id']}: 禁止 file:// 引用 ({field})")
        if PATH_TRAVERSAL.search(val):
            errors.append(f"{r['resource_id']}: 路径穿越嫌疑 ({field})")
        if DYN_INJECT.search(val):
            errors.append(f"{r['resource_id']}: 动态注入 {DYN_INJECT.search(val).group(0)!r} ({field})")
        if CTRL_CHARS.search(val):
            errors.append(f"{r['resource_id']}: 控制字符 ({field})")
        if len(val) > 1024:
            warnings.append(f"{r['resource_id']}: 超长字段 {field}({len(val)})")


def validate_candidate(candidate):
    """返回 {valid, errors, warnings, secret_findings, resource_count}"""
    errors, warnings = [], []

    if not isinstance(candidate, dict):
        return {"valid": False, "errors": ["顶层非 JSON 对象"], "warnings": [],
                "secret_findings": [], "resource_count": 0}
    if candidate.get("schema_version") != SCHEMA["schema_version"]:
        errors.append(f"schema_version 不支持={candidate.get('schema_version')!r}")
    for k in SCHEMA["required_top"]:
        if k not in candidate:
            errors.append(f"缺少顶层字段 {k}")

    resources = candidate.get("resources", [])
    if not isinstance(resources, list):
        errors.append("resources 非数组")
        resources = []

    seen_ids = {}
    seen_pairs = set()
    for i, r in enumerate(resources):
        rid = r.get("resource_id")
        if not isinstance(rid, str) or not SID_PATTERN.match(rid):
            errors.append(f"resources[{i}]: resource_id 非法={rid!r}")
        else:
            if rid in seen_ids:
                errors.append(f"resource_id 重复 {rid}")
            seen_ids[rid] = i
            if not r.get("channel") or not r.get("unified_model"):
                errors.append(f"{rid}: channel/unified_model 为空")
            pair = (r.get("channel"), r.get("unified_model"), r.get("credential_ref"))
            if pair in seen_pairs:
                errors.append(f"{rid}: 同 channel/model/credential 冲突")
            seen_pairs.add(pair)
        for k in SCHEMA["resource_required"]:
            if k not in r:
                errors.append(f"resources[{i}]: 缺少字段 {k}")
        _check_limits(errors, r)
        _check_capability(errors, r)
        _check_lifecycle(errors, r)
        _check_security(errors, warnings, r)
        if r.get("credential_ref") and not re.match(r"^cred:[A-Za-z0-9_.:-]+$", str(r["credential_ref"])):
            errors.append(f"{rid}: credential_ref 格式非法={r['credential_ref']!r}")

    raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
    secret_findings = scan_secrets(raw)

    return {"valid": not errors and not secret_findings,
            "errors": errors, "warnings": warnings,
            "secret_findings": secret_findings,
            "resource_count": len(resources)}


def main(argv=None):
    """python -m control_plane.validate <candidate.json> [--json]

    不回显敏感字段值；输出 {valid, errors, warnings, secret_findings}。
    """
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="candidate 校验")
    parser.add_argument("candidate", nargs="?", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.candidate is None:
        from .config import CANDIDATE_DIR
        args.candidate = CANDIDATE_DIR / "gateway_resources.candidate.json"

    path = Path(args.candidate)
    if not path.exists():
        result = {"valid": False, "errors": [f"文件不存在 {path}"],
                  "warnings": [], "secret_findings": [], "resource_count": 0}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"valid=False errors={result['errors']}")
        return 1

    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result = {"valid": False, "errors": [f"JSON 解析失败: {e}"],
                  "warnings": [], "secret_findings": [], "resource_count": 0}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"valid=False errors={result['errors']}")
        return 1

    result = validate_candidate(candidate)
    if args.json:
        # 脱敏：错误信息可能含字段值，只输出数量级，不输出值本身
        safe = {"valid": result["valid"],
                "errors": len(result["errors"]),
                "warnings": len(result["warnings"]),
                "secret_findings": len(result["secret_findings"]),
                "resource_count": result["resource_count"]}
        print(json.dumps(safe, ensure_ascii=False, indent=2))
    else:
        print(f"valid={result['valid']} errors={len(result['errors'])} "
              f"warnings={len(result['warnings'])} "
              f"secret_findings={len(result['secret_findings'])} "
              f"resources={result['resource_count']}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
