# -*- coding: utf-8 -*-
"""M1 SQLite 运行时真源（WAL 模式）
存：实例状态 / 额度 / cooldown / 事件日志
飞书是配置真源，这里只存运行时状态（错误切换后 SQLite 为准）。
"""
import sqlite3
import os
import threading
import json
import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS instances (
    instance_id    TEXT PRIMARY KEY,
    capability_id  TEXT NOT NULL,
    routing_group  TEXT NOT NULL,
    canonical_model TEXT NOT NULL,
    mode           TEXT NOT NULL DEFAULT 'mock',        -- mock | openai-compatible
    upstream_base  TEXT,                                 -- openai-compatible 模式的上游 base_url
    credential_id  TEXT,                                 -- 凭证 ID（本地 credentials.json 键名）
    status         TEXT NOT NULL DEFAULT '可用',          -- 可用/额度耗尽/冷却中/失效/待验证
    quota_remaining REAL NOT NULL DEFAULT 0,
    quota_unit     TEXT NOT NULL DEFAULT 'token',
    safety_margin  REAL NOT NULL DEFAULT 0,
    cooldown_until TEXT,                                 -- ISO 时间；未过期为冷却中
    route_priority INTEGER NOT NULL DEFAULT 99,
    config_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    request_id TEXT,
    instance_id TEXT,
    model TEXT,
    kind TEXT NOT NULL,      -- REQUEST / ERROR / FAILOVER / EXHAUSTED / COOLDOWN / CRED_INVALID / CONFIG_INVALID / OK
    detail TEXT
);
"""


class Ledger:
    def __init__(self, db_path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def seed(self, instances):
        """首次启动用配置播种；已存在则只补缺失，不覆盖运行态。"""
        with self._lock, self._db:
            for i in instances:
                self._db.execute(
                    """INSERT OR IGNORE INTO instances
                       (instance_id, capability_id, routing_group, canonical_model,
                        mode, upstream_base, credential_id, status,
                        quota_remaining, quota_unit, safety_margin, route_priority, config_version)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (i["instance_id"], i.get("capability_id"), i.get("routing_group"),
                     i.get("canonical_model"), i.get("mode", "mock"), i.get("upstream_base"),
                     i.get("credential_id"), i.get("status", "可用"),
                     i.get("quota_remaining", 0), i.get("quota_unit", "token"),
                     i.get("safety_margin", 0), i.get("route_priority", 99),
                     i.get("config_version", 1)))
            self._db.commit()

    def list_instances(self):
        with self._lock, self._db:
            rows = self._db.execute("SELECT * FROM instances").fetchall()
            cols = [d[0] for d in self._db.execute("SELECT * FROM instances").description]
            return [dict(zip(cols, r)) for r in rows]

    # M2：数据桥真源同步——配置字段 upsert，运行态字段（status/quota/cooldown）保留
    CONFIG_FIELDS = ["routing_group", "canonical_model", "mode", "upstream_base",
                     "credential_id", "quota_unit", "route_priority", "config_version"]

    def sync_instances(self, new_configs):
        """按数据桥产物同步实例配置。

        - 已存在实例：只 upsert 配置字段，不覆盖运行态（status/quota_remaining/cooldown_until）。
        - 新实例：INSERT（初始 status 来自数据桥映射，quota_remaining 由调用方给出初始值）。
        - 数据桥消失的实例：标记 status=失效（保留行与事件历史）。
        """
        with self._lock, self._db:
            existing = {r[0] for r in self._db.execute("SELECT instance_id FROM instances").fetchall()}
            for iid, c in new_configs.items():
                if iid in existing:
                    sets = ", ".join(f"{f}=?" for f in self.CONFIG_FIELDS)
                    self._db.execute(
                        f"UPDATE instances SET {sets} WHERE instance_id=?",
                        (*[c.get(f) for f in self.CONFIG_FIELDS], iid))
                else:
                    self._db.execute(
                        """INSERT OR IGNORE INTO instances
                           (instance_id, capability_id, routing_group, canonical_model,
                            mode, upstream_base, credential_id, status,
                            quota_remaining, quota_unit, safety_margin, route_priority, config_version)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (iid, c.get("capability_id"), c.get("routing_group"),
                         c.get("canonical_model"), c.get("mode", "openai-compatible"),
                         c.get("upstream_base"), c.get("credential_id"),
                         c.get("status", "可用"), c.get("quota_remaining", 0),
                         c.get("quota_unit", "token"), c.get("safety_margin", 0),
                         c.get("route_priority", 99), c.get("config_version", 1)))
            gone = existing - set(new_configs)
            for iid in gone:
                self._db.execute(
                    "UPDATE instances SET status='失效' WHERE instance_id=? AND status!='失效'", (iid,))
            self._db.commit()

    def get_instance(self, instance_id):
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM instances WHERE instance_id=?", (instance_id,)).fetchone()
            if not row:
                return None
            cols = [d[0] for d in self._db.execute("SELECT * FROM instances").description]
            return dict(zip(cols, row))

    def set_status(self, instance_id, status):
        with self._lock, self._db:
            self._db.execute("UPDATE instances SET status=? WHERE instance_id=?", (status, instance_id))
            self._db.commit()

    def set_quota(self, instance_id, remaining):
        with self._lock, self._db:
            self._db.execute("UPDATE instances SET quota_remaining=? WHERE instance_id=?", (remaining, instance_id))
            self._db.commit()

    # ---- M2 并发：per-instance 原子预留 ----

    def reserve(self, instance_id):
        """原子预留实例；仅当 status='可用' 且未冷却时才成功（并发下只有一个请求拿到）。"""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE instances SET status='预留' WHERE instance_id=? AND status='可用' "
                "AND (cooldown_until IS NULL OR cooldown_until<=?)", (instance_id, now)).rowcount
            self._db.commit()
        return cur == 1

    def release(self, instance_id):
        """释放预留回「可用」（仅当当前仍为预留态，避免覆盖运行态）。"""
        with self._lock, self._db:
            self._db.execute("UPDATE instances SET status='可用' WHERE instance_id=? AND status='预留'",
                             (instance_id,))
            self._db.commit()

    def clear_stale_reserved(self):
        """启动清理：崩溃残留的『预留』态全部释放回『可用』。"""
        with self._lock, self._db:
            self._db.execute("UPDATE instances SET status='可用' WHERE status='预留'")
            self._db.commit()

    def debit_atomic(self, instance_id, cost):
        """原子扣减额度：quota_remaining 在 SQL 层自减，避免并发双扣；扣到<=0 置额度耗尽。"""
        if cost <= 0:
            return
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE instances SET quota_remaining = quota_remaining - ? WHERE instance_id=?",
                (cost, instance_id)).rowcount
            if cur:
                row = self._db.execute(
                    "SELECT quota_remaining FROM instances WHERE instance_id=?", (instance_id,)).fetchone()
                if row and row[0] <= 0:
                    self._db.execute(
                        "UPDATE instances SET status='额度耗尽' WHERE instance_id=? AND status!='额度耗尽'",
                        (instance_id,))
            self._db.commit()

    def set_cooldown(self, instance_id, until_iso):
        with self._lock, self._db:
            self._db.execute("UPDATE instances SET cooldown_until=? WHERE instance_id=?", (until_iso, instance_id))
            self._db.commit()

    def log(self, request_id, instance_id, model, kind, detail=""):
        import datetime
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events (ts, request_id, instance_id, model, kind, detail) VALUES (?,?,?,?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),
                 request_id, instance_id, model, kind, detail))
            self._db.commit()

    def recent_events(self, limit=20):
        with self._lock, self._db:
            rows = self._db.execute(
                "SELECT ts, instance_id, model, kind, detail FROM events ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
            return [{"ts": r[0], "instance_id": r[1], "model": r[2], "kind": r[3], "detail": r[4]} for r in rows]
