# -*- coding: utf-8 -*-
"""capability contract test（RFC v2 G · P0）：渠道注册时实测能力，fail-closed。

防「假健康」重演：渠道声明 tools/vision 支持但实际不支持 OpenAI 协议
（xiaohongshu/dots3-note-prev 曾误标 tools 崩过 cherry studio 工具调用，
S-20260902-07 手改才恢复）。注册后异步对 default_model 跑 chat/vision/tools 三测，
把实测真值写回 model_capabilities.json（capabilities.load_model_capabilities 的 mtime
缓存自动重载），check_candidate 据此把不符能力排除出路由（fail-closed）。
chat 测不过 = 整渠道隔离（chat 恒为必需能力，check_candidate 因 mismatch 拒选）。

探测执行器复用 channels._urlopen（含渠道代理），但**不**走 channels.chat_completion，
避免测试计入 rate_limit/quota 台账污染真实用量。
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

import channels
import capabilities

_write_lock = threading.Lock()

_PING = {"role": "user", "content": "ping"}
# 1x1 透明 PNG data URI（极小微载荷，验证 vision 上传通路是否被接受）
_IMG = ("data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _get_key(cid):
    try:
        return channels.get_key(cid) or ""
    except Exception:  # noqa: BLE001
        return ""


def _pick_model(channel_id, definition):
    ch = channels.CHANNELS.get(channel_id) or definition or {}
    models = ch.get("models") or []
    return (ch.get("default_model") or (models[0] if models else "") or "")


def _probe(channel_id, definition, model, payload):
    """单发 chat 探测：复用 channels._urlopen（含代理）。返回 (http_status|None, body_text)。
    OK 与错误都原样返回，不抛；None 状态 = 本地/传输失败。"""
    ch = channels.CHANNELS.get(channel_id) or definition or {}
    url = ch["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + _get_key(channel_id),
        "User-Agent": ch.get("ua", "unified-ai-gateway/1.0"),
    }, method="POST")
    try:
        with channels._urlopen(req, timeout=15, channel_id=channel_id) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as he:
        try:
            return he.code, he.read().decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return he.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def _chat_ok(channel_id, definition, model):
    status, body = _probe(channel_id, definition, model, {
        "model": model, "messages": [_PING], "max_tokens": 4, "stream": False,
    })
    if status is None or status >= 400:
        return False
    try:
        c = (json.loads(body) or {}).get("choices") or []
        return bool((c[0].get("message") or {}).get("content")) if c else False
    except Exception:  # noqa: BLE001
        return False


def _vision_ok(channel_id, definition, model):
    status, body = _probe(channel_id, definition, model, {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "describe this image"},
            {"type": "image_url", "image_url": {"url": _IMG}},
        ]}],
        "max_tokens": 8, "stream": False,
    })
    # vision 不支持通常报 4xx（image/vision 不支持）；接受 = 通过
    return not (status is None or status >= 400)


def _tools_ok(channel_id, definition, model):
    status, body = _probe(channel_id, definition, model, {
        "model": model, "messages": [_PING],
        "tools": [{"type": "function", "function": {
            "name": "get_weather", "description": "query weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}],
        "tool_choice": "none",  # 不强制返回 tool_calls，仅验证协议接受
        "max_tokens": 8, "stream": False,
    })
    # 400/415 = 协议不接受 tools；接受 = 通过
    return not (status is None or status >= 400)


def verify_channel(channel_id, definition):
    """跑三测，返回 {chat, vision, tools: bool}。chat 恒测（必须真实可用）；全测不预判声明"""
    model = _pick_model(channel_id, definition)
    if not model:
        return {"chat": None, "vision": None, "tools": None}
    return {
        "chat": _chat_ok(channel_id, definition, model),
        "vision": _vision_ok(channel_id, definition, model),
        "tools": _tools_ok(channel_id, definition, model),
    }


def persist_results(channel_id, model, verified):
    """写实测真值到运行时 model_capabilities.json（热重载文件）。chat=False=整渠道隔离。"""
    if not model or not verified:
        return
    path = capabilities.CAP_FILE if os.path.exists(capabilities.CAP_FILE) \
        else os.path.join(channels.DATA_DIR, "model_capabilities.json")
    with _write_lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {"version": 1, "channels": {}}
        data.setdefault("channels", {})
        chan = data["channels"].setdefault(channel_id, {})
        m = chan.setdefault("models", {}).setdefault(model, {})
        for cap in ("chat", "vision", "tools"):
            if verified.get(cap) is not None:
                m[cap] = bool(verified[cap])
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001
            return
    try:
        capabilities.load_model_capabilities()  # 刷新 mtime 缓存，令新值立即生效
    except Exception:  # noqa: BLE001
        pass
    try:
        channels.invalidate_channel_cache(channel_id)
    except Exception:  # noqa: BLE001
        pass


def trigger_async(channel_id, definition):
    """注册后异步跑契约测试；无 key 则最多等 ~8s 再测（key 可能刚 POST 晚到）。"""
    def _run():
        try:
            model = _pick_model(channel_id, definition)
            if not model:
                return
            if not _get_key(channel_id):
                for _ in range(40):  # 等待 key 落库（save_channel_key 在 save_custom_channel 之后）
                    time.sleep(0.2)
                    if _get_key(channel_id):
                        break
                if not _get_key(channel_id):
                    return  # 无 key 不测（未配置鉴权无从验证）
            verified = verify_channel(channel_id, definition)
            if verified.get("chat") is None:
                return
            persist_results(channel_id, model, verified)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_run, daemon=True).start()