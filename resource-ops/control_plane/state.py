# -*- coding: utf-8 -*-
"""control_plane_state.json + control_plane.log（阶段5，Claude 裁定 Q7）。

- 状态文件：单文件原子覆写，O(1) 回答"现在是什么状态"。消费者：重启恢复判断
  （halted 检查）、WatchdogControlPlane 探测、人工排障。不是日志，不放流水细节。
- 流水日志：control_plane.log JSONL、512KB rotate（复用网关 resource_reload.log
  的轮转约定），记录 fetch/validate/publish/ack/rollback/halt/lease 事件流。
- 事件日志：Windows Application 事件源 API3100ControlPlane，事件号段 3201-3205
  （不复用网关 3105 语义）。写事件用 eventcreate 子进程 best-effort：权限不足或
  调用失败只记日志不抛错（告警文件始终落盘，watchdog 兜底读状态文件补报）。

路径默认 GATEWAY_DATA_DIR/control_plane/（与 live/last_good 同树，规避跨目录
ACL 差异——Claude 风险#3），env CP_STATE_DIR 可覆盖。
"""
import json
import os
import subprocess
import time
from pathlib import Path

GATEWAY_DATA_DIR = Path(os.environ.get(
    "GATEWAY_DATA_DIR", r"D:\项目\data\search_gateway"))
CP_DIR = Path(os.environ.get("CP_STATE_DIR") or (GATEWAY_DATA_DIR / "control_plane"))
STATE_FILE = CP_DIR / "control_plane_state.json"
LOG_FILE = CP_DIR / "control_plane.log"
ALERT_DIR = CP_DIR / "alerts"
LOG_MAX_BYTES = 512 * 1024

STATE_SCHEMA_VERSION = 1
# 状态文件必备字段（缺失时自动补默认值，向后兼容）
_STATE_DEFAULTS = {
    "schema_version": STATE_SCHEMA_VERSION,
    "updated_at": None,
    "last_run_at": None,
    "last_run_result": None,          # success/fetch_fail/validate_fail/error/noop
    "last_fetch_ok_at": None,         # 流水线活性信号（Q3/3203 探这个，不探换代）
    "last_publish_at": None,
    "last_publish_gen": None,
    "last_publish_sha256": None,
    "last_ack_result": None,          # ok/timeout/none
    "last_rollback_at": None,
    "rollback_times": [],             # 24h 滑窗时间戳列表（ISO 字符串）
    "consecutive_fetch_failures": 0,
    "consecutive_validate_failures": 0,
    "consecutive_ack_timeouts": 0,    # ACK 连续超时/回滚计数（Q4 第三类升级判据）
    "last_input_hash": None,          # validate 失败熔断的"原始输入哈希"
    "halted": False,
    "halted_reason": None,
    "halted_since": None,
    "halted_input_hash": None,
    "current_backoff_interval_s": 0,
    "loop_interval_s": None,
    "cooldown_until": None,           # ACK 回滚冷却（epoch 秒）
    "pid": None,
    "publish_attempt_count": 0,
    "publish_suppressed_count": 0,    # 冷却/最小间隔期间被抑制的发布次数
}

# 事件号段（Claude Q3）：3201 租约冲突 / 3202 心跳陈旧 / 3203 流水线活性停滞
# （当前阶段禁用告警，仅记录——空代是合法稳定基线，换代停滞≠故障）/
# 3204 回滚趋势异常（去抖 10 分钟）/ 3205 毒 candidate 熔断进入
EVENT_IDS = {"lease_conflict": 3201, "heartbeat_stale": 3202,
             "activity_stale": 3203, "rollback_trend": 3204, "halt": 3205}
EVENT_SOURCE = "API3100ControlPlane"


def ensure_dirs():
    CP_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_DIR.mkdir(parents=True, exist_ok=True)


def load_state():
    """读状态文件；不存在或损坏返回默认结构（损坏时保留坏文件为 .corrupt）。"""
    try:
        raw = STATE_FILE.read_text(encoding="utf-8")
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError("state 非对象")
    except FileNotFoundError:
        return dict(_STATE_DEFAULTS)
    except Exception:  # noqa: BLE001 —— 损坏不阻断，备份后用默认
        try:
            os.replace(STATE_FILE, STATE_FILE.with_suffix(".json.corrupt"))
        except OSError:
            pass
        return dict(_STATE_DEFAULTS)
    merged = dict(_STATE_DEFAULTS)
    merged.update({k: v for k, v in doc.items() if k in _STATE_DEFAULTS})
    return merged


def update_state(**fields):
    """读-改-写状态文件（原子覆写 tmp+fsync+os.replace）。返回更新后的完整状态。"""
    ensure_dirs()
    st = load_state()
    for k, v in fields.items():
        if k not in _STATE_DEFAULTS:
            raise KeyError("未知状态字段: %s" % k)
        st[k] = v
    st["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = STATE_FILE.with_suffix(".json.tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)
    return st


def log_event(event, **detail):
    """追加一条 JSONL 流水日志；超 512KB 轮转（保留一份 .1）。"""
    ensure_dirs()
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event}
    rec.update(detail)
    line = json.dumps(rec, ensure_ascii=False)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE.with_suffix(".log.1"))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def emit_event(kind, detail_text, alert_payload=None):
    """告警三件套：alert 文件（始终）+ Windows 事件日志（best-effort）+ 流水日志。

    kind ∈ EVENT_IDS。事件号段与网关 3105 严格分离（Claude Q3 裁定）。
    """
    eid = EVENT_IDS[kind]
    ensure_dirs()
    if alert_payload is None:
        alert_payload = {}
    alert_payload.update({"kind": kind, "event_id": eid,
                          "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        name = ALERT_DIR / ("%s_%s.json" % (kind, time.strftime("%Y%m%dT%H%M%S")))
        tmp = name.with_suffix(".json.tmp.%d" % os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(alert_payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, name)
    except OSError:
        pass
    log_event("alert", kind=kind, event_id=eid, detail=detail_text)
    try:
        subprocess.run(
            ["eventcreate", "/ID", str(eid), "/T", "ERROR", "/L", "APPLICATION",
             "/SO", EVENT_SOURCE, "/D", detail_text[:512]],
            capture_output=True, timeout=10, check=False)
    except Exception:  # noqa: BLE001 —— best-effort，永不因告警失败带死流水线
        pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def prune_rollbacks(st, window_s=86400):
    """把 rollback_times 修剪到 24h 滑窗内，返回修剪后的列表。"""
    now = time.time()
    keep = []
    for ts in st.get("rollback_times") or []:
        try:
            t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            continue
        if now - t <= window_s:
            keep.append(ts)
    return keep
