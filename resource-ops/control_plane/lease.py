# -*- coding: utf-8 -*-
"""单实例文件租约（阶段5，Claude 裁定 Q2）。

- 锁文件 lease.lock：O_CREAT|O_EXCL 独占创建（真正的获取原子性），内容
  {pid, hostname, started_at, heartbeat_at, lease_id}——可被 watchdog/人直接
  stat/读取（与命名互斥体的核心差异：可观测）。
- 心跳：独立守护线程 ≤30s 刷新 heartbeat_at（与 loop 单轮耗时解耦，否则
  "卡住"与"正常运行中"在心跳信号上无法区分）。
- 陈旧判定：3-5 倍心跳间隔（默认 150s），且必须大于单轮最坏耗时。
- 接管：锁存在但心跳陈旧 → 判定持有者已死，原子替换锁文件（tmp+os.replace）
  并在流水日志记录前 pid + 观测到的最后心跳年龄。
- 失去租约（运行中发现 lease_id 易主）→ 触发 stop 事件，主循环退出，退出码
  3111；启动时发现租约被占用 → 退出码 3110。绝不空转（Claude Q2 裁定）。

定位（写进设计的明确声明）：双写的最后一道防线是 publish.py 的原子替换 +
canonical_sha256 幂等，租约只是效率/清晰度层，不是数据正确性依赖。
"""
import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path

from .state import CP_DIR, ensure_dirs, log_event

LOCK_FILE = CP_DIR / "lease.lock"
HEARTBEAT_INTERVAL_S = 30
STALE_THRESHOLD_S = 150          # 5 × 心跳间隔
EXIT_LEASE_OCCUPIED = 3110       # 启动时租约被占用
EXIT_LEASE_LOST = 3111           # 运行中租约被他方接管


class LeaseOccupied(Exception):
    def __init__(self, holder):
        self.holder = holder
        super().__init__("lease occupied: %s" % holder)


class Lease:
    """一个租约会话。用法：
        with Lease() as lease: ...  # 或手动 acquire()/release()
    """

    def __init__(self, lock_path=None, heartbeat_s=HEARTBEAT_INTERVAL_S,
                 stale_s=STALE_THRESHOLD_S):
        self.lock_path = Path(lock_path) if lock_path else LOCK_FILE
        self.heartbeat_s = heartbeat_s
        self.stale_s = stale_s
        self.lease_id = None
        self.info = None
        self._stop = threading.Event()
        self._hb_thread = None

    # ---------- 内部 ----------

    def _read(self):
        try:
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return None

    def _is_stale(self, info, now=None):
        if not info:
            return True
        try:
            hb = time.mktime(time.strptime(info["heartbeat_at"], "%Y-%m-%dT%H:%M:%S"))
        except (KeyError, ValueError, TypeError):
            return True
        now = now or time.time()
        return (now - hb) > self.stale_s

    def _atomic_write_lock(self, doc):
        ensure_dirs()
        tmp = self.lock_path.with_suffix(".lock.tmp.%d" % os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.lock_path)

    def _make_info(self):
        return {"pid": os.getpid(), "hostname": socket.gethostname(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "heartbeat_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "lease_id": self.lease_id}

    def _heartbeat_loop(self):
        while not self._stop.wait(self.heartbeat_s):
            try:
                cur = self._read()
                if not cur or cur.get("lease_id") != self.lease_id:
                    log_event("lease_lost", lease_id=self.lease_id,
                              holder=(cur or {}).get("pid"))
                    self._stop.set()
                    return
                self._atomic_write_lock(self._make_info())
            except Exception as e:  # noqa: BLE001 —— 心跳失败不静默丢租约
                log_event("heartbeat_error", err="%s: %s" % (type(e).__name__, e))
                self._stop.set()
                return

    # ---------- 对外 ----------

    def acquire(self, takeover=True):
        """获取租约。被占用且未陈旧 → LeaseOccupied；陈旧 → 接管。"""
        ensure_dirs()
        self.lease_id = uuid.uuid4().hex
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._make_info(), f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                self.info = self._make_info()
                log_event("lease_acquire", lease_id=self.lease_id,
                          pid=os.getpid())
                return self
            except FileExistsError:
                cur = self._read()
                if cur and not self._is_stale(cur) and not takeover:
                    raise LeaseOccupied(cur)
                if cur and not self._is_stale(cur):
                    raise LeaseOccupied(cur)
                age = None
                if cur and cur.get("heartbeat_at"):
                    try:
                        hb = time.mktime(time.strptime(cur["heartbeat_at"], "%Y-%m-%dT%H:%M:%S"))
                        age = round(time.time() - hb)
                    except (ValueError, TypeError):
                        age = None
                log_event("lease_takeover", stale=True, prev_pid=(cur or {}).get("pid"),
                          last_heartbeat_age_s=age)
                try:
                    self._atomic_write_lock(self._make_info())
                except OSError:
                    continue  # 与其他接管者竞争，重试
                self.info = self._make_info()
                log_event("lease_acquire_after_takeover", lease_id=self.lease_id)
                return self

    def start_heartbeat(self):
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

    def lost(self):
        """运行中是否已判定失去租约（心跳线程发现易主/写失败）。"""
        return self._stop.is_set()

    def release(self):
        self._stop.set()
        if self._hb_thread:
            self._hb_thread.join(timeout=self.heartbeat_s + 2)
        try:
            cur = self._read()
            if cur and cur.get("lease_id") == self.lease_id:
                self.lock_path.unlink()
                log_event("lease_release", lease_id=self.lease_id)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def __enter__(self):
        self.acquire()
        self.start_heartbeat()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
