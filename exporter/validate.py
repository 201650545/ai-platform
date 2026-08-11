#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开数据桥产物语义校验器（GPT Extended 审查建议 #5）

部署前校验 public/ 产物：
  1. 每表 count > 0（防「成功发布空数据」）
  2. primary_key 非空且唯一
  3. 实例「所属能力」引用能力表 capability_id（引用完整性）
  4. 每条记录 keys ⊆ 白名单 + computed（防白名单外字段泄漏）
  5. 枚举字段只取预声明集合（额度状态各档）
  6. 值形状：Bearer/已知密钥前缀/cli_ / 带参 URL / email / 手机号 一律拒绝
  7. 与上一成功版本相比记录数下降 >30% → 阻断（--force 可跳过）

安全边界：
  - 命中只输出 表/字段/序号/原因，绝不输出值本身（与 scanner 同一立场）
  - --force 仅允许跳过「数量突变确认」，绝不能跳过 scanner/schema/0条/引用完整性

用法:
  python exporter/validate.py                        # 校验当前 public/ 产物
  python exporter/validate.py --baseline <index_url> # 拉线上 index.json 做数量突变检测
  python exporter/validate.py --force                # 人工确认后跳过数量突变阻断
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "exporter" / "config.json"
OUTPUT_DIR = REPO_ROOT / "public"
DROP_RATIO_LIMIT = 0.30

# ---- 值形状检测（命中不输出值，只报原因）----
_RE_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}")
_RE_CLI_ID = re.compile(r"(?i)\bcli_[A-Za-z0-9]{8,}\b")
_RE_KNOWN_KEY = re.compile(r"(?i)\b(?:sk-|sk_|ghp_|gho_|github_pat_|xox[bap]-|AKIA)[A-Za-z0-9_\-]{10,}\b")
_RE_URL_QUERY = re.compile(r"[?&][A-Za-z0-9_\-]{2,}=[A-Za-z0-9%_\-\.~+/]{8,}")
_RE_EMAIL = re.compile(r"(?<!\w)[\w.+-]{1,}@[\w-]{1,}\.[\w.-]{2,}(?!\w)")
_RE_PHONE_CN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_table(slug):
    path = OUTPUT_DIR / f"{slug}.json"
    if not path.exists():
        raise RuntimeError(f"缺少产物 {slug}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def quota_bands(cfg):
    """从 config.json 的 fuzz.bands 提取枚举集合（config-driven，不硬编码）。"""
    bands = set()
    for band_cfg in cfg.get("fuzz", {}).get("额度状态", {}).get("bands", []):
        bands.add(band_cfg["name"])
    return bands


def issues_for_table(table_cfg, schema_cfg, records, bands):
    """返回该表全部校验问题。"""
    issues = []
    pk = table_cfg["primary_key"]
    slug = table_cfg["slug"]
    allowed = set(schema_cfg.get("fields") or [])
    allowed |= set(schema_cfg.get("computed") or [])

    # 1) count > 0
    if len(records) == 0:
        issues.append(f"[致命] {slug}: count=0（成功发布空数据）")

    # 2) primary_key 非空且唯一
    seen = {}
    for i, rec in enumerate(records):
        v = rec.get(pk)
        if v in (None, ""):
            issues.append(f"[致命] {slug}: 第{i+1}条 主键 {pk!r} 为空")
        elif v in seen:
            issues.append(f"[致命] {slug}: 主键重复 {pk}={v!r}（第{seen[v]}条与第{i+1}条）")
        else:
            seen[v] = i + 1

    # 4) keys ⊆ 白名单 + computed
    for i, rec in enumerate(records):
        extra = set(rec.keys()) - allowed
        if extra:
            issues.append(f"[致命] {slug}: 第{i+1}条 含白名单外字段 {sorted(extra)}")

    # 5) 枚举字段
    for fname in sorted(allowed):
        if fname == "额度状态":
            for i, rec in enumerate(records):
                v = rec.get(fname)
                if v is not None and v not in bands:
                    issues.append(
                        f"[致命] {slug}: 第{i+1}条 {fname} 取值不在预声明集合")

    # 6) 值形状（只报原因，不报值）
    for i, rec in enumerate(records):
        for fname, v in rec.items():
            if not isinstance(v, str):
                continue
            if _RE_EMAIL.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似 email")
            elif _RE_PHONE_CN.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似手机号")
            if _RE_BEARER.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似 Bearer 凭证")
            elif _RE_CLI_ID.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似 cli_ 应用凭证")
            elif _RE_KNOWN_KEY.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似已知前缀密钥")
            elif _RE_URL_QUERY.search(v):
                issues.append(f"[致命] {slug}: 第{i+1}条 {fname} 疑似带凭据参数的 URL")

    return issues


def check_referential(cap_records, inst_records):
    """实例的「所属能力」必须引用能力表的 capability_id。"""
    issues = []
    ids = {r.get("capability_id") for r in cap_records}
    for i, rec in enumerate(inst_records):
        ref = rec.get("所属能力")
        if ref is None:
            continue
        for part in str(ref).split(","):
            part = part.strip()
            if part and part not in ids:
                issues.append(
                    f"[致命] instances: 第{i+1}条 所属能力 引用不存在的 capability_id={part!r}")
    return issues


def check_drop_ratio(baseline_counts, current_counts):
    """与上一成功版本比较，记录数下降 >30% 阻断。"""
    issues = []
    for slug, cur in current_counts.items():
        base = baseline_counts.get(slug)
        if base is None or base <= 0:
            continue
        drop = (base - cur) / base
        if drop > DROP_RATIO_LIMIT:
            issues.append(
                f"[阻断] {slug}: 记录数 {base}→{cur}（下降 {drop:.0%} > {DROP_RATIO_LIMIT:.0%}）"
                f"——疑似数据源异常/表被清空，请人工确认后 --force")
    return issues


def main():
    parser = argparse.ArgumentParser(description="公开数据桥产物语义校验器")
    parser.add_argument("--baseline", metavar="INDEX_URL",
                        help="拉取线上 index.json 做数量突变检测")
    parser.add_argument("--force", action="store_true",
                        help="人工确认后跳过数量突变阻断（不跳过 scanner/schema/0条/引用）")
    args = parser.parse_args()

    cfg = load_config()
    schema = json.loads((OUTPUT_DIR / "schema.json").read_text(encoding="utf-8"))
    bands = quota_bands(cfg)

    all_issues = []
    records_by_slug = {}
    for table_name, table_cfg in cfg["tables"].items():
        slug = table_cfg["slug"]
        records = load_table(slug)
        records_by_slug[slug] = records
        schema_cfg = schema.get("tables", {}).get(slug, {})
        all_issues += issues_for_table(table_cfg, schema_cfg, records, bands)

    # 3) 引用完整性
    if {"capabilities", "instances"} <= set(records_by_slug):
        all_issues += check_referential(
            records_by_slug["capabilities"], records_by_slug["instances"])

    # 7) 数量突变
    if args.baseline:
        with urllib.request.urlopen(args.baseline, timeout=30) as resp:
            base = json.loads(resp.read().decode("utf-8"))
        base_counts = {s: i["count"] for s, i in base.get("tables", {}).items()}
        cur_counts = {s: len(r) for s, r in records_by_slug.items()}
        drop_issues = check_drop_ratio(base_counts, cur_counts)
        if drop_issues and not args.force:
            all_issues += drop_issues
        elif drop_issues:
            print("  [已确认] 数量突变命中，已 --force 放行：")
            for it in drop_issues:
                print(f"    {it}")

    if all_issues:
        for it in all_issues:
            print(f"  {it}")
        print("校验未通过——中止部署。")
        sys.exit(1)
    print("校验通过（count/主键/引用/字段集/枚举/值形状/数量突变）")


if __name__ == "__main__":
    main()
