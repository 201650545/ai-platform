# -*- coding: utf-8 -*-
"""M1 SQLite 运行时真源（WAL 模式）
存：实例状态 / 额度 / cooldown / 事件日志
飞书是配置真源，这里只存运行时状态（错误切换后 SQLite 为准）。
"""
import sqlite3
import os
import threading
import json

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
