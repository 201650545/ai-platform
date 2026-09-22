# -*- coding: utf-8 -*-
"""bai（B.AI）每周探监（郭老师 2026-09-21 指示：打入冷宫，每周测一次有没有活动）

计划任务 BaiWelfareCheck 每周一 09:17 跑：
  测限免阵容 5 模型能否免费调用（deepseek-v4-flash/hy3/mimo-v2.5/qwen3.8-flash/glm-5.3-flash）
  任一成功 → data/渠道警报.log 报警（郭老师可接回编排）；全部仍拒付 → 记一行冷宫日志
"""
import json
import os
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
LINEUP = ["deepseek-v4-flash", "hy3", "mimo-v2.5", "qwen3.8-flash", "glm-5.3-flash"]
LOG = os.path.join(DATA, "渠道警报.log")
COLD = os.path.join(DATA, "bai_冷宫日志.log")


def main():
    cd = json.load(open(os.path.join(DATA, "channels.json"), encoding="utf-8"))
    key = cd["keys"]["bai"]
    ok_list = []
    for mid in LINEUP:
        body = json.dumps({"model": mid, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}).encode()
        req = urllib.request.Request("https://api.b.ai/v1/chat/completions", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + key)
        try:
            urllib.request.urlopen(req, timeout=45)
            ok_list.append(mid)
        except Exception as e:  # noqa: BLE001
            print(mid, "FAIL", str(e)[:70])
    line = f"[{NOW}] 探监：{len(LINEUP)-len(ok_list)}/{len(LINEUP)} 仍拒付" + (f" | 恢复可用: {', '.join(ok_list)}" if ok_list else "")
    print(line)
    if ok_list:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{NOW}] 🎉 B.AI 福利回归！可用限免模型：{', '.join(ok_list)} —— 可考虑接回编排\n")
    else:
        with open(COLD, "a", encoding="utf-8") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
