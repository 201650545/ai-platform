# -*- coding: utf-8 -*-
"""sync CLI：python -m control_plane.sync [--once] [--dry-run|--publish] [--force]
                          [--loop [秒]] [--clear-halt] [--json]

阶段4（保留语义，run_once 未改）：fetch → normalize → compile → validate 只出
candidate（默认单次 dry-run）；--publish 允许 validate 通过后原子发布
（publish.py 负责 ACK 超时回滚）；revision 去重；validate 失败绝不发布
（fail-closed）。

阶段5（Claude 裁定 S5-PIPELINE-DESIGN-2026，Q1-Q8 落地）：
- --loop [秒]（默认 60）：常驻轮询 + 单实例文件租约（lease.py；启动被拒退出
  3110、运行中失去租约退出 3111，绝不空转）。
- 三类失败区分（Q4）：
  ① fetch 失败 → 指数退避 60s×2、上限 1800s、±20% 比例抖动；
  ② validate 失败 → 不退避，按"原始输入哈希是否变化"计数，同一输入连续
    HALT_VALIDATE_THRESHOLD 次失败 → halted 熔断（事件 3205），期间仍 fetch
    探活但绝不 validate/publish，仅 --clear-halt 显式解除；
  ③ ACK 超时/回滚 → 对同一 candidate 按 loop 节奏短固定重试，连续
    ACK_ESCALATE_THRESHOLD 次或 24h 回滚达 ROLLBACK_TREND_24H 次 → 升级事件
    3204（去抖 10 分钟）。
- 防振荡 v1（Q5）：noop_same_sha 幂等 + ACK 回滚冷却期 COOLDOWN_MULTIPLIER×
  loop 间隔 + 最小发布间隔 MIN_PUBLISH_INTERVAL_S（单位时间代际上限与 K 次稳
  定门明确不做）。
- 观测（Q7）：control_plane_state.json（单文件原子覆写，watchdog/人 O(1) 读）
  + control_plane.log（JSONL、512KB 轮转）+ alert 文件 + Windows 事件
  3201-3205（事件源 API3100ControlPlane，与网关 3105 号段严格分离）。
- 重启恢复（Q6）：无特殊逻辑；启动时若处于 halted 则保持 halted，不自动恢复。
- 范围边界（Q8）：per-key 凭证解析与渠道级 gating 全部 defer，本阶段维持
  channel_name_mapped。
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time

from . import feishu_fetch
from . import normalize
from . import compile as compile_mod
from . import publish as publish_mod
from . import state as state_mod
from .lease import Lease, LeaseOccupied, EXIT_LEASE_OCCUPIED, EXIT_LEASE_LOST
from .config import RAW_DIR, CANDIDATE_DIR

# ---- 阶段5 定值（Q4/Q5/Q3）----
BASE_BACKOFF_S = 60            # fetch 退避基值（与默认 loop 间隔一致）
MAX_BACKOFF_S = 1800           # fetch 退避上限 30 分钟
MIN_PUBLISH_INTERVAL_S = 60    # 任意两次 publish 最小间隔（Q5 兜底）
COOLDOWN_MULTIPLIER = 5        # ACK 回滚冷却 = 5 × loop 间隔（Q5）
HALT_VALIDATE_THRESHOLD = 3    # 同一原始输入连续 validate 失败熔断阈值（Q4）
ACK_ESCALATE_THRESHOLD = 3     # ACK 连续超时升级告警阈值（Q4）
ROLLBACK_TREND_24H = 6         # 24h 回滚次数趋势阈值（Q4）
ALERT_DEBOUNCE_S = 600         # 3204 去抖 10 分钟（Q3）
CANDIDATE_NAME = "gateway_resources.candidate.json"

_LAST_ALERT_AT = {}            # 3204 去抖时间戳（进程内）


def _debounce_ok(key, min_gap_s=ALERT_DEBOUNCE_S):
    now = time.time()
    if now - _LAST_ALERT_AT.get(key, 0.0) < min_gap_s:
        return False
    _LAST_ALERT_AT[key] = now
    return True


def _raw_input_hash():
    """原始 fetch 输入哈希（Q4 熔断判据）：RAW_DIR 快照文件名+字节。

    必须取 fetch 后、validate 前的原始内容，而非 validate 后的 canonical_sha256
    ——后者衡量"编译产物"，前者衡量"上游输入"，熔断要回答的是"同一份坏输入
    是否还在反复触发失败"。
    """
    h = hashlib.sha256()
    for p in sorted(RAW_DIR.glob("*.json")):
        h.update(p.name.encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _jitter(interval_s):
    """±20% 比例抖动，下限 5s（Q4）。"""
    return max(5.0, float(interval_s) * random.uniform(0.8, 1.2))


def run_once(publish=False, force=False):
    """执行一次 fetch→compile→validate（→publish）。返回 (result, exit_code)。

    阶段4 语义原样保留：循环模式的发布门禁不在这里，由 _tick 统一管。
    """
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
        pout = publish_mod.publish()
        result["publish"] = pout
        if pout.get("publish_status") not in ("published", "noop_same_sha"):
            result["ok"] = False
            return result, 1
    return result, 0


# ---------------- 阶段5：单轮 _tick 与三类失败处理 ----------------

def _record_validate_fail(st, input_hash, errors, stage):
    """Q4 第二类：validate 失败不退避。

    同一原始输入连续 HALT_VALIDATE_THRESHOLD 次失败 → halted 熔断（3205）；
    输入已变化则重新计数（新候选按正常节奏重试）。
    """
    same = (st.get("last_input_hash") == input_hash and
            (st.get("consecutive_validate_failures") or 0) > 0)
    n = ((st.get("consecutive_validate_failures") or 0) + 1) if same else 1
    fields = dict(
        consecutive_fetch_failures=0,
        last_run_at=state_mod.now_iso(),
        last_run_result="validate_fail",
        current_backoff_interval_s=0,
        consecutive_validate_failures=n,
        last_input_hash=input_hash)
    if same and n >= HALT_VALIDATE_THRESHOLD:
        fields.update(halted=True,
                      halted_since=state_mod.now_iso(),
                      halted_reason="%s 阶段连续 %d 次 validate 失败且原始输入未变"
                                    % (stage, n),
                      halted_input_hash=input_hash)
        state_mod.update_state(**fields)
        state_mod.emit_event(
            "halt",
            "毒 candidate 熔断：连续 %d 次 validate 失败、原始输入 sha=%s 未变，"
            "已进入 halted（仅 --clear-halt 可解除）" % (n, input_hash[:12]),
            {"stage": stage, "consecutive_validate_failures": n,
             "input_hash": input_hash, "errors": (errors or [])[:5]})
        state_mod.log_event("halt_enter", stage=stage, n=n,
                            input_hash=input_hash[:12])
    else:
        state_mod.update_state(**fields)
        state_mod.log_event("validate_fail", stage=stage, n=n,
                            input_hash=input_hash[:12],
                            errors=(errors or [])[:5])


def _tick_halted(st, interval_s):
    """halted 态单轮（Q4）：仍 fetch 探活检测上游是否被修复，但绝不
    validate/publish——即使原始输入变化也不自动恢复（Q6：--clear-halt 才解除）。
    """
    try:
        feishu_fetch.fetch_all()
    except Exception as e:  # noqa: BLE001
        n = (st.get("consecutive_fetch_failures") or 0) + 1
        backoff = min(BASE_BACKOFF_S * (2 ** (n - 1)), MAX_BACKOFF_S)
        state_mod.update_state(
            consecutive_fetch_failures=n,
            last_run_at=state_mod.now_iso(),
            last_run_result="fetch_fail",
            current_backoff_interval_s=backoff)
        state_mod.log_event("halted_fetch_fail", n=n,
                            err="%s: %s" % (type(e).__name__, e),
                            next_backoff_s=backoff)
        return float(backoff)
    ih = _raw_input_hash()
    changed = (ih != st.get("halted_input_hash"))
    state_mod.update_state(
        consecutive_fetch_failures=0,
        last_run_at=state_mod.now_iso(),
        last_run_result="halted_fetch_ok",
        last_fetch_ok_at=state_mod.now_iso(),
        current_backoff_interval_s=0,
        halted_input_hash=ih)
    state_mod.log_event("halted_fetch_ok", input_changed=changed,
                        input_hash=ih[:12],
                        note="仅 fetch 比对；--clear-halt 后恢复完整流水线")
    return float(interval_s)


def _publish_allowed(st):
    """Q5 门禁：ACK 回滚冷却期 + 最小发布间隔。返回 (allowed, (reason, remain))。"""
    now = time.time()
    cooldown_until = st.get("cooldown_until") or 0
    if now < cooldown_until:
        return False, ("rollback_cooldown", round(cooldown_until - now))
    if st.get("last_publish_at"):
        try:
            last_pub = time.mktime(time.strptime(
                st["last_publish_at"], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            last_pub = 0
        if now - last_pub < MIN_PUBLISH_INTERVAL_S:
            return False, ("min_publish_interval",
                           round(MIN_PUBLISH_INTERVAL_S - (now - last_pub)))
    return True, None


def _suppress(st, reason, remain_s):
    state_mod.update_state(
        publish_suppressed_count=(st.get("publish_suppressed_count") or 0) + 1)
    state_mod.log_event("publish_suppressed", reason=reason, remain_s=remain_s)


def _handle_publish_result(st, pout, candidate_sha=None, retry=False):
    """发布结果落状态（published/noop_same_sha/invalid/rolled_back 三分支）。
    返回 publish_status 供调用方续处理。"""
    status = pout.get("publish_status")
    attempts = (st.get("publish_attempt_count") or 0) + 1
    if status in ("published", "noop_same_sha"):
        state_mod.update_state(
            publish_attempt_count=attempts,
            last_publish_at=state_mod.now_iso(),
            last_publish_gen=pout.get("generation_id"),
            last_publish_sha256=candidate_sha,
            last_ack_result="ok" if pout.get("gateway_ack") else "timeout",
            consecutive_ack_timeouts=0)
        state_mod.log_event("publish_ok", status=status, retry=retry,
                            gen=pout.get("generation_id"),
                            ack=bool(pout.get("gateway_ack")))
        return status
    if status == "invalid_candidate":
        # compile 侧 validator 已通过但 publish 侧独立 validator 拒绝——
        # 按毒 candidate 计数（复用 Q4 熔断，stage=publish）
        state_mod.update_state(publish_attempt_count=attempts)
        state_mod.log_event("publish_invalid", gen=pout.get("generation_id"))
        return status
    # rolled_back / rolled_back_no_previous → ACK 超时链（Q4 第三类 + Q5 冷却）
    rollback_times = state_mod.prune_rollbacks(st)
    rollback_times.append(state_mod.now_iso())
    n_ack = (st.get("consecutive_ack_timeouts") or 0) + 1
    cooldown = time.time() + COOLDOWN_MULTIPLIER * (st.get("loop_interval_s") or 60)
    state_mod.update_state(
        publish_attempt_count=attempts,
        last_ack_result="timeout",
        last_rollback_at=state_mod.now_iso(),
        rollback_times=rollback_times,
        cooldown_until=cooldown,
        consecutive_ack_timeouts=n_ack,
        consecutive_validate_failures=0,
        last_input_hash=None)
    state_mod.log_event("rollback", status=status, retry=retry,
                        gen=pout.get("generation_id"), n_ack=n_ack,
                        cooldown_until_s=round(cooldown))
    if n_ack >= ACK_ESCALATE_THRESHOLD and _debounce_ok("rollback_trend_ack"):
        state_mod.emit_event(
            "rollback_trend",
            "ACK 连续超时/回滚 %d 次（status=%s），已进入 %ds 冷却"
            % (n_ack, status, COOLDOWN_MULTIPLIER * (st.get("loop_interval_s") or 60)),
            {"consecutive_ack_timeouts": n_ack,
             "generation_id": pout.get("generation_id"), "retry": retry})
    if len(rollback_times) >= ROLLBACK_TREND_24H and \
            _debounce_ok("rollback_trend_24h"):
        state_mod.emit_event(
            "rollback_trend",
            "24h 内回滚达 %d 次（趋势异常）" % len(rollback_times),
            {"rollback_times_24h": len(rollback_times)})
    return status


def _retry_publish_after_ack_timeout(interval_s):
    """Q4 第三类：ACK 超时后对同一 candidate 短固定重试（loop 节奏，受 Q5 门禁
    约束），连续 ACK_ESCALATE_THRESHOLD 次失败后升级 3204 并停止自动重试。
    """
    st = state_mod.load_state()
    if not (CANDIDATE_DIR / CANDIDATE_NAME).exists():
        state_mod.update_state(last_ack_result="none")
        state_mod.log_event("retry_skip", reason="candidate 文件不存在")
        return float(interval_s)
    allowed, why = _publish_allowed(st)
    if not allowed:
        state_mod.log_event("retry_deferred", reason=why[0], remain_s=why[1])
        return float(interval_s)
    state_mod.log_event("publish_retry",
                        n_ack=st.get("consecutive_ack_timeouts") or 0)
    pout = publish_mod.publish()
    _handle_publish_result(st, pout, candidate_sha=None, retry=True)
    return float(interval_s)


def _tick(interval_s, publish, force):
    """阶段5 单轮。返回下一轮建议等待秒数（调用方叠加 ±20% 抖动）。"""
    st = state_mod.load_state()

    # ---- halted 态（Q4/Q6）：只 fetch 探活 ----
    if st.get("halted"):
        return _tick_halted(st, interval_s)

    # 上轮 validate 失败未决 → 本轮 force 全量重算（否则 revision 去重会把
    # 熔断计数饿死，永远到不了 3 次——Q9 验收 3 要求自然经历 3 个周期）
    pending_vf = (st.get("consecutive_validate_failures") or 0) > 0

    # ---- fetch/normalize/compile/validate（Q4 第一类：异常 → 指数退避）----
    try:
        result, code = run_once(publish=False, force=force or pending_vf)
    except Exception as e:  # noqa: BLE001
        n = (st.get("consecutive_fetch_failures") or 0) + 1
        backoff = min(BASE_BACKOFF_S * (2 ** (n - 1)), MAX_BACKOFF_S)
        state_mod.update_state(
            consecutive_fetch_failures=n,
            last_run_at=state_mod.now_iso(),
            last_run_result="fetch_fail",
            current_backoff_interval_s=backoff)
        state_mod.log_event("fetch_fail", n=n,
                            err="%s: %s" % (type(e).__name__, e),
                            next_backoff_s=backoff)
        return float(backoff)

    if result.get("noop"):
        # revision 未变化；但 ACK 超时未决时同一 candidate 需短固定重试（Q4）
        state_mod.update_state(
            consecutive_fetch_failures=0,
            last_run_at=state_mod.now_iso(),
            last_run_result="noop",
            last_fetch_ok_at=state_mod.now_iso(),
            current_backoff_interval_s=0)
        if publish and st.get("last_ack_result") == "timeout" and \
                (st.get("consecutive_ack_timeouts") or 0) < ACK_ESCALATE_THRESHOLD:
            return _retry_publish_after_ack_timeout(interval_s)
        return float(interval_s)

    input_hash = _raw_input_hash()

    if not result.get("valid"):
        _record_validate_fail(st, input_hash, result.get("errors"), stage="compile")
        return float(interval_s)

    # ---- validate 通过 → 发布阶段（Q5 门禁）----
    state_mod.update_state(
        consecutive_fetch_failures=0,
        consecutive_validate_failures=0,
        last_input_hash=None,
        last_run_at=state_mod.now_iso(),
        last_run_result="validate_ok",
        last_fetch_ok_at=state_mod.now_iso(),
        current_backoff_interval_s=0)
    if not publish:
        state_mod.log_event("validate_ok", dry_run=True,
                            sha=(result.get("candidate_sha256") or "")[:12])
        return float(interval_s)

    st = state_mod.load_state()
    allowed, why = _publish_allowed(st)
    if not allowed:
        _suppress(st, why[0], why[1])
        return float(interval_s)

    state_mod.log_event("publish_attempt",
                        sha=(result.get("candidate_sha256") or "")[:12])
    pout = publish_mod.publish()
    status = _handle_publish_result(st, pout,
                                    candidate_sha=result.get("candidate_sha256"))
    if status == "invalid_candidate":
        st2 = state_mod.load_state()
        _record_validate_fail(st2, _raw_input_hash(),
                              ["publish 侧 validator 拒绝该 candidate"],
                              stage="publish")
    return float(interval_s)


def _clear_halt():
    """Q4：毒 candidate 熔断的唯一解除途径。"""
    st = state_mod.load_state()
    if not st.get("halted"):
        print("halted=false：当前未处于熔断态，无需解除")
        return 0
    state_mod.update_state(halted=False, halted_reason=None, halted_since=None,
                           halted_input_hash=None,
                           consecutive_validate_failures=0,
                           last_input_hash=None)
    state_mod.log_event("halt_clear", note="显式 --clear-halt 解除")
    print("halt 已解除：下一轮恢复完整 fetch→validate→publish 流水线")
    return 0


def _loop(interval, publish):
    """常驻循环（Q1/Q2/Q6）。退出码：0 正常停止、3110 租约被占用、
    3111 运行中失去租约。绝不空转。"""
    interval = max(int(interval or 60), 5)
    state_mod.update_state(loop_interval_s=interval, pid=os.getpid())
    lease = Lease()
    try:
        try:
            lease.acquire()
        except LeaseOccupied as occ:
            holder = occ.holder or {}
            state_mod.log_event("lease_refused", holder_pid=holder.get("pid"))
            state_mod.emit_event(
                "lease_conflict",
                "启动被拒：租约被 pid=%s 持有（心跳未陈旧），本进程以 3110 退出，"
                "不空转" % holder.get("pid"),
                {"holder": holder})
            print("exit_code=%d lease occupied by pid=%s"
                  % (EXIT_LEASE_OCCUPIED, holder.get("pid")), flush=True)
            return EXIT_LEASE_OCCUPIED
        lease.start_heartbeat()
        st = state_mod.load_state()
        if st.get("halted"):
            state_mod.log_event("restart_halted", reason=st.get("halted_reason"),
                                since=st.get("halted_since"))
            print("启动时处于 halted 态（Q6）：保持 halted，仅 fetch 探活，"
                  "--clear-halt 解除", flush=True)
        print("sync --loop 启动：interval=%ss publish=%s pid=%d"
              % (interval, bool(publish), os.getpid()), flush=True)
        n = 0
        while True:
            if lease.lost():
                state_mod.log_event("lease_lost_exit")
                print("exit_code=%d lease lost" % EXIT_LEASE_LOST, flush=True)
                return EXIT_LEASE_LOST
            n += 1
            try:
                wait_s = _tick(interval, publish=publish, force=False)
                print(json.dumps({"tick": n, "wait_s": round(wait_s)},
                                 ensure_ascii=False), flush=True)
            except Exception as e:  # noqa: BLE001 —— 循环必须活着
                state_mod.log_event("tick_fatal",
                                    err="%s: %s" % (type(e).__name__, e))
                print(json.dumps({"tick": n, "fatal": "%s: %s"
                                  % (type(e).__name__, e)},
                                 ensure_ascii=False), flush=True)
                wait_s = float(interval)
            time.sleep(_jitter(wait_s))
    except KeyboardInterrupt:
        print("收到中断，正常退出", flush=True)
        return 0
    finally:
        lease.release()


def main():
    parser = argparse.ArgumentParser(description="资源控制平面 sync（阶段4+5）")
    parser.add_argument("--once", action="store_true", help="单次执行（默认即单次）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成 candidate，不 publish")
    parser.add_argument("--publish", action="store_true",
                        help="validate 通过后原子发布（publish.py 负责 ACK 回滚）")
    parser.add_argument("--force", action="store_true",
                        help="忽略 revision 去重，强制重新编译")
    parser.add_argument("--loop", nargs="?", const=60, default=None, type=int,
                        metavar="秒",
                        help="常驻轮询（默认 60s；阶段5：租约+三类退避+熔断）")
    parser.add_argument("--clear-halt", action="store_true",
                        help="解除毒 candidate 熔断 halted（Q4 唯一解除途径）")
    parser.add_argument("--daemon", action="store_true",
                        help="无窗口运行（pythonw 计划任务用）：stdout/stderr "
                             "重定向到 CP_DIR/loop_out.log")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if args.daemon:
        # pythonw 下 sys.stdout 为 None，print 会 AttributeError 带死循环；
        # 重定向到文件后 print/traceback 全部落盘
        state_mod.ensure_dirs()
        out = open(state_mod.CP_DIR / "loop_out.log", "a", encoding="utf-8",
                   buffering=1)
        sys.stdout = out
        sys.stderr = out

    if args.clear_halt:
        return _clear_halt()
    if args.loop is not None:
        return _loop(args.loop, publish=args.publish)
    if args.publish and args.dry_run:
        print("--publish 与 --dry-run 互斥", file=sys.stderr)
        return 2

    try:
        result, code = run_once(publish=args.publish, force=args.force)
    except Exception as e:  # noqa: BLE001 —— CLI 顶层，统一转 exit 码
        result = {"ok": False, "fatal": "%s: %s" % (type(e).__name__, e),
                  "errors": []}
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
