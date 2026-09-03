#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开数据桥导出器（方案书 §6.7 白名单 DTO 落地）

飞书 Bitable → 白名单 DTO → 额度区间模糊化 → 敏感扫描 → public/ 静态 JSON
→ GitHub Pages（供高级 AI 连接器实读仓库，持续优化架构）。

用法:
  python exporter/export.py            # 真实同步（需 FEISHU_APP_ID/SECRET + FEISHU_BASE_TOKEN）
  python exporter/export.py --mock     # 本地用 fixture 数据验证 DTO/模糊化/扫描链路
  python exporter/export.py --no-view  # 找不到「AI 公开导出」视图时不失败（仅测试用）

安全边界（方案书 §6）:
  - 白名单 DTO：只输出白名单字段，从零构造，不做黑名单删除
  - 额度模糊化：剩余额度快照 → 区间（充足/中等/偏低/耗尽…），原始数值丢弃
  - 敏感扫描：输出产物逐条 regex，命中即退出码非 0，中止部署（git 历史不可逆）
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "exporter" / "config.json"
FIXTURE_PATH = REPO_ROOT / "exporter" / "fixture_records.json"
OUTPUT_DIR = REPO_ROOT / "public"
UTC8 = datetime.timezone(datetime.timedelta(hours=8))
HTTP_TIMEOUT = 30
PAGE_SIZE = 500
MAX_RETRIES = 4


# ---------- 配置加载 ----------

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------- Feishu API（仅 stdlib） ----------

def _retry_wait(e, attempt):
    """429/5xx 指数退避，尊重 Retry-After；403/401 等配置错误不重试。"""
    ra = (e.headers.get("Retry-After") if getattr(e, "headers", None) else None)
    if ra and ra.isdigit():
        return min(int(ra), 60)
    return min(2 ** attempt, 30)  # 0,2,4,8,16 → 累计约 30s


def http_json(method, url, headers=None, body=None):
    """发 HTTP 请求并解析 JSON 响应（429/5xx/网络抖动有限重试）。

    错误日志只输出 host，绝不输出完整 URL（URL 路径含 FEISHU_BASE_TOKEN）
    也不输出响应 body（可能含敏感字段名），避免把凭证写进 CI 日志。
    """
    headers = dict(headers or {})
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    if body is not None:
        # urllib 默认给表单类型；飞书要求 application/json，否则 10003 invalid param
        headers.setdefault("Content-Type", "application/json")
    host = urllib.parse.urlsplit(url).hostname
    last_err = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            retryable = e.code in (429, 500, 502, 503, 504)
            if not retryable:
                # 401/403/404 等配置或路径错误：不重试，直接失败
                raise RuntimeError(f"HTTP {e.code} host={host}") from e
            last_err = e
            wait = _retry_wait(e, attempt)
            print(f"  [重试] HTTP {e.code} host={host} attempt={attempt+1} wait={wait}s")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            print(f"  [重试] 网络异常 {type(e).__name__} attempt={attempt+1} wait={wait}s")
            time.sleep(wait)
    raise RuntimeError(
        f"HTTP 重试耗尽 host={host} last={type(last_err).__name__}") from last_err


def feishu_auth(base_cfg):
    """获取 tenant_access_token。"""
    url = f"https://{base_cfg['host']}/open-apis/auth/v3/tenant_access_token/internal"
    body = {"app_id": os.environ[base_cfg["app_id_env"]],
            "app_secret": os.environ[base_cfg["app_secret_env"]]}
    resp = http_json("POST", url, body=body)
    if resp.get("code") != 0:
        raise RuntimeError(
            f"认证失败: code={resp.get('code')} msg={resp.get('msg')} "
            f"len_id={len(os.environ[base_cfg['app_id_env']])} "
            f"len_secret={len(os.environ[base_cfg['app_secret_env']])}")
    return resp["tenant_access_token"]


def api_get(token, base_cfg, path, **params):
    """GET 飞书开放接口，自动携带 token 与分页。返回 data.items 列表。"""
    base = f"https://{base_cfg['host']}/open-apis/bitable/v1/apps/{os.environ[base_cfg['app_token_env']]}"
    url = f"{base}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    items, page_token = [], ""
    while True:
        q = dict(params, page_size=str(PAGE_SIZE))
        if page_token:
            q["page_token"] = page_token
        import urllib.parse
        full = f"{url}?{urllib.parse.urlencode(q)}"
        resp = http_json("GET", full, headers=headers)
        if resp.get("code") != 0:
            raise RuntimeError(f"接口失败: {path} code={resp.get('code')} msg={resp.get('msg')}")
        data = resp.get("data") or {}
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
    return items


def resolve_view_id(token, base_cfg, table_id, view_name):
    """在表中定位视图，找不到返回 None（配合 --no-view 降级）。"""
    for v in api_get(token, base_cfg, f"/tables/{table_id}/views"):
        if v.get("view_name") == view_name:
            return v["view_id"]
    return None


# ---------- 值规范化 ----------

def _extract_text(v):
    """从 link/富文本 等值中抽取可读文本。"""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict) and item.get("text"):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return ",".join(parts)
    if isinstance(v, dict):
        if v.get("text"):
            return v["text"]
        if "value" in v:
            return _extract_text(v["value"])
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def normalize_value(v):
    """按值形状归一化：int→日期字符串、list/dict→文本、其余→字符串/数字。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        # 飞书 datetime 字段返回 epoch 毫秒；用 +8 时区格式化为日期，避免 CI(UTC) 差一天
        if v > 10**12:
            try:
                return datetime.datetime.fromtimestamp(v / 1000, tz=UTC8).strftime("%Y-%m-%d")
            except (ValueError, OSError, OverflowError):
                return str(v)
        return v
    if isinstance(v, str):
        return v.strip()
    return _extract_text(v)


def num_or_none(v):
    try:
        return float(str(v).replace(",", "").replace("，", "").strip())
    except (TypeError, ValueError):
        return None


# ---------- 额度区间模糊化 ----------

def compute_quota_band(raw_fields, status_val):
    """剩余额度模糊化区间（不公开精确额度）。"""
    remaining = num_or_none(raw_fields.get("剩余额度快照"))
    total = num_or_none(raw_fields.get("额度总量"))
    margin = num_or_none(raw_fields.get("安全余量"))
    if str(status_val).strip() == "额度耗尽":
        return "耗尽"
    if remaining is None:
        return "未知"
    if remaining <= 0:
        return "耗尽"
    if margin is not None and remaining <= margin:
        return "接近安全余量"
    if total and total > 0:
        pct = remaining / total
        if pct < 0.2:
            return "偏低(<20%)"
        if pct < 0.5:
            return "中等(20-50%)"
        return "充足(>50%)"
    return "未知"


# ---------- 白名单 DTO ----------

def build_dto(table_cfg, raw_fields):
    """按白名单构造公开记录（从零构造，随后丢弃/模糊化敏感字段）。"""
    out = {}
    for fname in table_cfg["whitelist"]:
        if fname in raw_fields:
            v = normalize_value(raw_fields[fname])
            if v not in (None, "", []):
                out[fname] = v
    # 模糊化：先算区间，再丢弃原始数值
    for band_field, band_cfg in table_cfg.get("fuzz", {}).items():
        if band_cfg.get("from"):
            out[band_field] = compute_quota_band(raw_fields, raw_fields.get("状态"))
    for fname in table_cfg.get("drop", []):
        out.pop(fname, None)
    return out


# ---------- 敏感扫描 ----------

def scan_outputs(root, patterns):
    """对全部公开产物做敏感扫描，命中即返回问题列表。

    命中值绝不写入日志：只输出 文件/检测器/offset/命中长度/sha256 前 12 位，
    避免「成功拦截部署、却把疑似凭证写进 CI 日志」。
    """
    issues = []
    for path in sorted(root.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                digest = hashlib.sha256(m.group(0).encode("utf-8")).hexdigest()[:12]
                issues.append(
                    f"{path.name}: detector=/{pat}/ offset={m.start()} "
                    f"len={m.end() - m.start()} sha256={digest}"
                )
    return issues


# ---------- 输出 ----------

def write_outputs(table_records, meta):
    """写 public/ 下的静态 JSON。table_records: {slug: [records]}"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    for slug, records in table_records.items():
        (OUTPUT_DIR / f"{slug}.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    capabilities = table_records.get("capabilities", [])
    instances = table_records.get("instances", [])
    index = {
        "site": "AI 自助资源运营体系 · 公开数据桥",
        "repo": "https://github.com/201650545/ai-platform/tree/main/resource-ops",
        "bridge_version": meta["bridge_version"],
        "build_id": meta["build_id"],
        "generated_at": meta["generated_at"],
        "freshness": {"stale_after_hours": 48},
        "note": "公开数据桥（方案书 §6.7）：白名单 DTO + 额度区间模糊化；凭证值/精确额度/内部账号绝不公开。"
                "消费方注意：generated_at 距今超过 48h 时数据视为陈旧，只作架构参考。",
        "tables": {
            "capabilities": {"count": len(capabilities), "file": "capabilities.json",
                             "primary_key": "capability_id"},
            "instances": {"count": len(instances), "file": "instances.json",
                          "primary_key": "instance_id", "fuzz": "额度状态"},
        },
        "fuzz_policy": "剩余额度快照/额度总量/安全余量 → 额度状态区间（耗尽/接近安全余量/偏低/中等/充足/未知）；原始数值不导出。",
    }
    (OUTPUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    schema = {"bridge_version": meta["bridge_version"], "tables": {}}
    for slug, records in table_records.items():
        cfg = meta["table_configs"][slug]
        schema["tables"][slug] = {
            "primary_key": cfg["primary_key"],
            "fields": cfg["whitelist"],
            "computed": list(cfg.get("fuzz", {}).keys()) or None,
        }
    (OUTPUT_DIR / "schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")

    # manifest.json ——「提交点」：先写完全部数据文件、最后写 manifest。
    # 哈希的是实际写盘字节（Path.read_bytes），与消费端 r.content 原始字节同口径；
    # 消费端逐文件 sha256 比对，自证「四文件同属一个 build」（fail-closed）。
    files = {}
    for name in ("index.json", "capabilities.json", "instances.json", "schema.json"):
        files[name] = {"sha256": hashlib.sha256((OUTPUT_DIR / name).read_bytes()).hexdigest()}
    manifest = {
        "bridge_version": meta["bridge_version"],
        "build_id": meta["build_id"],
        "generated_at": meta["generated_at"],
        "files": files,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return index


# ---------- 数据获取（真实 / mock） ----------

def fetch_real(cfg, allow_missing_view=False):
    """真实拉取飞书数据。

    allow_missing_view=False（CI 默认）时，公开导出视图找不到即中止——
    fail-closed，避免视图被重命名/误删后「降级为全表」把不该公开的记录导出去。
    --no-view 仅存在于人工测试路径（传 allow_missing_view=True）。
    """
    base_cfg = cfg["base"]
    for key in ("app_id_env", "app_secret_env", "app_token_env"):
        if base_cfg[key] not in os.environ:
            raise RuntimeError(f"缺少环境变量 {base_cfg[key]}——本地请先 export，CI 走仓库 Secret")
    token = feishu_auth(base_cfg)
    tables = {t["name"]: t["table_id"] for t in api_get(token, base_cfg, "/tables")}
    records = {}
    view_found = {name: None for name in cfg["tables"]}
    for table_name, table_cfg in cfg["tables"].items():
        if table_name not in tables:
            raise RuntimeError(f"base 中找不到表「{table_name}」")
        table_id = tables[table_name]
        view_id = resolve_view_id(token, base_cfg, table_id, base_cfg["export_view"])
        view_found[table_name] = view_id
        if not view_id and not allow_missing_view:
            raise RuntimeError(
                f"缺少公开导出视图（fail-closed）: table={table_name!r} "
                f"view={base_cfg['export_view']!r}——请检查飞书视图是否被重命名/误删"
            )
        params = {}
        if view_id:
            params["view_id"] = view_id
        raw = api_get(token, base_cfg, f"/tables/{table_id}/records", **params)
        records[table_name] = [r.get("fields", {}) for r in raw]
    for name, vid in view_found.items():
        state = "OK" if vid else ("降级为全表(仅测试)" if allow_missing_view else "未找到")
        print(f"  [表] {name} 视图「{base_cfg['export_view']}」: {state}")
    return records


def fetch_mock(cfg):
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["tables"]


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="AI 自助资源运营体系 · 公开数据桥导出器")
    parser.add_argument("--mock", action="store_true", help="用 fixture 数据本地验证链路")
    parser.add_argument("--no-view", action="store_true",
                        help="找不到「AI 公开导出」视图时降级为全表（仅测试用，CI 不得使用）")
    args = parser.parse_args()

    cfg = load_config()
    base_cfg = cfg["base"]
    if args.no_view and not args.mock:
        print("警告: --no-view 会绕过视图级防护，仅限本地测试。")

    print("① 拉取记录")
    raw_tables = (
        fetch_mock(cfg)
        if args.mock
        else fetch_real(cfg, allow_missing_view=args.no_view)
    )

    print("② 白名单 DTO + 额度模糊化")
    table_records, table_configs = {}, {}
    for table_name, table_cfg in cfg["tables"].items():
        slug = table_cfg["slug"]
        records = [build_dto(table_cfg, f) for f in raw_tables.get(table_name, [])]
        records = [r for r in records if r]  # 去掉空记录
        table_records[slug] = records
        table_configs[slug] = table_cfg
        print(f"  [{slug}] {len(records)} 条")

    print("③ 敏感扫描")
    # 先写入，后扫描，保证扫描对象就是即将部署的产物
    # build_id = 内容哈希（不含 generated_at）：数据未变化时保持稳定，
    # 供 CI 判断「是否需要部署」，避免每天无意义重传。
    canonical = json.dumps(table_records, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    meta = {
        "bridge_version": cfg["bridge_version"],
        "build_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "generated_at": datetime.datetime.now(UTC8).isoformat(timespec="seconds"),
        "table_configs": table_configs,
    }
    index = write_outputs(table_records, meta)
    issues = scan_outputs(OUTPUT_DIR, cfg["scan"]["patterns"])
    if issues:
        for it in issues:
            print(f"  [致命] {it}")
        print("敏感扫描未通过——中止（git 历史不可逆）。")
        sys.exit(1)
    print("  扫描通过（0 命中）")

    print(f"④ 完成: public/ 共 {index['tables']['capabilities']['count']} 能力, "
          f"{index['tables']['instances']['count']} 实例")
    print(f"  generated_at={meta['generated_at']}")


if __name__ == "__main__":
    main()
