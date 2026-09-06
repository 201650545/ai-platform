# -*- coding: utf-8 -*-
"""content_pool.py - 多 AI 搜索内容聚合交付"""
import json, math, threading, time, datetime
import urllib.request
from pathlib import Path
import engines

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"

# ---- 渠道组合预设（2026-08-30 实测选定：kimi/qianwen 超时、doubao 回答过短，降级）----
DEFAULT_ENGINES = ["metaso", "perplexity", "yuanbao", "grok", "aihot", "hackernews", "rss"]  # 4 路网页 + 3 路资讯（AI/HN/RSS）：信息全面 + 渠道失效时资讯兜底
DEEP_ENGINES = DEFAULT_ENGINES + ["zai"]  # 深度模式
# full = 8 路，调用方显式传 engine_ids 全列表

# ---- aihot 资讯 provider（独立 HTTP，不占浏览器线程）----
AIHOT_API = "https://aihot.virxact.com/api/public/items"
AIHOT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def aihot_items(since_hours=24, take=15):
    """拉 aihot 精选资讯条目（中文 AI 行业）；需带浏览器 UA，否则 403。"""
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "%s?mode=selected&since=%s&take=%d" % (AIHOT_API, since, take)
    req = urllib.request.Request(url, headers={"User-Agent": AIHOT_UA, "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    items = data.get("items") if isinstance(data, dict) else (data or [])
    return items if isinstance(items, list) else []


def aihot_search(_question, since_hours=24, take=15):
    """把 aihot 资讯转成标准 ANSWERED record（source_type=ai_news）。"""
    t0 = time.time()
    try:
        items = aihot_items(since_hours=since_hours, take=take)
        lines, urls = [], []
        for it in items:
            title = str(it.get("title") or it.get("title_en") or "").strip()
            link = str(it.get("url") or "").strip()
            summary = str(it.get("summary") or "").strip()
            source = str(it.get("source") or "").strip()
            if link:
                urls.append(link)
            line = "- " + (title or "(无标题)")
            if summary:
                line += "：" + summary
            if source:
                line += "（来源：" + source + "）"
            lines.append(line)
        if not lines:
            return {"status": "EMPTY", "answer": "", "urls": [], "elapsed": time.time() - t0,
                    "error": "aihot 该时间窗无内容", "source_type": "ai_news"}
        answer = "近 %dh AI 资讯精选（aihot）：\n" % since_hours + "\n".join(lines)
        return {"status": "ANSWERED", "answer": answer, "urls": urls, "elapsed": time.time() - t0,
                "error": "", "source_type": "ai_news"}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "answer": "", "urls": [], "elapsed": time.time() - t0,
                "error": str(e)[:120], "source_type": "ai_news"}


# ---- Hacker News 资讯 provider（hn.algolia.com 公开 API）----
HN_API = "https://hn.algolia.com/api/v1/search_by_date"


def hackernews_items(take=10):
    url = "%s?tags=front_page&hitsPerPage=%d" % (HN_API, take)
    req = urllib.request.Request(url, headers={"User-Agent": AIHOT_UA, "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    return data.get("hits") or []


def hackernews_search(_question, take=10):
    """Hacker News 头条 → 标准 record（source_type=hacker_news）。"""
    t0 = time.time()
    try:
        items = hackernews_items(take)
        lines, urls = [], []
        for it in items:
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            url = str(it.get("url") or "").strip() or "https://news.ycombinator.com/item?id=%s" % (it.get("objectID") or "")
            urls.append(url)
            lines.append("- %s（%d 分）" % (title, it.get("points") or 0))
        if not lines:
            return {"status": "EMPTY", "answer": "", "urls": [], "elapsed": time.time() - t0,
                    "error": "Hacker News 暂无内容", "source_type": "hacker_news"}
        return {"status": "ANSWERED", "answer": "Hacker News 头条（国际开发者/技术）：\n" + "\n".join(lines),
                "urls": urls, "elapsed": time.time() - t0, "error": "", "source_type": "hacker_news"}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "answer": "", "urls": [], "elapsed": time.time() - t0,
                "error": str(e)[:120], "source_type": "hacker_news"}


# ---- RSS 资讯 provider（python 直接抓 mfeo feeds 子集，无需 Go）----
RSS_FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("TLDR AI", "https://tldr.tech/api/rss/ai"),
    ("Import AI", "https://importai.substack.com/feed"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
]


def rss_items(feeds=None, take=8):
    import xml.etree.ElementTree as ET
    items = []
    for name, url in (feeds or RSS_FEEDS):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AIHOT_UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            root = ET.fromstring(raw)
            for it in root.iter("item"):
                t = (it.findtext("title") or "").strip()
                l = (it.findtext("link") or "").strip()
                if t and l:
                    items.append((t, l, name))
                if len(items) >= take:
                    break
        except Exception:  # noqa: BLE001
            continue
        if len(items) >= take:
            break
    return items


def rss_search(_question, take=8):
    """科技/安全 RSS 摘要 → 标准 record（source_type=rss_news）。"""
    t0 = time.time()
    try:
        items = rss_items(take=take)
        lines, urls = [], []
        for t, l, name in items:
            urls.append(l)
            lines.append("- %s（来源：%s）" % (t, name))
        if not lines:
            return {"status": "EMPTY", "answer": "", "urls": [], "elapsed": time.time() - t0,
                    "error": "RSS 暂无内容", "source_type": "rss_news"}
        return {"status": "ANSWERED", "answer": "科技/安全 RSS 摘要：\n" + "\n".join(lines),
                "urls": urls, "elapsed": time.time() - t0, "error": "", "source_type": "rss_news"}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "answer": "", "urls": [], "elapsed": time.time() - t0,
                "error": str(e)[:120], "source_type": "rss_news"}


def _quorum(n):
    """按渠道数给 quorum：4→3，5→4，6-8→ceil(n*0.6)。"""
    if n <= 4:
        return min(n, 3)
    if n == 5:
        return 4
    return max(3, int(math.ceil(n * 0.6)))


def _classify(result):
    """归一到 ANSWERED/EMPTY/ERROR/TIMEOUT；正文≥80 字才算 ANSWERED。"""
    status = result.get("status")
    answer = (result.get("answer") or "").strip()
    if status == "ok" and len(answer) >= 80:
        return "ANSWERED"
    if status == "ok":
        return "EMPTY"
    if status == "timeout":
        return "TIMEOUT"
    return "ERROR"

def _run_id():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def _esc(s):
    if not s: return ""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace(chr(34),"&quot;")

def _md(text):
    if not text: return ""
    out=[]; in_code=False
    for line in str(text).splitlines():
        ls=line.strip()
        if ls.startswith("```"): in_code=not in_code; continue
        if in_code: out.append("<pre>"+_esc(line)+"</pre>")
        elif ls.startswith("## "): out.append("<h3>"+_esc(ls[3:])+"</h3>")
        elif ls.startswith("### "): out.append("<h4>"+_esc(ls[4:])+"</h4>")
        elif ls.startswith("- "): out.append("<li>"+_esc(ls[2:])+"</li>")
        elif ls=="": out.append("")
        else: out.append("<p>"+_esc(line)+"</p>")
    return "\n".join(out)
CSS = "".join([
    "body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','PingFang SC','Microsoft YaHei',sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.7;margin:0;padding:32px 16px}",
    ".wrap{max-width:860px;margin:0 auto}",
    "header{background:#fff;border:1px solid #d2d2d7;border-radius:18px;padding:28px 32px;margin-bottom:20px;box-shadow:0 1px 2px rgba(0,0,0,.04)}",
    "h1{font-size:28px;font-weight:700;letter-spacing:-.02em;margin:0 0 8px}",
    ".q{color:#6e6e73;font-size:16px}",
    ".meta-sm{color:#86868b;font-size:12px;margin-top:6px}",
    ".card{background:#fff;border:1px solid #d2d2d7;border-radius:18px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}",
    ".card h2{font-size:18px;font-weight:600;margin:0 0 12px;padding-bottom:10px;border-bottom:1px solid #e8e8ed;color:#1d1d1f}",
    ".meta{font-size:12px;color:#86868b;font-weight:normal;margin-left:8px}",
    ".answer p{margin:8px 0;font-size:15px}.answer h3{margin:14px 0 6px;font-size:16px}.answer pre{background:#f5f5f7;border:1px solid #e8e8ed;border-radius:10px;padding:12px;overflow-x:auto;font-size:13px}.answer li{margin-left:20px;font-size:15px}",
    "details.think{margin:10px 0;padding:12px 16px;background:#f5f5f7;border-radius:12px}",
    "details.think summary{cursor:pointer;color:#6e6e73;font-size:13px;font-weight:500}",
    ".toolbar{position:fixed;right:20px;bottom:20px;display:flex;gap:8px}",
    ".toolbar button{background:#0071e3;color:#fff;border:none;border-radius:999px;padding:9px 18px;cursor:pointer;font-size:13px;font-weight:500;transition:opacity .15s}",
    ".toolbar button:hover{opacity:.85}",
    "footer{color:#86868b;font-size:12px;text-align:center;margin:28px 0;border-top:1px solid #e8e8ed;padding-top:20px}",
])

def llm_summarize(question, merged):
    """调网关 LLM 转发 API，把各引擎内容整理成一段综合结论（2026-08-26）。
    用本机 :3100 的 /v1/chat/completions（DeepSeek 等渠道）；失败返回空串（不阻塞报告）。
    #49：ref_links 来源编号参入 prompt，输出末尾列来源编号对应 ref_links。"""
    ok = [r for r in merged if r.get("status") == "ANSWERED" and (r.get("answer") or r.get("thinking"))]
    if not ok:
        return ""
    parts = []
    ref_map = {}  # 来源编号映射
    ref_idx = 1
    for r in ok:
        txt = (r.get("answer") or r.get("thinking") or "")[:1500]
        name = r.get("name") or r.get("provider") or r.get("id", "?")
        parts.append("【" + name + "】\n" + txt)
        # 收集该引擎的引用链接
        links = r.get("ref_links") or []
        if links:
            ref_map[name] = []
            for link in links:
                ref_map[name].append(f"[{ref_idx}] {link.get('title','')}: {link.get('url','')}")
                ref_idx += 1
    contents = "\n\n".join(parts)
    ref_section = ""
    if ref_map:
        lines = []
        for eng_name, refs in ref_map.items():
            lines.append(eng_name + " 来源：")
            lines.extend("  " + r for r in refs)
        ref_section = "\n\n引用来源：\n" + "\n".join(lines)
    prompt = ("以下是多个 AI 搜索引擎对同一个问题的回答。请综合它们，输出一段有条理的中文总结"
              "（先给结论，再列各来源要点，标注共识与差异；300 字以内，末尾列来源编号对应引用）：\n\n问题：" + question + "\n\n" + contents + ref_section)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:3100/v1/chat/completions",  # 走 API 转发网关(OpenAI 兼容)。:3000 是搜索网关只认 yuanbao-search，会拒 deepseek-v4-flash
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    except Exception as e:
        print("[content_pool] LLM summarize failed: " + str(e)[:200])
        return ""


def _build_report(run_id, question, merged, summary=None):
    cards=[]
    if summary:
        cards.append("<section class=card style='border-left:3px solid #0071e3'><h2>综合整理</h2><div class=answer>"+_md(summary)+"</div></section>")
    for r in merged:
        if r.get("status") in ("ANSWERED", "ok"):
            body=_md(r.get("answer") or r.get("thinking") or "") or "<p style=color:#999>（无有效内容）</p>"
            think=""
            if r.get("thinking"):
                think="<details class=think><summary>思考过程</summary>"+_md(r["thinking"])+"</details>"
            name=_esc(r.get("name") or r.get("provider") or "")
            icon=_esc(r.get("icon") or "")
            el=round(r.get("elapsed") or 0,1)
            rf=r.get("refs") or 0
            cards.append("<section class=card><h2>"+icon+" "+name+" <span class=meta>"+str(el)+"s · 引用 "+str(rf)+"</span></h2>"+think+"<div class=answer>"+body+"</div></section>")
        else:
            name=_esc(r.get("name") or r.get("provider") or "")
            icon=_esc(r.get("icon") or "")
            st=r.get("status") or "error"
            err=_esc(r.get("error") or "")
            cards.append("<section class=card style=opacity:.6><h2>"+icon+" "+name+" <span class=meta>"+st+"</span></h2><div class=answer><p style=color:#b00>未返回内容："+err+"</p></div></section>")
    cards_html="\n".join(cards)
    q=_esc(question); rid=_esc(run_id); n=len(merged)
    return "".join([
        "<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content=width=device-width,initial-scale=1>",
        "<title>AI 搜索聚合报告 · "+rid+"</title><style>"+CSS+"</style></head><body><div class=wrap>",
        "<header><h1>AI 搜索聚合报告</h1><div class=q>问题："+q+"</div>",
        "<div class=q style=margin-top:6px;font-size:12px;color:#999>"+rid+" · "+str(n)+" 个引擎返回</div></header>",
        cards_html,
        "<footer>由 content_pool 自动生成</footer></div>",
        "<div class=toolbar><button onclick=window.print()>打印 / PDF</button><button onclick=window.scrollTo(0,0)>返回顶部</button></div>",
        "</body></html>",
    ])
def run_search(question, engine_ids=None):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id=_run_id()
    run_dir=RUNS_DIR/run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir/"question.txt").write_text(question, encoding="utf-8")
    engine_ids = engine_ids or list(DEFAULT_ENGINES)
    n = len(engine_ids)
    quorum = _quorum(n)
    soft = 75 if n <= 4 else 120
    hard = 130
    lock = threading.Lock()
    records = {}
    for eid in engine_ids:
        name = engines.ENGINES.get(eid, {}).get("name", eid)
        icon = engines.ENGINES.get(eid, {}).get("icon", "")
        records[eid] = {"provider": eid, "name": name, "icon": icon, "status": "STARTED",
                        "phase": "running", "thinking": "", "answer": "", "answer_html": "",
                        "refs": 0, "urls": [], "elapsed": 0, "error": "", "source_type": "web_search"}

    _PROVIDERS = {"aihot": aihot_search, "hackernews": hackernews_search, "rss": rss_search}

    def _one(eid):
        if eid in _PROVIDERS:
            res = _PROVIDERS[eid](question)
            status = res.get("status", "ERROR")  # 资讯 provider 已自标 ANSWERED/EMPTY/ERROR，不走 _classify
        else:
            try:
                res = engines.ask_engine(eid, question)
            except Exception as e:  # noqa: BLE001
                res = {"status": "error", "answer": "", "refs": 0, "error": str(e)[:120], "elapsed": 0}
            status = _classify(res)
        urls = res.get("urls") or []
        if not urls and res.get("ref_links"):
            urls = [lk.get("url") for lk in res.get("ref_links", []) if isinstance(lk, dict) and lk.get("url")]
        with lock:
            records[eid] = {
                "provider": eid, "name": records[eid]["name"], "icon": records[eid]["icon"],
                "status": status, "phase": "done",
                "thinking": res.get("thinking", ""), "answer": res.get("answer", ""),
                "answer_html": res.get("answer_html", ""), "refs": res.get("refs", 0),
                "urls": list(dict.fromkeys(urls)), "elapsed": round(res.get("elapsed", 0), 1),
                "error": res.get("error", ""),
                "source_type": res.get("source_type") or "web_search",
            }

    threads = [threading.Thread(target=_one, args=(eid,), daemon=True) for eid in engine_ids]
    for t in threads:
        t.start()

    # quorum + deadline：达 quorum 后最多再等 10s 补尾路；统一 hard 硬截止；不再逐线程 join
    t0 = time.time()
    soft_deadline = t0 + soft
    hard_deadline = t0 + hard
    quorum_met_at = None
    while True:
        with lock:
            answered = sum(1 for r in records.values() if r.get("status") == "ANSWERED")
            all_done = all(r.get("phase") == "done" for r in records.values())
        now = time.time()
        if all_done:
            break  # 所有渠道已到终态（无论是否达 quorum），立即总结，避免空等 hard
        if answered >= quorum:
            if quorum_met_at is None:
                quorum_met_at = now
            if now >= quorum_met_at + 10:
                break  # quorum 已达成：最多再等 10s 补尾路，不拖到 soft
        elif now >= soft_deadline:
            break  # 未达 quorum：soft 到了就用现有结果
        if now >= hard_deadline:
            break
        time.sleep(1)

    with lock:
        for r in records.values():
            if r.get("phase") == "running":
                r["status"] = "TIMEOUT"
                r["phase"] = "done"
                r["error"] = r.get("error") or "等待回答超时"
    merged_list = list(records.values())

    with open(run_dir/"raw.jsonl","a",encoding="utf-8") as f:
        for rec in merged_list: f.write(json.dumps(rec,ensure_ascii=False)+"\n")
    (run_dir/"merged.json").write_text(json.dumps(merged_list,ensure_ascii=False,indent=2),encoding="utf-8")
    summary=llm_summarize(question, merged_list)
    (run_dir/"summary.md").write_text(summary or "（无综合结论）",encoding="utf-8")
    report_path=run_dir/"report.html"
    report_path.write_text(_build_report(run_id, question, merged_list, summary),encoding="utf-8")
    return run_id, str(report_path), merged_list

if __name__=="__main__":
    import sys
    q=" ".join(sys.argv[1:]) or "中国近期的 AI 政策动态"
    rid, rp, recs = run_search(q)
    print("RUN:", rid)
    print("REPORT:", rp)
    for r in recs: print(" ", r["provider"], r["status"], round(r.get("elapsed",0),1))