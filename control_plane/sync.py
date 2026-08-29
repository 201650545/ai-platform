"""sync CLI：python -m control_plane.sync --once [--dry-run] [--force]

P4.1 只做 fetch → normalize → compile → validate，绝不 publish。
输出（设计 §13）：
  source_revision_vector / candidate_sha256 / resource_count / exit_code
"""
import argparse
import json
import sys

from . import feishu_fetch
from . import normalize
from . import compile as compile_mod


def main():
    parser = argparse.ArgumentParser(description="阶段4 资源控制平面 sync")
    parser.add_argument("--once", action="store_true", help="单次执行（默认即单次）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成 candidate，不 publish（P4.1 唯一允许模式）")
    parser.add_argument("--force", action="store_true",
                        help="忽略 revision 去重，强制重新编译")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if not args.dry_run:
        print("P4.1 只允许 --dry-run；publish 待 P4.3 引入。", file=sys.stderr)
        return 2

    result = {"ok": True, "mode": "dry-run", "errors": []}
    try:
        prev_state = feishu_fetch.read_state()
        vector = feishu_fetch.fetch_all()
        current_vector = {k: v["rev"] for k, v in vector.items()}
        if not args.force and prev_state == current_vector:
            result["noop"] = True
            result["source_revision_vector"] = current_vector
            result["reason"] = "revision 未变化"
            _emit(result, args.json)
            return 0
        feishu_fetch.write_state(vector)

        summary = normalize.normalize_all()
        resources = summary["resources"]
        table_revisions = {k: v for k, v in vector.items()}
        candidate, canonical_sha256, vres = compile_mod.run_compile(
            table_revisions, resources, summary["warnings"])

        result.update({
            "noop": False,
            "source_revision_vector": current_vector,
            "candidate_sha256": canonical_sha256,
            "resource_count": len(resources),
            "valid": vres["valid"],
            "errors": vres["errors"],
            "warnings": vres["warnings"],
            "secret_findings": vres["secret_findings"],
            "normalize_warnings": summary["warnings"],
            "candidate_file": str(compile_mod.CANDIDATE_FILE),
        })
        if not vres["valid"]:
            result["ok"] = False
            _emit(result, args.json)
            return 1
        _emit(result, args.json)
        return 0
    except Exception as e:  # noqa: BLE001 —— CLI 顶层，统一转 exit 码
        result.update({"ok": False, "fatal": f"{type(e).__name__}: {e}"})
        _emit(result, args.json)
        return 1


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"source_revision_vector={json.dumps(result.get('source_revision_vector', {}), ensure_ascii=False)}")
    if result.get("noop"):
        print(f"noop=true reason={result.get('reason')}")
        return
    print(f"candidate_sha256={result.get('candidate_sha256')}")
    print(f"resource_count={result.get('resource_count')}")
    print(f"valid={result.get('valid')}")
    print(f"errors={result.get('errors')}")
    print(f"secret_findings={result.get('secret_findings')}")
    if result.get("normalize_warnings"):
        print(f"normalize_warnings={json.dumps(result['normalize_warnings'], ensure_ascii=False)}")
    if not result.get("ok"):
        print(f"exit_code=1")
    print(f"exit_code={0 if result.get('ok') else 1}")


if __name__ == "__main__":
    sys.exit(main())
