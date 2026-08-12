#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1 最小闭环调度器
Python 单进程 + SQLite(WAL) + localhost base_url 代理。

路由：过滤（canonical_model 匹配 / 状态可用 / 未冷却 / 额度>安全余量）
      → 排序（route_priority 升序，剩余额度降序）→ 调用 adapter。

错误分类（写回 SQLite，可切换错误自动 failover 到同能力下一实例）：
  quota_exhausted            → EXHAUSTED      （状态=额度耗尽，可切换）
  HTTP 429（非 quota）        → COOLDOWN       （状态=冷却中 +60s，可切换）
  401/403                    → CRED_INVALID   （状态=失效，立即失败不切换）
  model_not_found / 404      → CONFIG_INVALID （状态=失效，立即失败不切换）
  HTTP 5xx                   → RETRYABLE_5XX  （冷却中 +30s，可切换）
  200 里包错误（choices 缺失 / finish_reason=error）→ COOLDOWN（不重放）

流式安全：M1 整读上游再转发，切换决策发生在转发前；已透传即不再重放。

Secret 边界：凭证只从本地 credentials.json（受信平面）读，SQLite/日志/响应
均不落 key；日志 detail 白名单化（instance/model/kind/status，无请求体）。

用法：
  python scheduler.py [--port 8789] [--db scheduler.sqlite3] [--config config.json]
"""
import argparse
import datetime
import json
import os
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Ledger

QUOTA_PATTERNS = re.compile(
    r"quota|insufficient.{0,20}balance|balance.{0,20}insufficient|"
    r"余额不足|额度|exceeded.*(?:limit|balance)", re.I)


def now_iso(offset_s=0):
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=offset_s)
    return dt.isoformat(timespec="seconds")


def classify_error(status, text):
    """HTTP status + body → 错误分类。200 里包错误也识别。"""
    if status == 200:
        try:
            obj = json.loads(text)
        except Exception:
            return "OK"
        if isinstance(obj, dict):
            if obj.get("error"):
                return "COOLDOWN"
            choices = obj.get("choices")
            if not choices:
                return "COOLDOWN"
            for c in choices:
                if isinstance(c, dict) and c.get("finish_reason") == "error":
                    return "COOLDOWN"
        return "OK"
    lower = text.lower()
    if status in (401, 403):
        return "CRED_INVALID"
    if status == 404 or "does not exist" in lower or "model_not_found" in lower:
        return "CONFIG_INVALID"
    if status == 429:
        return "EXHAUSTED" if QUOTA_PATTERNS.search(lower) else "COOLDOWN"
    if 500 <= status <= 599:
        return "RETRYABLE_5XX"
    if QUOTA_PATTERNS.search(lower):
        return "EXHAUSTED"
    return "OTHER"


# 可切换 vs 立即失败
RETRYABLE = {"EXHAUSTED", "COOLDOWN", "RETRYABLE_5XX"}
FATAL = {"CRED_INVALID", "CONFIG_INVALID"}


def _err(status, message, code=None):
    e = {"error": {"message": message, "type": "invalid_request_error"}}
    if code:
        e["error"]["code"] = code
    return status, json.dumps(e, ensure_ascii=False)


class MockAdapter:
    """可编程 mock：按实例 mock_fail 返回成功或指定错误，用于验收切换逻辑。"""

    def call(self, inst, payload):
        fail = inst.get("mock_fail", "")
        model = payload.get("model", inst.get("canonical_model"))
        if fail == "quota_exhausted":
            return 429, json.dumps({"error": {"message": "Rate limit reached, insufficient balance",
                                              "type": "insufficient_quota", "code": "insufficient_quota"}})
        if fail == "rate_limit":
            return 429, json.dumps({"error": {"message": "Rate limit reached, retry later",
                                              "type": "rate_limit", "code": "rate_limit"}})
        if fail == "auth_invalid":
            return 401, json.dumps({"error": {"message": "Invalid API key", "type": "invalid_request_error"}})
        if fail == "model_not_found":
            return 404, json.dumps({"error": {"message": f"The model `{model}` does not exist",
                                              "type": "invalid_request_error", "code": "model_not_found"}})
        if fail == "internal_error":
            return 500, json.dumps({"error": {"message": "upstream internal error", "type": "server_error"}})
        if fail == "error_in_200":
            return 200, json.dumps({"error": {"message": "hidden upstream failure", "type": "server_error"}})
        # 成功（可流式）
        body = {
            "id": f"chatcmpl-mock-{inst['instance_id']}",
            "object": "chat.completion",
            "created": 1780000000,
            "model": model,
            "x_instance_id": inst["instance_id"],
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": f"mock 响应来自实例 {inst['instance_id']}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        if payload.get("stream"):
            chunks = [
                {"id": body["id"], "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {"id": body["id"], "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {"content": f"来自实例 {inst['instance_id']}"}, "finish_reason": None}]},
                {"id": body["id"], "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            sse = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks)
            return 200, sse + "data: [DONE]\n\n"
        return 200, json.dumps(body, ensure_ascii=False)


class OpenAICompatibleAdapter:
    """真实转发到上游（M3 启用）。密钥从 credentials.json 注入，绝不落日志。"""

    def _request(self, inst, payload, credentials):
        base = (inst.get("upstream_base") or "").rstrip("/")
        if not base:
            return None, (500, json.dumps({"error": {"message": "upstream_base 未配置", "type": "config_error"}}))
        cred = credentials.get(inst.get("credential_id")) or {}
        key = cred.get("key") or ""
        url = base + "/chat/completions"
        req = Request(url, method="POST",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        return req, None

    def call(self, inst, payload, credentials):
        req, err = self._request(inst, payload, credentials)
        if err:
            return err
        try:
            resp = urlopen(req, timeout=120)
            return resp.status, resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except URLError as e:
            return 502, json.dumps({"error": {"message": f"upstream unreachable: {e.reason}", "type": "server_error"}})

    def call_stream(self, inst, payload, credentials, on_chunk):
        """真实流式逐块转发：上游 SSE 每读到一块立即 on_chunk 写客户端，不整读缓冲。

        首个字节前失败（HTTPError/网络）返回 (status, err_text)；
        200 后逐块透传，返回 (200, "")——已透传即不重放（流式安全）。
        """
        req, err = self._request(inst, payload, credentials)
        if err:
            return err
        try:
            resp = urlopen(req, timeout=120)
        except HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except URLError as e:
            return 502, json.dumps({"error": {"message": f"upstream unreachable: {e.reason}", "type": "server_error"}})
        # SSE 逐行读转发：read(4096) 会阻塞等满或 EOF（把流式压成整段）；
        # readline 每行到达即转发，逐事件透传，客户端可边收边渲染。
        while True:
            line = resp.readline()
            if not line:
                break
            on_chunk(line)
        return 200, ""


class Scheduler:
    def __init__(self, config_path, db_path=None, port=None):
        self.config_path = config_path
        self.cfg = self._load_config()
        if db_path:
            self.cfg["db_path"] = db_path
        if port:
            self.cfg["listen"]["port"] = port
        self.ledger = Ledger(self.cfg.get("db_path", "scheduler.sqlite3"))
        self.ledger.clear_stale_reserved()  # M2：清理崩溃残留的『预留』态
        self.ledger.seed(self.cfg["instances"])
        self.credentials = self._load_credentials()
        self._mock = MockAdapter()
        self._real = OpenAICompatibleAdapter()
        self._request_lock = threading.Lock()

    def _load_config(self):
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_credentials(self):
        p = self.cfg.get("credentials_path", "credentials.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _inst_config(self):
        """每次调用重读 config，mock 行为可改文件即时生效。"""
        return {i["instance_id"]: i for i in self._load_config()["instances"]}

    def _merge(self, row):
        """SQLite 运行态行 + config 配置（mock 行为/上游/凭证）"""
        merged = dict(row)
        c = self._inst_config().get(row["instance_id"], {})
        for k in ("mode", "mock_fail", "upstream_base", "credential_id"):
            if k in c:
                merged[k] = c[k]
        return merged

    def select_candidates(self, model):
        now = now_iso()
        cands = []
        for row in self.ledger.list_instances():
            if row["canonical_model"] != model:
                continue
            if row["status"] != "可用":
                continue
            if row.get("cooldown_until") and row["cooldown_until"] > now:
                continue
            if (row.get("quota_remaining") or 0) <= (row.get("safety_margin") or 0):
                continue
            cands.append(row)
        cands.sort(key=lambda r: (r.get("route_priority", 99), -(r.get("quota_remaining") or 0)))
        return cands

    @staticmethod
    def _extract_cost(resp_text):
        """从 200 响应提取 usage.total_tokens；无 usage / 解析失败返回 0。"""
        try:
            obj = json.loads(resp_text)
            if isinstance(obj, dict) and obj.get("usage"):
                return obj["usage"].get("total_tokens", 0) or 0
        except Exception:
            pass
        return 0

    def debit(self, inst, resp_text):
        """原子扣减额度（M2 并发安全：SQL 层自减，防双扣）；扣到<=0 自动置额度耗尽。"""
        self.ledger.debit_atomic(inst["instance_id"], self._extract_cost(resp_text))

    def apply_error(self, inst, kind, request_id, model, status):
        iid = inst["instance_id"]
        if kind == "EXHAUSTED":
            self.ledger.set_status(iid, "额度耗尽")
            self.ledger.log(request_id, iid, model, "EXHAUSTED", f"http {status}")
        elif kind == "COOLDOWN":
            self.ledger.set_status(iid, "冷却中")
            self.ledger.set_cooldown(iid, now_iso(60))
            self.ledger.log(request_id, iid, model, "COOLDOWN", f"http {status}")
        elif kind == "RETRYABLE_5XX":
            self.ledger.set_status(iid, "冷却中")
            self.ledger.set_cooldown(iid, now_iso(30))
            self.ledger.log(request_id, iid, model, "COOLDOWN", f"5xx http {status}")
        elif kind == "CRED_INVALID":
            self.ledger.set_status(iid, "失效")
            self.ledger.log(request_id, iid, model, "CRED_INVALID", f"http {status}")
        elif kind == "CONFIG_INVALID":
            self.ledger.set_status(iid, "失效")
            self.ledger.log(request_id, iid, model, "CONFIG_INVALID", f"http {status}")

    def handle_chat(self, payload):
        request_id = str(uuid.uuid4())[:8]
        model = payload.get("model")
        if not model:
            return _err(400, "model 必填")
        cands = self.select_candidates(model)
        if not cands:
            has_model = any(r["canonical_model"] == model for r in self.ledger.list_instances())
            if not has_model:
                self.ledger.log(request_id, None, model, "CONFIG_INVALID", "模型未配置")
                return _err(404, f"模型 {model} 未配置（M1 仅支持已登记能力，拒绝偷换模型）", "model_not_found")
            return _err(503, f"模型 {model} 的所有实例当前不可用（额度耗尽/冷却中/失效）")
        last_status, last_text = 503, json.dumps({"error": {"message": "all instances failed"}})
        for row in cands:
            # M2 并发：per-instance 原子预留；被并发占用则试下一个候选
            if not self.ledger.reserve(row["instance_id"]):
                continue
            inst = self._merge(row)
            try:
                if inst.get("mode") == "openai-compatible":
                    status, text = self._real.call(inst, payload, self.credentials)
                else:
                    status, text = self._mock.call(inst, payload)
            except Exception as e:  # adapter 内部异常视为 5xx
                status, text = 500, json.dumps({"error": {"message": f"adapter error: {type(e).__name__}"}})
            kind = classify_error(status, text)
            if kind == "OK":
                self.debit(inst, text)                    # 原子扣减
                self.ledger.release(inst["instance_id"])  # 释放预留回「可用」
                self.ledger.log(request_id, inst["instance_id"], model, "OK",
                                f"http {status} via {inst['instance_id']}")
                return status, text
            # 失败：apply_error 写状态（覆盖预留态，等价释放）
            self.apply_error(inst, kind, request_id, model, status)
            if kind in FATAL:
                return status, text
            if kind in RETRYABLE:
                self.ledger.log(request_id, inst["instance_id"], model, "FAILOVER",
                                f"{kind} → 同能力下一实例")
                last_status, last_text = status, text
                continue
            # OTHER：保守处理，标记冷却但不切换
            self.ledger.set_status(inst["instance_id"], "冷却中")
            self.ledger.set_cooldown(inst["instance_id"], now_iso(60))
            return status, text
        return last_status, last_text

    def stream_prepare(self, payload):
        """M3 流式：选候选 + 原子预留 + 返回逐块转发 streamer(wfile)。

        只对 openai-compatible 真实实例启用逐块透传；mock 实例流式回退
        handle_chat 整读（M1 行为）。无候选/预留失败返回非 200。
        切换决策发生在首个 chunk 前；200 后已透传即不重放。
        """
        request_id = str(uuid.uuid4())[:8]
        model = payload.get("model")
        if not model:
            s, t = _err(400, "model 必填")
            return s, t, None
        cands = self.select_candidates(model)
        if not cands:
            has_model = any(r["canonical_model"] == model for r in self.ledger.list_instances())
            if not has_model:
                self.ledger.log(request_id, None, model, "CONFIG_INVALID", "模型未配置")
                s, t = _err(404, f"模型 {model} 未配置（拒绝偷换模型）", "model_not_found")
                return s, t, None
            s, t = _err(503, f"模型 {model} 的所有实例当前不可用")
            return s, t, None
        for row in cands:
            if not self.ledger.reserve(row["instance_id"]):
                continue
            inst = self._merge(row)
            if inst.get("mode") != "openai-compatible":
                self.ledger.release(row["instance_id"])  # mock 实例不走逐块，回退整读
                continue
            if not (inst.get("upstream_base") or ""):
                self.ledger.release(row["instance_id"])
                continue

            def streamer(wfile, _inst=inst, _iid=row["instance_id"]):
                status, err_text = self._real.call_stream(
                    _inst, payload, self.credentials, on_chunk=wfile.write)
                if status == 200:
                    self.ledger.release(_iid)
                    self.ledger.log(request_id, _iid, model, "OK", f"stream via {_iid}")
                else:
                    kind = classify_error(status, err_text)
                    self.apply_error(_inst, kind, request_id, model, status)
                    # 已发 SSE 头，错误只能追加写（首个 chunk 前失败，罕见）
                    try:
                        wfile.write(json.dumps({"error": {"message": err_text[:200]}}, ensure_ascii=False).encode("utf-8"))
                        wfile.flush()
                    except Exception:
                        pass

            return 200, "", streamer
        s, t = _err(503, "无可用真实实例（流式）")
        return s, t, None


def make_handler(sch):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, status, text, ctype="application/json; charset=utf-8"):
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length)

        def _json_body(self):
            raw = self._read_body()
            try:
                return json.loads(raw or b"{}")
            except Exception:
                return None

        def do_GET(self):
            path = self.path
            if path == "/healthz":
                return self._send(200, json.dumps({"ok": True, "instances": len(sch.ledger.list_instances())}))
            if path == "/__admin/instances":
                rows = []
                for r in sch.ledger.list_instances():
                    rows.append({"instance_id": r["instance_id"], "canonical_model": r["canonical_model"],
                                 "status": r["status"], "quota_remaining": r["quota_remaining"],
                                 "cooldown_until": r.get("cooldown_until"), "route_priority": r["route_priority"]})
                return self._send(200, json.dumps(rows, ensure_ascii=False))
            if path == "/__admin/events":
                return self._send(200, json.dumps(sch.ledger.recent_events(50), ensure_ascii=False))
            return self._send(404, json.dumps({"error": {"message": "not found"}}))

        def do_POST(self):
            if self.path == "/v1/chat/completions":
                body = self._json_body()
                if body is None:
                    return self._send(400, json.dumps({"error": {"message": "invalid json body"}}))
                if body.get("stream"):
                    status, text, streamer = sch.stream_prepare(body)
                    if status == 200 and streamer:
                        # 真实实例逐块转发（SSE 无 Content-Length）
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "keep-alive")
                        self.end_headers()
                        self.wfile.flush()
                        try:
                            streamer(self.wfile)
                        except Exception:
                            pass  # 客户端断开等：停止转发
                        return
                    # 无真实实例 → 回退 handle_chat 整读（mock 流式 SSE，带 Content-Length）
                    status, text = sch.handle_chat(body)
                    return self._send(status, text)
                status, text = sch.handle_chat(body)
                return self._send(status, text)
            if self.path.startswith("/__admin/instances/") and self.path.endswith("/status"):
                iid = self.path[len("/__admin/instances/"):-len("/status")]
                body = self._json_body()
                if body is None or "status" not in body:
                    return self._send(400, json.dumps({"error": {"message": "需 {\"status\": ...}"}}))
                sch.ledger.set_status(iid, body["status"])
                sch.ledger.log(None, iid, None, "ADMIN", f"手动置状态 {body['status']}")
                return self._send(200, json.dumps({"ok": True, "instance_id": iid, "status": body["status"]}))
            return self._send(404, json.dumps({"error": {"message": "not found"}}))

        def log_message(self, fmt, *args):  # secret redaction：不打印请求行以外的内容
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap.add_argument("--db", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    sch = Scheduler(args.config, db_path=args.db, port=args.port)
    host = sch.cfg["listen"]["host"]
    port = sch.cfg["listen"]["port"]
    srv = ThreadingHTTPServer((host, port), make_handler(sch))
    print(f"[scheduler] M1 调度器已启动  http://{host}:{port}  (db={sch.cfg['db_path']})")
    print(f"[scheduler] canonical_model={sch.cfg.get('canonical_model')}")
    for r in sch.ledger.list_instances():
        print(f"[scheduler]   实例 {r['instance_id']}  status={r['status']}  quota={r['quota_remaining']}  priority={r['route_priority']}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
