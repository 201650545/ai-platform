# -*- coding: utf-8 -*-
"""
web2api 浏览器桥适配器 (:3102) —— 把登录态网页版模型转成 OpenAI 兼容 API
==========================================================================
架构（2026-09-22 定稿）：真实请求一律在 daily Chrome 的页面上下文里发起
（opencli eval 驱动），本服务只做「编排请求 → 页面内 fetch → 轮询收割 →
OpenAI SSE 重放」。

为什么必须走浏览器桥（站外直调两条死路，均已实测）：
- 千问：阿里云 WAF 对非浏览器指纹返回 JS 挑战页（200 + aliyun_waf_aa HTML）
- MiMo：鉴权 ph 值依赖 httpOnly 小米账号 cookie，站外拿不到

页面上下文天然带全部 cookie 与 WAF 通关态 → token/cookie 永不过期免维护。

端点：
- GET  /health                  → 各适配器就绪状态
- GET  /v1/models               → OpenAI 模型列表
- POST /v1/chat/completions     → OpenAI 兼容（stream=true/false）

依赖：opencli（daemon + daily Chrome 扩展）+ 对应站点登录态。
MiMo 线：需郭老师在 daily Chrome 打开 aistudio.xiaomimimo.com 登录小米账号后启用。
"""
import http.server
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path

PORT = 3102
OPENCLI = r"C:\Users\郭永涛\AppData\Roaming\npm\opencli.cmd"

ADAPTERS = {
    "qwen-web": {
        "session": "qwenweb",
        "page": "https://chat.qwen.ai/",
        "origin_check": "chat.qwen.ai",
        "models": ["qwen3.7-plus"],
        "default_model": "qwen3.7-plus",
        "note": "千问网页版（登录态），浏览器桥",
    },
    "mimo-web": {
        "session": "mimoweb",
        "page": "https://aistudio.xiaomimimo.com/",
        "origin_check": "aistudio.xiaomimimo.com",
        "models": ["mimo-v2.6-pro", "mimo-v2.6-flash"],
        "default_model": "mimo-v2.6-pro",
        "note": "MiMo Studio 网页版（登录态）：钩子抓 ph + 自动代发 UI 消息刷新会话；仅 pro/flash 实测可调（ultraspeed-studio 上游报模型名称错误）",
    },
}

_locks = {cid: threading.Lock() for cid in ADAPTERS}


# ---------------------------------------------------------------- opencli 桥

def ocli(*args, timeout=60):
    r = subprocess.run([OPENCLI, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def ocli_eval(session, js, timeout=60):
    """对象返回值解析为 dict；opencli 输出混有 npm 包装器告警行，截取首尾大括号。"""
    out = ocli("browser", session, "eval", js, timeout=timeout).strip()
    i, j = out.find("{"), out.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(out[i:j + 1])
        except Exception:  # noqa: BLE001
            pass
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {"_raw": out[:300]}


def ensure_page(session, page, origin_check):
    """确保浏览器桥会话落在目标站点上（同会话复用既有标签）。"""
    st = ocli_eval(session, "JSON.stringify({url:location.href,ready:document.readyState})")
    url = str(st.get("url", ""))
    if origin_check not in url:
        ocli("browser", session, "open", page, "--window", "background", timeout=40)
        for _ in range(15):
            time.sleep(1.5)
            st = ocli_eval(session, "JSON.stringify({url:location.href,ready:document.readyState})")
            if origin_check in str(st.get("url", "")) and st.get("ready") == "complete":
                break
        else:
            return False
    return origin_check in str(st.get("url", ""))


# ---------------------------------------------------------------- 千问适配器

QWEN_HEADERS = ("{'Accept':'application/json','X-Accel-Buffering':'no',"
                "'X-Request-Id':crypto.randomUUID(),'Content-Type':'application/json',"
                "'Version':'0.2.91','source':'web',"
                "'Timezone':new Date().toString().match(/GMT[+-]\\d+/)[0],"
                "'Authorization':'Bearer '+localStorage.token}")

QWEN_NEW_CHAT = ("async ()=>{"
                 "const r=await fetch('/api/v2/chats/new',{method:'POST',credentials:'include',"
                 "headers:%s,body:JSON.stringify({title:'w2a-bridge',chat:{}})});"
                 "const j=await r.json().catch(()=>({}));"
                 "return {ok:!!(j.data&&j.data.id),id:(j.data&&j.data.id)||null,raw:JSON.stringify(j).slice(0,150)};"
                 "}" % QWEN_HEADERS)

QWEN_START = ("()=>{"
              "const job='__JOB__'; const cid='__CID__'; const prompt=__PROMPT__;"
              "window.__w2a=window.__w2a||{}; window.__w2a[job]={lines:[],done:false};"
              "const body={stream:true,version:'2.1',incremental_output:true,chatId:cid,parentId:'',"
              "chat_id:cid,chat_mode:'normal',model:__MODEL__,parent_id:null,"
              "messages:[{id:null,fid:crypto.randomUUID(),parentId:null,childrenIds:[crypto.randomUUID()],"
              "role:'user',content:prompt,user_action:'chat',files:[],"
              "timestamp:Math.floor(Date.now()/1000),models:[__MODEL__],model:'',chat_type:'t2t',"
              "feature_config:{thinking_enabled:false,output_schema:'phase',research_mode:'normal',"
              "auto_thinking:false,thinking_mode:'Auto',thinking_format:'summary',auto_search:false},"
              "extra:{meta:{subChatType:'t2t'}},sub_chat_type:'t2t',parent_id:null}],"
              "timestamp:Math.floor(Date.now()/1000)};"
              "const ctl=new AbortController(); window.__w2a[job].ctl=ctl;"
              "setTimeout(()=>ctl.abort().catch(()=>{}),240000);"
              "(async()=>{"
              "try{"
              "const r=await fetch('/api/v2/chat/completions?chat_id='+cid,{method:'POST',credentials:'include',"
              "signal:ctl.signal,headers:%s,body:JSON.stringify(body)});"
              "if(!r.ok||!r.body){const t=await r.text().catch(()=>'');"
              "window.__w2a[job].lines.push(JSON.stringify({w2a_err:r.status,raw:t.slice(0,300)}));"
              "window.__w2a[job].done=true;return;}"
              "const reader=r.body.getReader(); const dec=new TextDecoder(); let buf='';"
              "while(true){const {done,value}=await reader.read(); if(done)break;"
              "buf+=dec.decode(value,{stream:true}); let idx;"
              "while((idx=buf.indexOf('\\n\\n'))>=0){const ev=buf.slice(0,idx); buf=buf.slice(idx+2);"
              "const m=ev.match(/^data:\\s*(.*)$/m); if(m) window.__w2a[job].lines.push(m[1]);}}"
              "}catch(e){window.__w2a[job].lines.push(JSON.stringify({w2a_err:'fetch',raw:String(e)}));}"
              "window.__w2a[job].done=true;"
              "})();"
              "return {started:true,job:job};}"
              % QWEN_HEADERS)

QWEN_POLL = ("()=>{const j=(window.__w2a||{})['__JOB__']; if(!j)return {err:'nojob'};"
             "const take=j.lines.splice(0,j.lines.length);"
             "return {n:take.length,lines:take,done:!!j.done};}")


def qwen_flatten_messages(messages):
    """多轮对话拍平成单条 user prompt（网页版无服务端多轮注入，按文本拼接）。"""
    if len(messages) == 1 and messages[0].get("role") == "user":
        return messages[0].get("content", "")
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # 多模态数组只取文本段
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        tag = {"system": "系统指令", "user": "用户", "assistant": "助手"}.get(role, role)
        parts.append("%s：%s" % (tag, content))
    return "\n\n".join(parts)


def qwen_send(cid, model, prompt, session):
    """页面上下文发起流式请求，返回 job id。"""
    js = (QWEN_START.replace("__JOB__", uuid.uuid4().hex[:12])
          .replace("__CID__", cid)
          .replace("__MODEL__", json.dumps(model))
          .replace("__PROMPT__", json.dumps(prompt, ensure_ascii=False)))
    js = js.replace("__SESSION_EVALESC__", "")
    res = ocli_eval(session, js)
    if not res.get("started"):
        raise RuntimeError("start 失败：%s" % json.dumps(res, ensure_ascii=False)[:200])
    return res["job"]


def qwen_poll(job, session):
    res = ocli_eval(session, QWEN_POLL.replace("__JOB__", job))
    if res.get("err"):
        return [], True
    return res.get("lines", []), bool(res.get("done"))


QWEN_DEL_CHAT = ("async ()=>{"
                 "const ctl=new AbortController(); setTimeout(()=>ctl.abort(),10000);"
                 "try{"
                 "const r=await fetch('/api/v2/chats/__CID__',{method:'DELETE',credentials:'include',"
                 "signal:ctl.signal,"
                 "headers:{'Accept':'application/json','X-Request-Id':crypto.randomUUID(),"
                 "'Version':'0.2.91','source':'web',"
                 "'Authorization':'Bearer '+localStorage.token}});"
                 "return {status:r.status};"
                 "}catch(e){return {aborted:true};}" "}")


def qwen_del_chat_async(cid, session):
    """用完即删会话，防网页版聊天记录爆炸；失败不抛（下轮巡检可手动清）。"""
    try:
        ocli_eval(session, QWEN_DEL_CHAT.replace("__CID__", cid), timeout=20)
    except Exception:  # noqa: BLE001
        pass


def qwen_iter_sse(cid, model, prompt, session):
    """ yield (delta_text, usage_dict_or_None)；自动建会话+收割。"""
    made = ocli_eval(session, QWEN_NEW_CHAT)
    if not made.get("ok"):
        raise RuntimeError("建会话失败：%s" % json.dumps(made, ensure_ascii=False)[:200])
    cid = made["id"]
    job = qwen_send(cid, model, prompt, session)
    t0 = time.time()
    usage = None
    got_any = False
    try:
        while True:
            lines, done = qwen_poll(job, session)
            if lines:
                got_any = True
            for ln in lines:
                try:
                    ev = json.loads(ln)
                except Exception:  # noqa: BLE001
                    continue
                if "w2a_err" in ev:
                    raise RuntimeError("上游错误 %s：%s" % (ev["w2a_err"], ev.get("raw", "")))
                if ev.get("usage"):
                    usage = ev["usage"]
                ch = (ev.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                if delta.get("content") and delta.get("phase") != "thinking":
                    yield delta["content"], None
                if delta.get("status") == "finished" or ln.strip() == "[DONE]":
                    done = True
            if done:
                if usage:
                    yield "", usage
                return
            if not got_any and time.time() - t0 > 75:
                # 上游偶发风控挂起：新会话+completions 无响应（UI 正常），快速失败让回落链接管
                raise RuntimeError("上游 75s 无首包（疑似风控挂起），建议稍后重试")
            if time.time() - t0 > 230:
                raise RuntimeError("收割超时")
            time.sleep(0.35)
    finally:
        qwen_del_chat_async(cid, session)


# ---------------------------------------------------------------- MiMo 适配器

# ph 机制（2026-09-22 实测破译）：SPA 每会话随机生成 16B ph，经 401→serviceLogin→sts
# 链绑定到 httpOnly 会话；跨域 fetch 走不完 SSO（CORS），故适配器不复算 ph，而是
# ①常驻钩子抓 SPA 真实请求里的 ph ②没有/失效时自动代发一条 UI 消息触发 SPA 自愈
MIMO_HOOK = ("(()=>{if(window.__mimo_ph_hook)return JSON.stringify({ok:true,ph:window.__mimo_ph||null});"
             "window.__mimo_ph_hook=true; const of=window.fetch;"
             "window.fetch=function(...args){try{let url=typeof args[0]==='string'?args[0]:(args[0]&&args[0].url);"
             "const m=String(url).match(/bot\\/chat\\?xiaomichatbot_ph=([^&]+)/);"
             "if(m)window.__mimo_ph=decodeURIComponent(m[1]);}catch(e){} return of.apply(this,args);};"
             "return JSON.stringify({ok:true,ph:window.__mimo_ph||null});})()")

MIMO_GETPH = "(()=>JSON.stringify({ph:window.__mimo_ph||null}))()"

MIMO_UISEND = ("(()=>{const ta=document.querySelector('textarea'); if(!ta)return JSON.stringify({err:'no ta'});"
               "const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;"
               "set.call(ta,__TEXT__); ta.dispatchEvent(new Event('input',{bubbles:true}));"
               "let container=ta,btn=null;"
               "for(let i=0;i<6&&container.parentElement;i++){container=container.parentElement;"
               "const b=[...container.querySelectorAll('button')].filter(x=>!x.disabled&&x.querySelector('svg'));"
               "if(b.length>=2){btn=b[b.length-1];break;}}"
               "if(!btn)return JSON.stringify({err:'no btn'}); btn.click();"
               "return JSON.stringify({sent:true});})()")

MIMO_START = ("(()=>{const job='__JOB__'; const ph=window.__mimo_ph||''; if(!ph)return JSON.stringify({err:'no ph'});"
              "window.__m2a=window.__m2a||{}; window.__m2a[job]={lines:[],done:false};"
              "const body={msgId:Array.from(crypto.getRandomValues(new Uint8Array(16))).map(b=>b.toString(16).padStart(2,'0')).join(''),"
              "conversationId:Array.from(crypto.getRandomValues(new Uint8Array(16))).map(b=>b.toString(16).padStart(2,'0')).join(''),"
              "query:__PROMPT__,isEditedQuery:false,"
              "modelConfig:{enableThinking:false,webSearchStatus:'disabled',model:__MODEL__},multiMedias:[]};"
              "const ctl=new AbortController(); window.__m2a[job].ctl=ctl;"
              "setTimeout(()=>ctl.abort().catch(()=>{}),180000);"
              "(async()=>{try{"
              "const r=await fetch('/open-apis/bot/chat?xiaomichatbot_ph='+encodeURIComponent(ph),"
              "{method:'POST',credentials:'include',signal:ctl.signal,"
              "headers:{'Content-Type':'application/json','x-timeZone':'Asia/Shanghai','Accept-Language':'system'},"
              "body:JSON.stringify(body)});"
              "if(!r.ok){const t=await r.text().catch(()=>'');"
              "window.__m2a[job].lines.push(JSON.stringify({m2a_err:r.status,raw:t.slice(0,200)}));"
              "window.__m2a[job].done=true;return;}"
              "const reader=r.body.getReader(); const dec=new TextDecoder(); let buf='';"
              "while(true){const {done,value}=await reader.read(); if(done)break;"
              "buf+=dec.decode(value,{stream:true}); let idx;"
              "while((idx=buf.indexOf('\\n\\n'))>=0){const ev=buf.slice(0,idx); buf=buf.slice(idx+2);"
              "const em=ev.match(/^event:(.+)$/m); const dm=ev.match(/^data:(.*)$/m);"
              "window.__m2a[job].lines.push(JSON.stringify({e:em?em[1].trim():'',d:dm?dm[1]:''}));}}"
              "}catch(e){window.__m2a[job].lines.push(JSON.stringify({m2a_err:'fetch',raw:String(e)}));}"
              "window.__m2a[job].done=true;})();"
              "return JSON.stringify({started:true,job:job});})()")

MIMO_POLL = ("(()=>{const j=(window.__m2a||{})['__JOB__']; if(!j)return JSON.stringify({err:'nojob'});"
             "const take=j.lines.splice(0,j.lines.length);"
             "return JSON.stringify({n:take.length,lines:take,done:!!j.done});})()")


MIMO_CLICK_SEND = ("(()=>{const ta=document.querySelector('textarea'); if(!ta)return JSON.stringify({err:'no ta'});"
                   "let container=ta,btn=null;"
                   "for(let i=0;i<6&&container.parentElement;i++){container=container.parentElement;"
                   "const b=[...container.querySelectorAll('button')].filter(x=>!x.disabled&&x.querySelector('svg'));"
                   "if(b.length>=2){btn=b[b.length-1];break;}}"
                   "if(!btn)return JSON.stringify({err:'no btn'}); btn.click();"
                   "return JSON.stringify({sent:true});})()")


def mimo_ensure_ph(session, timeout_s=70):
    """读钩子里的 ph；没有就 CDP type + 点发送按钮代发一条 UI 消息，
    等真实请求出现后钩子即捕获 ph（SPA 会话失效时会顺带自愈走 SSO）。"""
    res = ocli_eval(session, MIMO_HOOK)
    if res.get("ph"):
        return res["ph"]
    ocli("browser", session, "type", "textarea", "ping", timeout=40)
    clicked = ocli_eval(session, MIMO_CLICK_SEND)
    if not clicked.get("sent"):
        raise RuntimeError("点发送按钮失败：%s" % json.dumps(clicked, ensure_ascii=False)[:150])
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(1.2)
        got = ocli_eval(session, MIMO_GETPH)
        if got.get("ph"):
            return got["ph"]
        # SSO 导航会重置 window：钩子没了就重装再来一轮
        re_hook = ocli_eval(session, MIMO_HOOK)
        if not re_hook.get("ok"):
            continue
        if re_hook.get("ph"):
            return re_hook["ph"]
    raise RuntimeError("等待 ph 超时（页面未产生 bot/chat 请求）")


def mimo_iter_sse(model, prompt, session):
    """yield (delta_text, None)。MiMo 把思考段以 <think>…</think> 内嵌在正文流里
    （enableThinking 关不掉），故持有首段直到 </think> 出现再吐答案段增量。"""
    mimo_ensure_ph(session)
    job = uuid.uuid4().hex[:12]
    js = (MIMO_START.replace("__JOB__", job)
          .replace("__MODEL__", json.dumps(model))
          .replace("__PROMPT__", json.dumps(prompt, ensure_ascii=False)))
    res = ocli_eval(session, js)
    if res.get("err"):
        raise RuntimeError("start 失败：%s" % json.dumps(res, ensure_ascii=False)[:150])
    raw = ""
    sent = 0
    in_answer = False
    t0 = time.time()
    while True:
        pr = ocli_eval(session, MIMO_POLL.replace("__JOB__", job))
        lines = pr.get("lines", []) if not pr.get("err") else []
        done = bool(pr.get("done"))
        for ln in lines:
            try:
                ev = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if "m2a_err" in ev:
                raise RuntimeError("上游错误 %s：%s" % (ev["m2a_err"], ev.get("raw", "")))
            if ev.get("e") == "error":
                try:
                    detail = json.loads(ev.get("d") or "{}").get("content", "")
                except Exception:  # noqa: BLE001
                    detail = ev.get("d", "")
                raise RuntimeError("上游 error 事件：%s" % (detail or "unknown"))
            if ev.get("e") != "message":
                continue
            try:
                payload = json.loads(ev.get("d") or "{}")
            except Exception:  # noqa: BLE001
                continue
            if payload.get("type") != "text":
                continue
            raw += payload.get("content", "")
            if not in_answer:
                if "</think>" in raw:
                    raw = raw.split("</think>", 1)[1]
                    sent = 0
                    in_answer = True
                elif "<think>" in raw:
                    continue  # 思考段未闭合，继续持有
                elif len(raw) > 0 and not raw.lstrip().startswith("<"):
                    in_answer = True  # 无思考段的纯答案流
        if in_answer:
            out = raw.replace("\x00", "")
            if len(out) > sent:
                yield out[sent:], None
                sent = len(out)
        if done:
            if not in_answer and raw:
                # 流结束仍困在思考段：正则剥离后兜底吐出
                import re as _re
                out = _re.sub(r"<think>[\s\S]*?</think>", "", raw).replace("\x00", "")
                if out:
                    yield out, None
            return
        if time.time() - t0 > 170:
            raise RuntimeError("收割超时")
        if not lines:
            time.sleep(0.35)


# ---------------------------------------------------------------- OpenAI 壳

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            states = {}
            for cid, ad in ADAPTERS.items():
                st = ocli_eval(ad["session"], "JSON.stringify({url:location.href})")
                states[cid] = {
                    "page_ready": ad["origin_check"] in str(st.get("url", "")),
                    "note": ad["note"],
                }
                if cid == "qwen-web" and states[cid]["page_ready"]:
                    tok = ocli_eval(ad["session"], "JSON.stringify({t:!!localStorage.token})")
                    states[cid]["login"] = bool(tok.get("t"))
            return self._json(200, {"status": "ok", "adapters": states})
        if self.path == "/v1/models":
            data = []
            for cid, ad in ADAPTERS.items():
                for m in ad["models"]:
                    data.append({"id": "%s/%s" % (cid, m), "object": "model",
                                 "owned_by": cid})
            return self._json(200, {"object": "list", "data": data})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return self._json(400, {"error": "bad json"})

        full_model = req.get("model", "qwen-web/qwen3.7-plus")
        cid, _, model = full_model.partition("/")
        if cid not in ADAPTERS:
            cid, model = "qwen-web", full_model
        ad = ADAPTERS[cid]
        if not ad["models"]:
            return self._json(503, {"error": "该网页适配器未启用：%s（%s）" % (cid, ad["note"])})
        model = model or ad["default_model"]
        stream = bool(req.get("stream"))
        messages = req.get("messages") or []
        if not messages:
            return self._json(400, {"error": "messages 为空"})

        if not ensure_page(ad["session"], ad["page"], ad["origin_check"]):
            return self._json(502, {"error": "浏览器桥未就绪（Chrome/opencli/登录态）"})
        prompt = qwen_flatten_messages(messages)
        comp_id = "chatcmpl-w2a-" + uuid.uuid4().hex[:10]
        created = int(time.time())

        got = _locks[cid].acquire(timeout=30)
        if not got:
            return self._json(429, {"error": "浏览器桥忙（单飞行并发），请稍后"})
        try:
            it_fn = mimo_iter_sse if cid == "mimo-web" else (
                lambda m, p, s: qwen_iter_sse(None, m, p, s))
            if not stream:
                chunks = []
                usage = None
                for delta, u in it_fn(model, prompt, ad["session"]):
                    chunks.append(delta)
                    if u:
                        usage = u
                out = {"id": comp_id, "object": "chat.completion", "created": created,
                       "model": full_model,
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(chunks)},
                                    "finish_reason": "stop"}],
                       "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
                return self._json(200, out)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def emit(obj):
                self.wfile.write(("data: %s\n\n" % json.dumps(obj, ensure_ascii=False)).encode("utf-8"))
                self.wfile.flush()

            emit({"id": comp_id, "object": "chat.completion.chunk", "created": created,
                  "model": full_model,
                  "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
            usage = None
            for delta, u in it_fn(model, prompt, ad["session"]):
                if not delta:
                    if u:
                        usage = u
                    continue
                emit({"id": comp_id, "object": "chat.completion.chunk", "created": created,
                      "model": full_model,
                      "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]})
            emit({"id": comp_id, "object": "chat.completion.chunk", "created": created,
                  "model": full_model,
                  "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            if usage:
                emit({"id": comp_id, "object": "chat.completion.chunk", "created": created,
                      "model": full_model, "usage": usage,
                      "choices": [{"index": 0, "delta": {}, "finish_reason": None}]})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            try:
                self._json(502, {"error": "web2api 上游失败：%s" % exc})
            except Exception:  # noqa: BLE001
                pass
        finally:
            _locks[cid].release()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    srv = Server(("127.0.0.1", PORT), Handler)
    print("web2api 浏览器桥 :%d 就绪（qwen-web 已启用；mimo-web 待登录）" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
