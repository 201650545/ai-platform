# -*- coding: utf-8 -*-
"""
web2api v2（:3102）—— 浏览器桥双层架构（GPT 镜像 2026-09-23 方案落地）
==========================================================================
层 1  BrowserBackend：唯一的浏览器操作层。opencli eval 驱动 daily Chrome，
      只提供「页面就绪 + 发起 JS 任务 + 轮询收割」三种原语，不知道任何
      上游协议（千问/MiMo/未来站点一律平等）。
层 2  ProviderAdapter：每平台一个适配器，只做「平台协议 ↔ OpenAI 协议」
      转换（会话管理、SSE 解析、鉴权自愈、思考段剥离），通过 backend 执行，
      不触碰 opencli/subprocess。
层 3  OpenAI 壳：/v1/models、/v1/chat/completions，按模型前缀路由到 adapter。

规则（GPT 方案约束）：
- 3100 网关永远只看到 base_url+key 的普通渠道（custom_channels 已挂）。
- 新增平台 = 新增一个 Adapter 类，壳与后端零改动。
- 浏览器型渠道是 opportunistic capacity：每 adapter 独立信号量（缺省并发 1）。

依赖：opencli（daemon + daily Chrome 扩展）+ 对应站点登录态。
"""
import http.server
import json
import subprocess
import threading
import time
import uuid

PORT = 3102
OPENCLI = r"C:\Users\郭永涛\AppData\Roaming\npm\opencli.cmd"

CREATE_NO_WINDOW = 0x08000000


# ============================================================
# 层 1：BrowserBackend（浏览器执行后端）
# ============================================================

class BrowserBackend:
    """opencli 驱动的页面任务执行器。一个 session = Chrome 里一个常驻标签。"""

    def __init__(self, opencli=OPENCLI):
        self._opencli = opencli
        self._session_locks = {}

    def _lock(self, session):
        if session not in self._session_locks:
            self._session_locks[session] = threading.Lock()
        return self._session_locks[session]

    def ocli(self, *args, timeout=60):
        r = subprocess.run([self._opencli, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)
        return (r.stdout or "") + (r.stderr or "")

    def eval(self, session, js, timeout=60):
        """对象返回值解析为 dict；opencli 输出混有 npm 包装器告警行，截取首尾大括号。"""
        out = self.ocli("browser", session, "eval", js, timeout=timeout).strip()
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

    def ensure_page(self, session, page, origin_check):
        """确保会话标签落在目标站点上（同会话复用既有标签）。"""
        st = self.eval(session, "JSON.stringify({url:location.href,ready:document.readyState})")
        if origin_check in str(st.get("url", "")):
            return True
        self.ocli("browser", session, "open", page, "--window", "background", timeout=40)
        for _ in range(15):
            time.sleep(1.5)
            st = self.eval(session, "JSON.stringify({url:location.href,ready:document.readyState})")
            if origin_check in str(st.get("url", "")) and st.get("ready") == "complete":
                return True
        return origin_check in str(st.get("url", ""))

    def run_job(self, session, start_js, poll_js, on_lines, first_byte_timeout=None,
                total_timeout=170, idle_sleep=0.35):
        """通用「fire JS → 轮询收割 lines」任务循环。
        start_js 须立刻返回 {started|err}；poll_js 返回 {lines:[], done:bool}。
        on_lines(lines) 由 adapter 解析协议；抛异常即中止。
        返回 (got_any, elapsed)。"""
        t0 = time.time()
        got_any = False
        res = self.eval(session, start_js)
        if res.get("err"):
            raise RuntimeError("start 失败：%s" % json.dumps(res, ensure_ascii=False)[:200])
        while True:
            pr = self.eval(session, poll_js)
            lines = pr.get("lines", []) if not pr.get("err") else []
            done = bool(pr.get("done"))
            if lines:
                got_any = True
                on_lines(lines)
            if done:
                return got_any, time.time() - t0
            now = time.time() - t0
            if first_byte_timeout and not got_any and now > first_byte_timeout:
                raise RuntimeError("上游 %ds 无首包（疑似风控挂起），建议稍后重试" % first_byte_timeout)
            if now > total_timeout:
                raise RuntimeError("收割超时")
            if not lines:
                time.sleep(idle_sleep)


BACKEND = BrowserBackend()


# ============================================================
# 层 2：ProviderAdapter（平台协议适配器）
# ============================================================

class QwenAdapter:
    """千问 chat.qwen.ai：显式建会话 → completions SSE → 用完即删。"""

    id = "qwen-web"
    session = "qwenweb"
    page = "https://chat.qwen.ai/"
    origin_check = "chat.qwen.ai"
    models = ["qwen3.7-plus"]
    default_model = "qwen3.7-plus"
    note = "千问网页版（登录态），direct adapter"

    HEADERS = ("{'Accept':'application/json','X-Accel-Buffering':'no',"
               "'X-Request-Id':crypto.randomUUID(),'Content-Type':'application/json',"
               "'Version':'0.2.91','source':'web',"
               "'Timezone':new Date().toString().match(/GMT[+-]\\d+/)[0],"
               "'Authorization':'Bearer '+localStorage.token}")

    NEW_CHAT = ("async ()=>{"
                "const r=await fetch('/api/v2/chats/new',{method:'POST',credentials:'include',"
                "headers:%s,body:JSON.stringify({title:'w2a-bridge',chat:{}})});"
                "const j=await r.json().catch(()=>({}));"
                "return {ok:!!(j.data&&j.data.id),id:(j.data&&j.data.id)||null};"
                "}" % HEADERS)

    START = ("()=>{"
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
             % HEADERS)

    POLL = ("()=>{const j=(window.__w2a||{})['__JOB__']; if(!j)return {err:'nojob'};"
            "const take=j.lines.splice(0,j.lines.length);"
            "return {n:take.length,lines:take,done:!!j.done};}")

    DEL_CHAT = ("async ()=>{"
                "const ctl=new AbortController(); setTimeout(()=>ctl.abort(),10000);"
                "try{"
                "const r=await fetch('/api/v2/chats/__CID__',{method:'DELETE',credentials:'include',"
                "signal:ctl.signal,"
                "headers:{'Accept':'application/json','X-Request-Id':crypto.randomUUID(),"
                "'Version':'0.2.91','source':'web',"
                "'Authorization':'Bearer '+localStorage.token}});"
                "return {status:r.status};"
                "}catch(e){return {aborted:true};}" "}")

    FIRST_BYTE_TIMEOUT = 75
    TOTAL_TIMEOUT = 230

    def chat_stream(self, model, prompt):
        """yield (delta_text, usage)；run_job 在工作线程跑，增量经队列回传保证真流式。"""
        import queue as _q
        made = BACKEND.eval(self.session, self.NEW_CHAT)
        if not made.get("ok"):
            raise RuntimeError("建会话失败：%s" % json.dumps(made, ensure_ascii=False)[:200])
        cid = made["id"]
        job = uuid.uuid4().hex[:12]
        start = (self.START.replace("__JOB__", job).replace("__CID__", cid)
                 .replace("__MODEL__", json.dumps(model))
                 .replace("__PROMPT__", json.dumps(prompt, ensure_ascii=False)))
        poll = self.POLL.replace("__JOB__", job)
        q = _q.Queue()
        state = {"usage": None}

        def handle(lines):
            for ln in lines:
                try:
                    ev = json.loads(ln)
                except Exception:  # noqa: BLE001
                    continue
                if "w2a_err" in ev:
                    raise RuntimeError("上游错误 %s：%s" % (ev["w2a_err"], ev.get("raw", "")))
                if ev.get("usage"):
                    state["usage"] = ev["usage"]
                ch = (ev.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                if delta.get("content") and delta.get("phase") != "thinking":
                    q.put(("delta", delta["content"]))
                if delta.get("status") == "finished" or ln.strip() == "[DONE]":
                    pass

        def worker():
            try:
                BACKEND.run_job(self.session, start, poll, handle,
                                first_byte_timeout=self.FIRST_BYTE_TIMEOUT,
                                total_timeout=self.TOTAL_TIMEOUT)
                q.put(("done", None))
            except Exception as exc:  # noqa: BLE001
                q.put(("error", exc))
            finally:
                try:
                    BACKEND.eval(self.session, self.DEL_CHAT.replace("__CID__", cid), timeout=20)
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=worker, daemon=True).start()
        while True:
            kind, payload = q.get()
            if kind == "delta":
                yield payload, None
            elif kind == "done":
                if state["usage"]:
                    yield "", state["usage"]
                return
            elif kind == "error":
                raise payload


class MimoAdapter:
    """MiMo aistudio：钩子抓 ph + 失效自动代发 UI 消息自愈；think 段持有剥离。"""

    id = "mimo-web"
    session = "mimoweb"
    page = "https://aistudio.xiaomimimo.com/"
    origin_check = "aistudio.xiaomimimo.com"
    models = ["mimo-v2.6-pro", "mimo-v2.6-flash"]
    default_model = "mimo-v2.6-pro"
    note = ("MiMo Studio 网页版：钩子抓 ph + 自动代发 UI 消息自愈；"
            "仅 pro/flash 实测可调（ultraspeed-studio 上游报模型名称错误）")

    HOOK = ("(()=>{if(window.__mimo_ph_hook)return JSON.stringify({ok:true,ph:window.__mimo_ph||null});"
            "window.__mimo_ph_hook=true; const of=window.fetch;"
            "window.fetch=function(...args){try{let url=typeof args[0]==='string'?args[0]:(args[0]&&args[0].url);"
            "const m=String(url).match(/bot\\/chat\\?xiaomichatbot_ph=([^&]+)/);"
            "if(m)window.__mimo_ph=decodeURIComponent(m[1]);}catch(e){} return of.apply(this,args);};"
            "return JSON.stringify({ok:true,ph:window.__mimo_ph||null});})()")

    GETPH = "(()=>JSON.stringify({ph:window.__mimo_ph||null}))()"

    CLICK_SEND = ("(()=>{const ta=document.querySelector('textarea'); if(!ta)return JSON.stringify({err:'no ta'});"
                  "let container=ta,btn=null;"
                  "for(let i=0;i<6&&container.parentElement;i++){container=container.parentElement;"
                  "const b=[...container.querySelectorAll('button')].filter(x=>!x.disabled&&x.querySelector('svg'));"
                  "if(b.length>=2){btn=b[b.length-1];break;}}"
                  "if(!btn)return JSON.stringify({err:'no btn'}); btn.click();"
                  "return JSON.stringify({sent:true});})()")

    START = ("(()=>{const job='__JOB__'; const ph=window.__mimo_ph||''; if(!ph)return JSON.stringify({err:'no ph'});"
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

    POLL = ("(()=>{const j=(window.__m2a||{})['__JOB__']; if(!j)return JSON.stringify({err:'nojob'});"
            "const take=j.lines.splice(0,j.lines.length);"
            "return JSON.stringify({n:take.length,lines:take,done:!!j.done});})()")

    PH_WAIT_S = 70
    TOTAL_TIMEOUT = 170

    def _ensure_ph(self):
        res = BACKEND.eval(self.session, self.HOOK)
        if res.get("ph"):
            return res["ph"]
        BACKEND.ocli("browser", self.session, "type", "textarea", "ping", timeout=40)
        clicked = BACKEND.eval(self.session, self.CLICK_SEND)
        if not clicked.get("sent"):
            raise RuntimeError("点发送按钮失败：%s" % json.dumps(clicked, ensure_ascii=False)[:150])
        t0 = time.time()
        while time.time() - t0 < self.PH_WAIT_S:
            time.sleep(1.2)
            got = BACKEND.eval(self.session, self.GETPH)
            if got.get("ph"):
                return got["ph"]
            re_hook = BACKEND.eval(self.session, self.HOOK)
            if not re_hook.get("ok"):
                continue
            if re_hook.get("ph"):
                return re_hook["ph"]
        raise RuntimeError("等待 ph 超时（页面未产生 bot/chat 请求）")

    def chat_stream(self, model, prompt):
        self._ensure_ph()
        job = uuid.uuid4().hex[:12]
        start = (self.START.replace("__JOB__", job)
                 .replace("__MODEL__", json.dumps(model))
                 .replace("__PROMPT__", json.dumps(prompt, ensure_ascii=False)))
        poll = self.POLL.replace("__JOB__", job)
        raw = ""
        sent = 0
        evbuf = {"raw": ""}

        def handle2(lines):
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
                if payload.get("type") == "text":
                    evbuf["raw"] += payload.get("content", "")

        BACKEND.run_job(self.session, start, poll, handle2, total_timeout=self.TOTAL_TIMEOUT)
        import re as _re
        text = _re.sub(r"<think>[\s\S]*?</think>", "", evbuf["raw"]).replace("\x00", "")
        if text:
            yield text, None


ADAPTERS = {a.id: a for a in (QwenAdapter(), MimoAdapter())}


# ============================================================
# 层 3：OpenAI 壳
# ============================================================

def flatten_messages(messages):
    """多轮对话拍平成单条 user prompt（网页版按单条文本提交）。"""
    if len(messages) == 1 and messages[0].get("role") == "user":
        c = messages[0].get("content", "")
        if isinstance(c, str):
            return c
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        tag = {"system": "系统指令", "user": "用户", "assistant": "助手"}.get(role, role)
        parts.append("%s：%s" % (tag, content))
    return "\n\n".join(parts)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
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
                st = BACKEND.eval(ad.session, "JSON.stringify({url:location.href})")
                states[cid] = {"page_ready": ad.origin_check in str(st.get("url", "")),
                               "note": ad.note}
            return self._json(200, {"status": "ok", "adapters": states,
                                    "arch": "v2 layered (backend/adapters/shell)"})
        if self.path == "/v1/models":
            data = [{"id": "%s/%s" % (cid, m), "object": "model", "owned_by": cid}
                    for cid, ad in ADAPTERS.items() for m in ad.models]
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
        ad = ADAPTERS.get(cid)
        if ad is None:
            return self._json(400, {"error": "未知 adapter：%s" % cid})
        model = model or ad.default_model
        stream = bool(req.get("stream"))
        messages = req.get("messages") or []
        if not messages:
            return self._json(400, {"error": "messages 为空"})
        prompt = flatten_messages(messages)
        comp_id = "chatcmpl-w2a-" + uuid.uuid4().hex[:10]
        created = int(time.time())

        lock = BACKEND._lock(ad.session)
        if not lock.acquire(timeout=30):
            return self._json(429, {"error": "浏览器桥忙（单飞行并发），请稍后"})
        try:
            if not BACKEND.ensure_page(ad.session, ad.page, ad.origin_check):
                return self._json(502, {"error": "浏览器桥未就绪（Chrome/opencli/登录态）"})

            def delta_iter():
                for delta, usage in ad.chat_stream(model, prompt):
                    yield delta, usage

            if not stream:
                chunks, usage = [], None
                for delta, u in delta_iter():
                    if delta:
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
            for delta, u in delta_iter():
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
            lock.release()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    srv = Server(("127.0.0.1", PORT), Handler)
    print("web2api v2（分层架构）:%d 就绪 —— adapters: %s" % (PORT, ", ".join(ADAPTERS)), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
