#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_id 变更检测（GPT Extended 审查建议 #6）

比较本次产物与线上 index.json 的 build_id（内容哈希，不含 generated_at）。
build_id 一致 → 数据没变化，输出 changed=false，CI 跳过部署；
build_id 不同 / 无线上基线 / --force → changed=true，CI 部署。

用法:
  python exporter/check_changed.py            # 正常比较
  python exporter/check_changed.py --force    # 强制标记为「已变化」（workflow_dispatch 手动触发）
"""
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_INDEX = REPO_ROOT / "public" / "index.json"
ONLINE_INDEX = "https://201650545.github.io/ai-resource-hub/index.json"


def main():
    force = "--force" in sys.argv
    local = json.loads(LOCAL_INDEX.read_text(encoding="utf-8"))
    local_build = local.get("build_id")

    online_build = None
    try:
        with urllib.request.urlopen(ONLINE_INDEX, timeout=30) as resp:
            online_build = json.loads(resp.read().decode("utf-8")).get("build_id")
    except Exception as e:
        # 线上基线不可达：fail-open 到「需部署」，保证不静默停更
        print(f"警告: 无法读取线上基线（{type(e).__name__}），按需部署处理", file=sys.stderr)

    changed = force or (local_build != online_build)
    print(f"changed={'true' if changed else 'false'}")
    if local_build:
        print(f"build_id={local_build}")
    if not online_build:
        print("线上无 build_id 基线 → 本次部署")
    elif local_build != online_build and not force:
        print("build_id 变化 → 需部署")
    elif force:
        print("--force 强制 → 需部署")
    else:
        print("build_id 一致 → 跳过部署")


if __name__ == "__main__":
    main()
