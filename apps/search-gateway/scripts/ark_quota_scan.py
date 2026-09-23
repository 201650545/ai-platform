# -*- coding: utf-8 -*-
"""方舟（火山方舟）免费额度每日巡检（2026-09-22，郭老师指令「ark 模型每天也要盘点」）。

做法：opencli 驱动日常 Chrome（须已登录 ark.volcengine.com 控制台），打开
「开通管理」页，逐标签页/逐页解析「模型用量上限（剩X/共Y）」行，产出：

1. data/ark_quota_snapshot.json —— 全量额度快照（人可读）
2. data/quota_guard.json 回写 —— 同名模型的 remaining 刷新（警戒闸门热加载即生效）
3. data/渠道警报.log —— ①任一模型剩余比例 ≤20%（警戒线触发）②巡检失败（浏览器
   未就绪/未登录/页面结构变化）时追加告警，与 zscc 警报同一出口

模型名归一：控制台名 lower + 「正式版」→"-formal"（如 DeepSeek-V4-Flash正式版
→ deepseek-v4-flash-formal），与 quota_guard.json 的 models 键一致。
写文件一律无 BOM UTF-8（Set-Content 带 BOM 的坑见 CHANGELOG S-20260922-08）。
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(r"D:\项目\ai-hub\search_gateway")
DATA = BASE / "data"
ALERT_LOG = DATA / "渠道警报.log"
SNAPSHOT = DATA / "ark_quota_snapshot.json"
GUARD = DATA / "quota_guard.json"
OPENCLI = r"C:\Users\郭永涛\AppData\Roaming\npm\opencli.cmd"
CONSOLE_URL = ("https://ark.volcengine.com/region:cn-beijing/openManagement"
               "?LLM=%7B%7D&advancedActiveKey=model")
WARN_PCT = 20.0

PROVIDERS = ("字节跳动", "DeepSeek", "智谱AI", "月之暗面", "MiniMax", "阿里云",
             "百度", "阶跃星辰", "零一万物", "讯飞", "腾讯",
             "影眸科技（上海）有限公司", "北京数美万物科技有限公司")
NOISE = re.compile(r"tokens$|张$|RPM|TPM|元/千|元/张|开通|模型上新|升级|延迟|^--$|全面开放|QPS|IPM|并发")


def ocli(*args, timeout=90):
    # CREATE_NO_WINDOW：禁止弹 system32 cmd 窗口（2026-09-23 郭老师指令）
    r = subprocess.run([OPENCLI, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=0x08000000)
    return r.stdout or ""


def ocli_eval(js, timeout=90):
    """opencli browser main eval —— 对象返回值输出 JSON；字符串返回值输出原文。"""
    out = ocli("browser", "main", "eval", js, timeout=timeout).strip()
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        # npm 包装器告警行混入时，对象返回值截取 {..}；纯字符串返回值原样给出
        i, j = out.find("{"), out.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(out[i:j + 1])
            except Exception:  # noqa: BLE001
                pass
        return out


def alert(msg):
    line = "[%s] [方舟额度巡检] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def parse_quota_rows(text):
    """从页面 innerText 解析 剩X/共Y(tokens|张) 行 → [(模型名, 剩, 总, 单位)]。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    rows = []
    for i, l in enumerate(lines):
        m = re.match(r"^剩([\d,]+)\s*/共([\d,]+) (tokens|张)$", l)
        if not m:
            continue
        rem, tot, unit = m.group(1), m.group(2), m.group(3)
        state = provider = name = ""
        for j in range(i - 1, max(-1, i - 30), -1):
            s = lines[j]
            if not state and s in ("已开通", "未开通"):
                state = s
            if state and not provider and s in PROVIDERS:
                provider = s
            if provider and not name and s != provider and not NOISE.search(s):
                name = s
                break
        if name:
            rows.append((name, int(rem.replace(",", "")), int(tot.replace(",", "")), unit, state))
    seen, out = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return out


def normalize(name):
    return name.strip().lower().replace("正式版", "-formal").replace(" ", "")


def click(page_or_tab):
    """点击页码/标签页：取可见、高度小于 60px 的叶子元素最后一个。"""
    js = ("async () => { const els=[...document.querySelectorAll('li,button,div,span')]"
          ".filter(e=>e.textContent.trim()===%r&&e.offsetParent"
          "&&e.getBoundingClientRect().height>0&&e.getBoundingClientRect().height<60);"
          "if(!els.length) return 'NOT_FOUND'; els[els.length-1].click();"
          "await new Promise(r=>setTimeout(r,1800)); return 'OK'; }" % page_or_tab)
    return ocli_eval(js)


def grab_text():
    return ocli_eval("() => document.body.innerText")


def main():
    # 0) 打开控制台页（后台窗口）
    ocli("browser", "main", "open", CONSOLE_URL, "--window", "background")
    time.sleep(6)
    try:
        head = grab_text()
    except Exception as exc:  # noqa: BLE001
        alert("失败：页面打不开（%s）——Chrome 未运行或 opencli 桥未连" % exc)
        return 1
    if "模型用量上限" not in head and "剩" not in head:
        if "登录" in head or "Sign in" in head:
            alert("失败：方舟控制台未登录，额度未盘点——请在日常 Chrome 登录 ark.volcengine.com")
        else:
            alert("失败：页面结构变化，未识别到额度表")
        return 1

    inventory = []  # (归一名, 控制台名, 剩, 总, 单位, 状态)
    # 1) 语言模型（分页）
    click("语言模型")
    time.sleep(2)
    for page in ("1", "2", "3", "4"):
        if click(page) == "NOT_FOUND":
            break
        time.sleep(1)
        for name, rem, tot, unit, state in parse_quota_rows(grab_text()):
            inventory.append((normalize(name), name, rem, tot, unit, state))
    # 2) 视觉模型（含 张 计价，分页）
    click("视觉模型")
    time.sleep(2)
    for page in ("1", "2", "3"):
        if click(page) == "NOT_FOUND":
            break
        time.sleep(1)
        for name, rem, tot, unit, state in parse_quota_rows(grab_text()):
            inventory.append((normalize(name), name, rem, tot, unit, state))
    # 3) 向量模型
    click("向量模型")
    time.sleep(2)
    for name, rem, tot, unit, state in parse_quota_rows(grab_text()):
        inventory.append((normalize(name), name, rem, tot, unit, state))

    if not inventory:
        alert("失败：本次巡检解析到 0 条额度行——页面结构变化，须人工检查")
        return 1

    # 4) 快照落盘（无 BOM）
    now = datetime.now()
    snap = {"checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(inventory),
            "models": [{"key": k, "name": n, "remaining": rem, "total": tot,
                        "unit": u, "state": st,
                        "remaining_pct": round(rem / tot * 100, 1) if tot else None}
                       for k, n, rem, tot, u, st in inventory]}
    with open(SNAPSHOT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    # 5) 回写 quota_guard.json 同名模型的 remaining（无 BOM）
    by_key = {k: (rem, tot, u) for k, n, rem, tot, u, st in inventory}
    guard = json.loads(GUARD.read_text(encoding="utf-8-sig"))
    updated = []
    for model, rec in (guard.get("channels", {}).get("ark", {}).get("models") or {}).items():
        hit = by_key.get(model)
        if not hit:
            continue
        rem, tot, u = hit
        old = rec.get("remaining")
        if rem != old:
            rec["remaining"] = rem
            rec["total"] = tot
            updated.append("%s %s→%s/%s%s" % (model, old, rem, tot, u))
        # aliases 联动：同一模型在网关侧的真实上游名共享同一份剩余额度
        for alias in rec.get("aliases") or []:
            if alias in guard["channels"]["ark"]["models"]:
                guard["channels"]["ark"]["models"][alias]["remaining"] = rem
                guard["channels"]["ark"]["models"][alias]["total"] = tot
    with open(GUARD, "w", encoding="utf-8", newline="\n") as f:
        json.dump(guard, f, ensure_ascii=False, indent=1)

    # 6) 警戒线告警：任一模型 ≤20%
    breaches = ["%s 剩%s/%s%s（%.1f%%）" % (n, rem, tot, u, rem / tot * 100)
                for k, n, rem, tot, u, st in inventory
                if tot and rem / tot * 100 <= WARN_PCT]
    if breaches:
        alert("警戒线触发（剩≤20%%应停用，闸门已自动拦）：%s" % "；".join(breaches))
    print("盘点 %d 个模型，guard 回写 %d 处：%s" % (len(inventory), len(updated),
                                                  "；".join(updated) if updated else "无变化"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
