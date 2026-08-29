# -*- coding: utf-8 -*-
"""sync CLI：python -m control_plane.sync [--once] [--dry-run|--publish] [--force] [--loop [秒]]

P4.1：fetch → normalize → compile → validate，只出 candidate（--dry-run）。
P4.2：--publish 允许 validate 通过后原子发布（publish.py 负责 ACK 回滚）。
P4.7：--loop [秒]（默认 60）轮询 + revision 去重 + 0-10s jitter；validate 失败
      不发布、保持 last-good，循环继续。仅显式 CLI 启用，不注册任何计划任务。
输出（设计 §13）：
  source_revision_vector / candidate_sha256 / resource_count / exit_code
"""
import argparse
import json
import random
import sys
import time

from . import feishu_fetch
from . import normalize
from . import compile as compile_mod


def run_once(publish=False, force=False):
    """执行一次 fetch→compile→validate（→publish）。返回 (result, exit_code)。"""
    result = {"ok": True, "mode": "publish" if publish else "dry-run", "errors": []}
    prev_state = feishu_fetch.read_state()
    vector = feishu_fetch.fetch_all()
    current_vector = {k: v["rev"] for k, v in vector.items()}
    if not force and prev_state == current_vector:
        result["noop"] = True
        result["source_revision_vector"] = current_vector
        result["reason"] = "revision 未变化"
        return result, 0
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
        # fail-closed：校验失败绝不 publish，live last-good 保持不动
        return result, 1
    if publish:
        from . import publish as publish_mod
        pout = publish_mod.publish()
        result["publish"] = pout
        if pout.get("publish_status") not in ("published", "noop_same_sha"):
            result["ok"] = False
            return result, 1
    return result, 0


def _loop(interval, publish, once_min=60):
    """60 秒轮询 + 0-10s jitter（GPT §2）。异常不退出循环，逐轮记录。"""
    interval = max(int(interval or once_min), 5)
    n = 0
    while True:
        n += 1
        try:
            result, code = run_once(publish=publish)
            print(json.dumps({"loop": n, "exit": code, "noop": result.get("noop"),
                              "generation": (result.get("publish") or {}).get("generation_id"),
                              "publish_status": (result.get("publish") or {}).get("publish_status")},
                             ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001 —— 循环必须活着
            print(json.dumps({"loop": n, "fatal": "%s: %s" % (type(e).__name__, e)},
                             ensure_ascii=False), flush=True)
        time.sleep(interval + random.uniform(0, 10))


def main():
    parser = argparse.ArgumentParser(description="阶段4 资源控制平面 sync")
    parser.add_argument("--once", action="store_true", help="单次执行（默认即单次）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成 candidate，不 publish")
    parser.add_argument("--publish", action="store_true",
                        help="validate 通过后原子发布（P4.2+）")
    parser.add_argument("--force", action="store_true",
                        help="忽略 revision 去重，强制重新编译")
    parser.add_argument("--loop", nargs="?", const=60, default=None, type=int,
                        metavar="秒", help="轮询模式（默认 60s + 0-10s jitter；P4.7）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if args.loop is not None:
        print("sync --loop 启动：interval=%ss publish=%s" % (args.loop, bool(args.publish)),
              flush=True)
        _loop(args.loop, publish=args.publish)
        return 0
    if args.publish and args.dry_run:
        print("--publish 与 --dry-run 互斥", file=sys.stderr)
        return 2

    try:
        result, code = run_once(publish=args.publish, force=args.force)
    except Exception as e:  # noqa: BLE001 —— CLI 顶层，统一转 exit 码
        result = {"ok": False, "fatal": "%s: %s" % (type(e).__name__, e), "errors": []}
        code = 1
    _emit(result, args.json)
    return code


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"source_revision_vector={json.dumps(result.get('source_revision_vector', {}), ensure_ascii=False)}")
    if result.get("noop"):
        print(f"noop=true reason={result.get('reason')}")
        print("exit_code=0")
        return
    print(f"candidate_sha256={result.get('candidate_sha256')}")
    print(f"resource_count={result.get('resource_count')}")
    print(f"valid={result.get('valid')}")
    print(f"secret_findings={result.get('secret_findings')}")
    if result.get("publish"):
        print("publish=" + json.dumps(result["publish"], ensure_ascii=False))
    if result.get("normalize_warnings"):
        print(f"normalize_warnings={json.dumps(result['normalize_warnings'], ensure_ascii=False)}")
    print(f"exit_code={0 if result.get('ok') else 1}")


if __name__ == "__main__":
    sys.exit(main())
