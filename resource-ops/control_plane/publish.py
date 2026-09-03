# -*- coding: utf-8 -*-
"""Publish：candidate → gateway_resources.json 原子发布（GPT 设计 §6/§8/§13）。

铁律：
- 发布前置校验 fail-closed：candidate 必须通过 validate_candidate，否则 exit!=0、
  published=false、live 文件不动；
- 原子替换：gateway_resources.json.tmp.<pid> → fsync → os.replace()，watcher 只会
  看到完整旧文件或完整新文件；
- publisher ACK rollback（GPT §8 第二层）：发布后轮询
  GET /api/resource-config/status（≤wait_ack 秒），active_generation_id 未变成新
  generation 即视为网关拒绝加载 → 用发布前的 live 字节原子回滚；
- 历史：每次被替换的 generation 存 resource_history/<generation_id>.json（保留 20 份），
  rollback --previous 原子回退到上一个历史 generation。

CLI（GPT §13）：
  python -m control_plane.publish --candidate <path> [--wait-ack 10] [--json]
  python -m control_plane.publish rollback --previous [--json]

生成物路径：GATEWAY_DATA_DIR（默认 D:\\项目\\data\\search_gateway，env 可覆盖）。
本模块绝不写渠道 key/凭证，也不读飞书。
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from .config import CANDIDATE_DIR
from .validate import validate_candidate

GATEWAY_DATA_DIR = Path(os.environ.get(
    "GATEWAY_DATA_DIR", r"D:\项目\data\search_gateway"))
LIVE_NAME = "gateway_resources.json"
HISTORY_DIRNAME = "resource_history"
STATUS_URL = os.environ.get(
    "GATEWAY_STATUS_URL", "http://127.0.0.1:3100/api/resource-config/status")
HISTORY_KEEP = 20


def _live_path():
    return GATEWAY_DATA_DIR / LIVE_NAME


def _history_dir():
    d = GATEWAY_DATA_DIR / HISTORY_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, data: bytes):
    tmp = Path(str(path) + (".tmp.%d" % os.getpid()))
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_generation(data: bytes):
    try:
        doc = json.loads(data.decode("utf-8"))
        return doc.get("generation_id"), doc.get("canonical_sha256")
    except Exception:  # noqa: BLE001
        return None, None


def _prune_history():
    files = sorted(_history_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
    for p in files[:-HISTORY_KEEP]:
        try:
            p.unlink()
        except OSError:
            pass


def _gateway_ack(generation_id, deadline):
    """轮询状态端点直到 active_generation_id==generation_id 或超时。"""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(STATUS_URL, timeout=2) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("active_generation_id") == generation_id:
                    return True, payload
        except Exception:  # noqa: BLE001 —— 网关暂不可达继续等到超时
            pass
        time.sleep(1.0)
    return False, None


def publish(candidate_path=None, wait_ack=10.0):
    """发布 candidate。返回结果 dict；调用方据 publish_status/exit code 判定。

    publish_status: published / rolled_back / noop_same_sha / invalid_candidate
    """
    path = Path(candidate_path) if candidate_path else CANDIDATE_DIR / "gateway_resources.candidate.json"
    result = {"candidate_file": str(path), "live_file": str(_live_path()),
              "publish_status": None, "gateway_ack": None,
              "generation_id": None, "previous_generation_id": None}
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        result.update(publish_status="invalid_candidate", error="candidate 读取/解析失败: %s" % e.__class__.__name__)
        return result
    vres = validate_candidate(candidate)
    if not vres["valid"]:
        result.update(publish_status="invalid_candidate",
                      errors=len(vres["errors"]),
                      secret_findings=len(vres["secret_findings"]))
        return result

    live = _live_path()
    prev_bytes = None
    if live.exists():
        prev_bytes = live.read_bytes()
        prev_gen, prev_sha = _read_generation(prev_bytes)
        result["previous_generation_id"] = prev_gen
        if prev_sha and prev_sha == candidate.get("canonical_sha256"):
            # 同一内容重复发布：幂等 noop，等 ACK 汇报现状即可
            ack, _ = _gateway_ack(candidate.get("generation_id"), time.time() + wait_ack)
            result.update(publish_status="noop_same_sha", gateway_ack=ack,
                          generation_id=candidate.get("generation_id"))
            return result

    raw = json.dumps(candidate, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write(live, raw)
    # 历史归档（发布前的旧 generation）
    if prev_bytes is not None and result["previous_generation_id"]:
        try:
            _atomic_write(_history_dir() / (result["previous_generation_id"] + ".json"), prev_bytes)
            _prune_history()
        except OSError:
            pass

    result["generation_id"] = candidate.get("generation_id")
    ack, payload = _gateway_ack(result["generation_id"], time.time() + wait_ack)
    result["gateway_ack"] = ack
    if ack:
        result["publish_status"] = "published"
        return result

    # ACK 超时 → 网关拒绝/未加载 → 原子回滚到发布前内容（GPT §8 第二层）
    if prev_bytes is not None:
        _atomic_write(live, prev_bytes)
        result["publish_status"] = "rolled_back"
    else:
        # 发布前无 live（首次发布失败）：移除残缺 live，避免 watcher 撞坏文件
        try:
            live.unlink()
        except OSError:
            pass
        result["publish_status"] = "rolled_back_no_previous"
    return result


def rollback_previous():
    """把 live 原子回退到 resource_history 中最近一份不等于当前 generation 的历史。"""
    live = _live_path()
    cur_gen, _ = _read_generation(live.read_bytes()) if live.exists() else (None, None)
    files = sorted(_history_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        if p.stem != cur_gen:
            data = p.read_bytes()
            _atomic_write(live, data)
            gen, _ = _read_generation(data)
            return {"publish_status": "rolled_back", "generation_id": gen,
                    "previous_generation_id": cur_gen, "source": str(p)}
    return {"publish_status": "no_history_to_rollback", "generation_id": cur_gen}


def main(argv=None):
    parser = argparse.ArgumentParser(description="控制平面原子发布")
    parser.add_argument("--candidate", default=None)
    parser.add_argument("--wait-ack", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("rollback", help="回滚到上一 generation")
    sub.add_parser("status", help="查看网关加载状态")
    args = parser.parse_args(argv)

    if args.cmd == "status":
        try:
            with urllib.request.urlopen(STATUS_URL, timeout=3) as resp:
                print(json.dumps(json.loads(resp.read().decode("utf-8")),
                                 ensure_ascii=False, indent=2))
            return 0
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": "status 不可达: %s" % e.__class__.__name__},
                             ensure_ascii=False))
            return 1
    if args.cmd == "rollback":
        out = rollback_previous()
        ok = out.get("publish_status") == "rolled_back"
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(out, ensure_ascii=False))
        return 0 if ok else 1

    out = publish(args.candidate, args.wait_ack)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))
    ok = out.get("publish_status") in ("published", "noop_same_sha")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
