#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开数据桥失败通知（GPT Extended 审查建议 #9）

只发 run_id / failed_stage / error_code，绝不发原始异常 body 或敏感字段。
BRIDGE_ALERT_WEBHOOK 未配置时静默跳过（不阻塞主流程）。
"""
import json
import os
import urllib.request


def main():
    webhook = os.environ.get("BRIDGE_ALERT_WEBHOOK", "").strip()
    if not webhook:
        print("缺少 BRIDGE_ALERT_WEBHOOK，跳过通知（不影响主流程）")
        return

    payload = {
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "failed_stage": os.environ.get("FAILED_STAGE", "unknown"),
        "error_code": "BRIDGE_EXPORT_FAILED",
        "text": f"AI 资源公开数据桥导出失败（{os.environ.get('GITHUB_REPOSITORY', '')} run #{os.environ.get('GITHUB_RUN_ID', '')}）",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=data,
        headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"通知已发送: HTTP {resp.status}")
    except Exception as e:
        print(f"通知发送失败（不阻塞主流程）: {type(e).__name__}")


if __name__ == "__main__":
    main()
