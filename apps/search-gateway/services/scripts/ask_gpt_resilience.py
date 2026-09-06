#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ask_gpt_resilience.py
====================
通过 `opencli browser gpt` 桥接，向 GPT 镜像站注入 RFC v2 评审提示词，
等待 GPT Extended 思考后：截图 + 抓取回复文本落盘。

镜像站已知问题（用户实测）：
  - URL 会跳到 /chat/... 但 body 仍是"账号选择页"（Vue SPA 路由触发了 hashchange，
    但水合未发生 → 页面没有可交互 textarea/输入框）。
  - 因此除"找原生输入框"外，还必须提供"绕过水合、直接 POST 站点 API"的策略。

用法：
  python ask_gpt_resilience.py                 # 完整流程：RFC->开站->S0..S4->注入->等待->截图->抓回复
  python ask_gpt_resilience.py --only=S0
  python ask_gpt_resilience.py --post-only     # 跳过定位，直接按 API_ENDPOINTS 逐个 POST
  python ask_gpt_resilience.py --no-answer     # 注入后不等回复不抓回复（只到截图）
  python ask_gpt_resilience.py --dry-run       # 只 fetch RFC + 打 prompt，不碰浏览器
"""
import os
import sys
import json
import time
import subprocess
import urllib.request

SESSION = "gpt"
START_URL = "https://vip-09.67673.live/"
FALLBACK_URL = "https://ai.wendabao-f.net/?utm_source=hidden-ncn-"   # 主站重定向目标
RFC_URL = (
    "https://raw.githubusercontent.com/201650545/ai-hub-memory/master/"
    "projects/ai-resources/plans/plan-fast-chain-resilience-v2-20260903.md"
)
LOG_DIR = r"D:\项目\logs"
SHOT = os.path.join(LOG_DIR, "gpt_rfc_reply_20260903.png")
REPLY = os.path.join(LOG_DIR, "gpt_rfc_reply_20260903.md")
PROMPT_LOG = os.path.join(LOG_DIR, "gpt_rfc_prompt_20260903.md")

# 候选文本输入框的 CSS（按序尝试）
INPUT_CSS = [
    "textarea",
    "[contenteditable='true']",
    "[contenteditable='TRUE']",
    "textarea[data-lexical-editor]",
    ".chat-input textarea",
    "input[type='text']",
]
# 候选发送按钮（按序）
SEND_CSS = [
    "button[data-testid='send-button']",
    "button.SendButton",
    "button[title='Send']",
    "button[aria-label*='Send']",
    "button[type='submit']",
]
# 策略 (c)/(e)：在页内 fetch 的候选后端地址（需按镜像站实际端点调整）
API_ENDPOINTS = [
    "/api/v1/chat/send",
    "/api/chat",
    "/api/openai/v1/chat/completions",
    "/api/gpt/chat",
]
# 卡片文案（策略 (b)/(d)）
CARD_NAMES = ["ChatGPT", "GPT", "DeepSeek", "Claude", "Gemini", "Grok"]

BASE_PROMPT = """你是一个 AI 网关架构师。请评审下面这个 fast 链抗脆弱性 RFC，重点给 3 个建议：
1. A+B 组合（v2 8 渠道 + sensetime 首位）是否合理？还有更便宜的 fallback 候选？
2. capability 误标如何自动化检测？渠道加进来时自动跑 3 个标准测试
3. OR 4 key 池的弱 provider 限流是否有更聪明的 key 调度？

【完整 RFC 内容】
{rfc}
"""


# ---------------------------------------------------------------- env helpers
def fetch_rfc():
    req = urllib.request.Request(RFC_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def sh(args, timeout=120):
    base = ["opencli", "browser", SESSION] + args
    try:
        r = subprocess.run(
            base, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "timeout"}
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        return {"ok": False, "err": (r.stderr or out or "")[:400]}
    try:
        return {"ok": True, "data": json.loads(out)}
    except Exception:
        return {"ok": True, "raw": out}


class Gpt:
    def open(self, url):        return sh(["open", url])
    def wait_time(self, sec):   return sh(["wait", "time", str(sec), "--timeout", str(int(sec * 1000) + 5000)])
    def wait_sel(self, css):    return sh(["wait", "selector", css, "--timeout", "15000"])
    def state(self):            return sh(["state"])
    def find(self, **kw):       return sh(["find"] + [f"--{k}={v}" for k, v in kw.items()])
    def eval(self, js):         return sh(["eval", js])
    def click(self, target, **kw):
        args = ["click"]
        if target:
            args.append(target)
        args += [f"--{k}={v}" for k, v in kw.items()]
        return sh(args)
    def fill(self, target, text, **kw):
        args = ["fill", target, text] + [f"--{k}={v}" for k, v in kw.items()]
        return sh(args, timeout=120)
    def shot(self, path):       return sh(["screenshot", path])
    def extract(self, **kw):
        args = ["extract"] + [f"--{k}={v}" for k, v in kw.items()]
        return sh(args)


# ---------------------------------------------------------------- strategies
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def s0_native_input(api, prompt):
    """S0(a): 找原生 textarea / contenteditable，注入提示词 + 发送。"""
    found = None
    for css in INPUT_CSS:
        r = api.find(css=css, limit=5)
        m = (r.get("data") or {}).get("matches_n", 0) if r.get("ok") else 0
        log(f"S0 probe {css} -> matches={m}")
        if m and r.get("ok"):
            found = css
            break
    if not found:
        r = api.find(role="textbox", limit=5)
        n = (r.get("data") or {}).get("matches_n", 0) if r.get("ok") else 0
        if n:
            found = "[role='textbox']"
    if not found:
        return False
    log(f"S0 fill into {found}")
    r = api.fill(found, prompt, nth=0)
    if not (r.get("ok") and (r.get("data") or {}).get("verified")):
        log(f"S0 fill result: {r}")
    sent = False
    for css in SEND_CSS:
        rr = api.click(css)
        if rr.get("ok") and (rr.get("data") or {}).get("clicked"):
            sent = True
            log(f"S0 sent via {css}")
            break
    if not sent:
        log("S0 no send button; trying Enter key")
        sh(["keys", "Enter"])
        sent = True
    return True


def s_find_card(api):
    """S1(b): 点 ChatGPT/chat 卡片，尝试触发路由。"""
    for name in CARD_NAMES:
        r = api.find(text=name, limit=5)
        n = (r.get("data") or {}).get("matches_n", 0) if r.get("ok") else 0
        if n:
            log(f"S1 found card text={name} matches={n}; clicking")
            api.click(None, text=name, nth=0)
            api.wait_time(3)
            return True
    return False


def s2_deepseek_card(api):
    """S2(d): 直接切 DeepSeek 卡片，再回来找输入框。"""
    r = api.find(text="DeepSeek", limit=5)
    if r.get("ok") and (r.get("data") or {}).get("matches_n"):
        api.click(None, text="DeepSeek", nth=0)
        api.wait_time(3)
        return True
    return False


def s3_probe_page(api):
    """S3: eval 深度探测页面水合状态 / DOM 结构 / 脚本暴露的 API，供排查。"""
    js = (
        "(function(){var t=document.querySelectorAll('textarea').length,"
        "ce=document.querySelectorAll('[contenteditable=\"true\"]').length,"
        "inp=document.querySelectorAll('input').length,"
        "url=location.href,title=document.title,"
        "links=Array.from(document.querySelectorAll('a')).slice(0,30).map(a=>a.href),"
        "winKeys=Object.keys(window).filter(k=>/__|APP|api|vue|pinia/i.test(k)).slice(0,40),"
        "res=(performance.getEntriesByType&&performance.getEntriesByType('resource')||[])"
        ".slice(-40).map(e=>e.name);"
        "return JSON.stringify({url,title,textarea:t,contenteditable:ce,input:inp,links,winKeys,res});"
        "})()"
    )
    r = api.eval(js)
    log(f"S3 probe -> {r.get('raw') or r}")
    return r.get("ok")


def s4_direct_post(api, prompt):
    """S4(c/e): 绕过水合，在页内直接 fetch 候选后端端点提交。

    提示词 base64 后经 atob 还原进 body，避免提示词内的引号/换行撑破注入的 JS 字符串。
    """
    import base64
    b64 = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    for ep in API_ENDPOINTS:
        out = api.eval(
            "fetch('%s',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:atob('%s')}).then(r=>r.text()).then(t=>'OK:'+t.slice(0,200))"
            ".catch(e=>'ERR:'+e)" % (ep, b64)
        )
        log(f"S4 fetch {ep} -> {out.get('raw') or out}")
        s = out.get("raw") or ""
        if s.startswith("OK"):
            return True
    return False


# ------------------------------------------------------------------- reply
def grab_reply(api):
    """等 GPT Extended 思考后：截图 + 抽取回复文本。"""
    mark = time.time()
    last = 0
    while time.time() - mark < 40:
        time.sleep(8)
        js = (
            "JSON.stringify({len:(document.querySelector('.markdown, .prose, .message')"
            ".innerText||'').length})"
        )
        r = api.eval(js)
        try:
            obj = json.loads(r.get("raw") or r.get("data") or "{}")
        except Exception:
            obj = {}
        if obj.get("len", 0) > last:
            last = obj.get("len", 0)
            log(f"reply growing: len={last}")
            if last > 0:
                time.sleep(6)   # 再等一段，让它写完
                break
    api.shot(SHOT)
    log(f"screenshot -> {SHOT}")
    r = api.extract(chunk_size=12000)
    text = r.get("raw") or json.dumps(r.get("data"))
    with open(REPLY, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"reply md -> {REPLY}")
    return text


def run(prompt, only, no_answer):
    api = Gpt()
    api.open(START_URL)
    api.wait_time(5)
    log(f"opened {START_URL}")

    if only:
        strategies = [only]
    else:
        strategies = ["s0_native_input", "s_find_card", "s2_deepseek_card", "s3_probe_page", "s4_direct_post"]

    reached = False
    for name in strategies:
        log(f"== strategy {name} ==")
        try:
            fn = globals()[name]
            ok = fn(api, prompt) if name in ("s0_native_input", "s4_direct_post") else fn(api)
        except Exception as e:
            log(f"{name} raised: {e}")
            ok = False
        if ok and name in ("s0_native_input", "s4_direct_post"):
            reached = True
            log(f"prompt submitted via {name}; waiting ~25s for GPT Extended thinking")
            time.sleep(25)
            break

    if not reached:
        log("WARNING: 未能注入提示词；当前停留在对页面的只读探测阶段")

    if not no_answer and reached:
        grab_reply(api)
    else:
        api.shot(SHOT)
        log(f"shot-only -> {SHOT}")


def main():
    args = sys.argv[1:]
    only = None
    for a in args:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    post_only = "--post-only" in args
    no_answer = "--no-answer" in args
    dry = "--dry-run" in args

    log(f"fetching RFC v2: {RFC_URL}")
    rfc = fetch_rfc()
    prompt = BASE_PROMPT.format(rfc=rfc)
    with open(PROMPT_LOG, "w", encoding="utf-8") as f:
        f.write(prompt)
    log(f"prompt (RFC {len(rfc)}B / total {len(prompt)}B) -> {PROMPT_LOG}")

    if dry:
        log("dry-run: stop before browser.")
        return

    if post_only:
        api = Gpt()
        api.open(START_URL)
        api.wait_time(5)
        api.open(FALLBACK_URL)
        api.wait_time(5)
        s4_direct_post(api, prompt)
        time.sleep(25)
        grab_reply(api)
        return

    run(prompt, only, no_answer)


if __name__ == "__main__":
    main()