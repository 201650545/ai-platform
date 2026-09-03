#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三端同步编排：GitHub ↔ 本地 ↔ 飞书

方向：
  GitHub → 本地   git pull --rebase（只快进/重放，绝不 force；冲突自动中止待人工）
  本地 → GitHub   先敏感扫描 → git add -A + commit → push
  飞书 → 本地     运行 feishu_exports 配置的导出命令（缺环境变量则跳过）

用法：
  python sync_all.py                 # 全量：pull + push + feishu
  python sync_all.py --pull          # 仅 GitHub → 本地
  python sync_all.py --push          # 仅 本地 → GitHub（含敏感扫描）
  python sync_all.py --feishu        # 仅 飞书 → 本地
  python sync_all.py --dry-run       # 预览，不实际执行
  python sync_all.py --repo <name>   # 只处理指定仓库/导出（可多次）
  python sync_all.py --no-log        # 不写同步日志
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "sync_config.json")
LOG_PATH = os.path.join(BASE_DIR, "sync_log.md")

GIT = "git"


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run(cmd, cwd=None, env=None):
    """执行命令，返回 (returncode, stdout, stderr)。"""
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600, env=e)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"命令不存在: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"超时: {' '.join(cmd)}"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def append_log(entries):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(e + "\n")


def secret_scan(repo, patterns):
    """对工作区文本文件做敏感扫描。命中返回 [(file, pattern)]。"""
    code, out, _ = run([GIT, "status", "--porcelain", "-z"], cwd=repo["path"])
    if code != 0:
        return []
    hits = []
    for raw in out.split("\0"):
        if not raw:
            continue
        path = raw[3:] if len(raw) > 3 else raw
        path = path.strip('"')
        if not path:
            continue
        full = os.path.join(repo["path"], path)
        if not os.path.isfile(full):
            continue
        if not path.lower().endswith((".json", ".md", ".txt", ".yaml", ".yml",
                                      ".py", ".js", ".ts", ".html", ".env", ".toml")):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        for pat in patterns:
            if re.search(pat, content):
                hits.append((path, pat))
                break
    return hits


def sync_repo(repo, patterns, dry, do_pull, do_push):
    """单仓库三端同步：本地改动→commit → pull --rebase → push。"""
    name = repo["name"]
    out = []

    code, status, _ = run([GIT, "status", "--porcelain"], cwd=repo["path"])
    if code != 0:
        return [f"- {name}: [fail] git status 失败"]
    has_local = bool(status.strip())

    # ---- 1. 本地改动 → commit（含敏感扫描）----
    if has_local and do_push:
        hits = secret_scan(repo, patterns)
        if hits:
            files = ", ".join(h for h, _ in hits[:5])
            return [f"- {name}: [blocked] 敏感扫描命中 {len(hits)} 处（如 {files}），跳过提交"]
        if dry:
            out.append(f"- {name}: [dry] 将提交 {len(status.splitlines())} 个文件")
        else:
            if run([GIT, "add", "-A"], cwd=repo["path"])[0] != 0:
                return [f"- {name}: [fail] git add 失败"]
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
            code, _, err = run([GIT, "commit", "-m", f"sync(三端): 本地→GitHub 自动同步 {stamp}"],
                               cwd=repo["path"])
            if code != 0:
                return [f"- {name}: [fail] commit 失败: {(err or '')[:300]}"]
            out.append(f"- {name}: [ok] 已提交本地改动")
    elif has_local and not do_push and do_pull:
        out.append(f"- {name}: [warn] 有未提交改动，pull 前请先 --push")

    # ---- 2. GitHub → 本地（pull --rebase）----
    if do_pull:
        if dry:
            out.append(f"- {name}: [dry] 将 pull --rebase")
        else:
            code, o, e = run([GIT, "pull", "--rebase"], cwd=repo["path"],
                             env={"GIT_EDITOR": "true"})
            if code != 0:
                run([GIT, "rebase", "--abort"], cwd=repo["path"])
                out.append(f"- {name}: [fail] pull 冲突，已中止 rebase（{(e or o)[:200]}）")
            else:
                last = [ln for ln in o.splitlines() if ln.strip()]
                out.append(f"- {name}: [ok] pull 完成" + (f"（{last[-1]}）" if last else ""))

    # ---- 3. 本地 → GitHub（push）----
    if do_push:
        if dry:
            out.append(f"- {name}: [dry] 将 push")
        else:
            code, o, e = run([GIT, "push"], cwd=repo["path"])
            if code != 0:
                out.append(f"- {name}: [fail] push 失败: {(e or o)[:200]}")
            else:
                out.append(f"- {name}: [ok] 已推送")

    return out


def run_feishu_export(exp, dry):
    missing = [e for e in exp.get("env", []) if not os.environ.get(e)]
    if missing:
        return "skip", f"缺环境变量: {', '.join(missing)}（CI 已托管，可跳过）"
    if dry:
        return "dry", "（dry-run 不执行）"
    code, out, err = run(exp["cmd"], cwd=exp.get("cwd"))
    if code == 0:
        last = [ln for ln in out.splitlines() if ln.strip()]
        return "ok", last[-1] if last else "导出完成"
    return "fail", (err or out)[:300]


def main():
    ap = argparse.ArgumentParser(description="三端同步：GitHub ↔ 本地 ↔ 飞书")
    ap.add_argument("--pull", action="store_true", help="仅 GitHub → 本地")
    ap.add_argument("--push", action="store_true", help="仅 本地 → GitHub")
    ap.add_argument("--feishu", action="store_true", help="仅 飞书 → 本地")
    ap.add_argument("--dry-run", action="store_true", help="预览，不实际执行")
    ap.add_argument("--repo", action="append", default=[], help="只处理指定名称（可多次）")
    ap.add_argument("--no-log", action="store_true", help="不写同步日志")
    args = ap.parse_args()

    cfg = load_config()
    patterns = cfg.get("secret_scan", {}).get("patterns", [])
    only = set(args.repo)

    do_pull = args.pull or not (args.push or args.feishu)
    do_push = args.push or not (args.pull or args.feishu)
    do_feishu = args.feishu or not (args.pull or args.push)

    lines = [f"## {now_str()} 三端同步"]
    results = []

    for repo in cfg.get("repos", []):
        if not repo.get("enabled"):
            continue
        if only and repo["name"] not in only:
            continue
        results.extend(sync_repo(repo, patterns, args.dry_run, do_pull, do_push))

    if do_feishu:
        for exp in cfg.get("feishu_exports", []):
            if not exp.get("enabled"):
                continue
            if only and exp["name"] not in only:
                continue
            st, msg = run_feishu_export(exp, args.dry_run)
            results.append(f"- feishu {exp['name']}: [{st}] {msg}")

    if not results:
        results.append("- 无匹配的同步项（检查 --repo 名称或 enabled）")

    lines.extend(results)
    print("\n".join(lines))

    if not args.no_log:
        append_log(lines + [""])


if __name__ == "__main__":
    main()
