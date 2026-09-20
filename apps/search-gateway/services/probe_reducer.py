# -*- coding: utf-8 -*-
"""probe_reducer：探针事实注册表的唯一写入者（RFC：测试-编排两角色架构 第一期）

设计要点（GPT Extended 评审 2026-09-19，全文 D:\\项目\\logs\\gpt_model_probe_reply_20260919.md）：
- 探针执行器（capability_verify / daily_speed_test / channel probes）只写不可变 run 文件
  到 probe_runs/<YYYY-MM-DD>/<run_id>.json，绝不直接写真源。
- 本 reducer 是 model_probes.json / model_perf.json 的唯一 writer：按 namespace（kind）
  合并，kind 内冲突按 observed_at → probe_version → event_id 定新旧。
- 提交流程：跨进程文件锁 → 读 snapshot+revision → 消费未 applied 的 run → merge →
  schema 校验 → tmp+flush+fsync → os.replace → revision+=1 → 记录 applied run_id。
- 兼容视图物化：model_capabilities.json ← capabilities；model_pricing.json billing
  class ← billing（**只写 class 实测值，绝不碰 authorized/paid 授权语义**——授权是
  人的政策，不是实测事实）。

铁律：Probe 只产事实；Reducer 独占写入；Policy 只由人定义；Orchestrator 只代入。
"""
import json
import os
import tempfile

import channels

DATA_DIR = channels.DATA_DIR
RUNS_DIR = os.path.join(DATA_DIR, "probe_runs")
PROBES_JSON = os.path.join(DATA_DIR, "model_probes.json")
PERF_JSON = os.path.join(DATA_DIR, "model_perf.json")

SCHEMA_VERSION = 1
# namespace → 该 kind 的 run 只能触碰真源的哪些字段
KIND_FIELDS = {
    "catalog": {"catalog"},
    "access": {"access"},
    "capabilities": {"capabilities"},
    "billing": {"billing"},
    "perf": None,  # perf 不进 probes，走 model_perf 聚合
}
VALID_ACCESS = {"available", "paid_required", "forbidden", "auth_error", "unknown"}
VALID_CATALOG = {"listed", "retired", "missing", "unknown"}


def _lock_path():
    return os.path.join(DATA_DIR, "probe_reducer.lock")


class _FileLock:
    """Windows 可用的跨进程排他锁（msvcrt.locking）。"""

    def __enter__(self):
        self._fh = open(_lock_path(), "a+b")
        import msvcrt
        msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
        return self

    def __exit__(self, *exc):
        import msvcrt
        try:
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:  # noqa: BLE001
            pass
        self._fh.close()


def _atomic_write_json(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:  # noqa: BLE001
            pass
        raise


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def emit_run(channel, model, kind, payload, writer="manual",
             probe_version="1.0", observed_at=None, run_id=None):
    """执行器侧唯一入口：把一条探测结果落成不可变 run 文件。返回 run_id。

    payload 结构按 kind：
      catalog       {state, http_status?}
      access        {state, plan?, http_status?, confidence?}
      capabilities  {chat?, vision?, tools?, stream?, json_schema?}  值可为 None=不测
      billing       {class_, billing_model?, meter_unit?, free_allowance?,
                     cost_sample?{probe_profile, meter_value, input_tokens?, output_tokens?}}
      perf          {tok_s?, ttft_ms?, total_ms?, completion_tokens?, ok, error?}
    """
    import time as _t
    import uuid as _uuid
    observed_at = observed_at or _t.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    run_id = run_id or _uuid.uuid4().hex[:16]
    day = observed_at[:10]
    run = {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"{run_id}-{kind}",
        "run_id": run_id,
        "writer": writer,
        "probe_version": probe_version,
        "channel": channel,
        "model": model,
        "kind": kind,
        "observed_at": observed_at,
        "payload": payload,
    }
    out = os.path.join(RUNS_DIR, day, f"{run_id}-{kind}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    return run_id


def _model_entry(probes, channel, model):
    return (probes.setdefault("channels", {})
            .setdefault(channel, {})
            .setdefault("models", {})
            .setdefault(model, {}))


def _merge_run(probes, perf, run):
    """按 namespace 合并一条 run。返回 changed:bool。"""
    kind = run.get("kind")
    ch, md = run.get("channel"), run.get("model")
    if not ch or not md or kind not in KIND_FIELDS:
        return False
    obs = run.get("observed_at") or ""
    pv = run.get("probe_version") or ""
    payload = run.get("payload") or {}

    if kind == "perf":
        # perf 只进聚合文件的 samples 缓冲（reducer 顺带维护 EWMA/p50）
        entry = (perf.setdefault("channels", {}).setdefault(ch, {})
                 .setdefault("models", {}).setdefault(md, {}))
        samples = entry.setdefault("samples", [])
        samples.append({
            "observed_at": obs,
            "tok_s": payload.get("tok_s"),
            "ttft_ms": payload.get("ttft_ms"),
            "total_ms": payload.get("total_ms"),
            "completion_tokens": payload.get("completion_tokens"),
            "ok": bool(payload.get("ok")),
        })
        # 只保留最近 48 条原始样本
        del samples[:-48]
        return True

    fields = KIND_FIELDS[kind]
    entry = _model_entry(probes, ch, md)
    section = entry.setdefault(kind, {})
    # kind 内旧值比较：observed_at 字典序即时间序（ISO8601 同格式）
    cur_obs = section.get("observed_at") or ""
    if cur_obs > obs:
        return False
    v = payload  # payload 即该 kind 的值对象（emit_run 侧已按 kind 组装）
    if v is None:
        return False
    if kind == "catalog":
        if v.get("state") in VALID_CATALOG:
            section.clear()
            section.update({"state": v["state"],
                            "http_status": v.get("http_status"),
                            "observed_at": obs, "probe_version": pv})
            return True
    elif kind == "access":
        if v.get("state") in VALID_ACCESS:
            section.clear()
            section.update({"state": v["state"], "plan": v.get("plan"),
                            "http_status": v.get("http_status"),
                            "confidence": v.get("confidence", 1.0),
                            "observed_at": obs, "probe_version": pv})
            return True
    elif kind == "capabilities":
        caps = section.setdefault("values", {})
        for cap in ("chat", "vision", "tools", "stream", "json_schema"):
            if v.get(cap) is not None:
                caps[cap] = bool(v[cap])
        section["observed_at"] = obs
        section["probe_version"] = pv
        return True
    elif kind == "billing":
        b = {}
        if v.get("class_") is not None:
            b["class"] = v["class_"]
        for key in ("billing_model", "meter_unit", "free_allowance"):
            if v.get(key) is not None:
                b[key] = v[key]
        cs = v.get("cost_sample")
        if cs:
            b["cost_sample"] = cs
        b["observed_at"] = obs
        b["probe_version"] = pv
        section.clear()
        section.update(b)
        return True
    return False


def _recompute_perf_aggregates(perf):
    """由 samples 重算 p50/EWMA/success_rate/confidence。"""
    for ch, ch_entry in (perf.get("channels") or {}).items():
        for md, entry in (ch_entry.get("models") or {}).items():
            samples = entry.get("samples") or []
            oks = [s for s in samples if s.get("ok")]
            recent = [s for s in oks if s.get("tok_s")]
            tok = sorted(s["tok_s"] for s in recent)
            ttft = sorted(s["ttft_ms"] for s in oks if s.get("ttft_ms"))
            p50 = (tok[len(tok)//2] if tok else None)
            tp50 = (ttft[len(ttft)//2] if ttft else None)
            ewma = None
            for s in recent:
                ewma = s["tok_s"] if ewma is None else 0.3*s["tok_s"] + 0.7*ewma
            entry["tok_s_p50"] = p50
            entry["tok_s_ewma"] = round(ewma, 2) if ewma else None
            entry["ttft_ms_p50"] = tp50
            entry["success_rate"] = (round(len(oks)/len(samples), 3) if samples else None)
            entry["samples_n"] = len(samples)
            entry["confidence"] = min(1.0, len(recent)/3.0)
            entry["last_sample_at"] = (samples[-1]["observed_at"] if samples else None)


def reduce_all(max_runs=2000):
    """消费所有未 applied 的 run 文件 → 更新 model_probes.json + model_perf.json。
    返回 {applied:int, revision:int}。"""
    applied_ids = _load_json(os.path.join(DATA_DIR, "probe_runs_applied.json"), {})
    probes = _load_json(PROBES_JSON, {
        "schema_version": SCHEMA_VERSION, "revision": 0,
        "channels": {},
    })
    perf = _load_json(PERF_JSON, {
        "schema_version": SCHEMA_VERSION, "channels": {},
    })
    pending = []
    if os.path.isdir(RUNS_DIR):
        for day in sorted(os.listdir(RUNS_DIR)):
            ddir = os.path.join(RUNS_DIR, day)
            if not os.path.isdir(ddir):
                continue
            for fn in sorted(os.listdir(ddir)):
                if not fn.endswith(".json"):
                    continue
                rid = fn.rsplit("-", 1)[0] if "-" in fn else fn[:-5]
                ev = fn[:-5]
                if applied_ids.get(ev):
                    continue
                run = _load_json(os.path.join(ddir, fn), None)
                if run:
                    pending.append((ev, run))
    changed_p = changed_f = 0
    for ev, run in pending[:max_runs]:
        r1 = _merge_run(probes, perf, run)
        if r1:
            changed_f += 1
        changed_p += r1
        applied_ids[ev] = {"applied_at": run.get("observed_at")}
    if pending:
        _recompute_perf_aggregates(perf)
        probes["revision"] = int(probes.get("revision") or 0) + 1
        probes["generated_at"] = pending[-1][1].get("observed_at")
        _atomic_write_json(PROBES_JSON, probes)
        _atomic_write_json(PERF_JSON, perf)
        _atomic_write_json(os.path.join(DATA_DIR, "probe_runs_applied.json"), applied_ids)
    return {"applied": len(pending[:max_runs]), "revision": probes.get("revision")}


def materialize_compat_views():
    """从 model_probes.json 物化兼容视图。
    - capabilities → model_capabilities.json（只写实测模型的布尔值）
    - billing class → model_pricing.json（只补全缺失 class；绝不改 authorized）
    """
    probes = _load_json(PROBES_JSON, None)
    if not probes:
        return
    # --- capabilities 视图 ---
    cap_path = os.path.join(DATA_DIR, "model_capabilities.json")
    cap = _load_json(cap_path, {"version": 1, "channels": {}})
    for ch, ch_entry in (probes.get("channels") or {}).items():
        for md, entry in (ch_entry.get("models") or {}).items():
            caps = (entry.get("capabilities") or {}).get("values") or {}
            if not caps:
                continue
            chan = cap.setdefault("channels", {}).setdefault(ch, {})
            m = chan.setdefault("models", {}).setdefault(md, {})
            for k in ("chat", "vision", "tools", "stream", "json_schema"):
                if k in caps:
                    m[k] = caps[k]
    _atomic_write_json(cap_path, cap)
    # --- pricing 视图：只补缺（实测 free 填入，无实测不动） ---
    probes_billing = []
    for ch, ch_entry in (probes.get("channels") or {}).items():
        for md, entry in (ch_entry.get("models") or {}).items():
            b = entry.get("billing") or {}
            if b.get("class"):
                probes_billing.append((ch, md, b["class"], b.get("observed_at") or ""))
    if probes_billing:
        import pricing
        pr_path = os.path.join(DATA_DIR, "model_pricing.json")
        pr = _load_json(pr_path, {})
        chs = pr.setdefault("channels", {})
        for ch, md, cls, obs in probes_billing:
            if cls != "free":
                continue  # paid/unknown 不自动写——付费语义归人
            c = chs.setdefault(ch, {})
            models = c.setdefault("models", {})
            if md in models:
                continue  # 已有条目（可能含人的授权）绝不覆盖
            models[md] = {"class": "free", "verified_at": obs[:10],
                          "evidence": "probe_reducer materialize (access=available + billing.class=free)"}
        _atomic_write_json(pr_path, pr)
        try:
            pricing.load_pricing()  # 刷新 pricing 模块缓存（如有 mtime 缓存则重读）
        except Exception:  # noqa: BLE001
            pass


def run_full():
    """reduce + 物化，一条龙。"""
    r = reduce_all()
    materialize_compat_views()
    return r


if __name__ == "__main__":
    import sys
    print(json.dumps(run_full(), ensure_ascii=False))
    sys.exit(0)
