# -*- coding: utf-8 -*-
"""v0.3 飞书 base 六表重构落地脚本
用法: python build_v03.py <step>
  step: table3 | table4 | table2 | migrate | table1 | table6 | delete_old | link_fields | verify

通道: 直接调 node run.js（绕开坏掉的 .bashrc lark-cli 函数）
"""
import json, subprocess, sys, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")

def lark(*args):
    """调用 lark-cli，返回解析后的 JSON dict。"""
    cmd = [NODE, RUN_JS] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"EXIT {p.returncode}: {' '.join(cmd)}")
        print(p.stderr[:3000])
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        print("RAW:", p.stdout[:2000])
        return None

# ---------- 字段定义 ----------

TABLE3_FIELDS = [
    {"type": "text", "name": "capability_id", "description": "唯一键"},
    {"type": "text", "name": "资源名称", "description": "人类可读名"},
    {"type": "select", "name": "类别", "options": [
        {"name": "LLM API", "hue": "Blue"},
        {"name": "生图", "hue": "Purple"},
        {"name": "搜索", "hue": "Orange"},
        {"name": "云GPU", "hue": "Red"},
        {"name": "向量库", "hue": "Green"},
        {"name": "IDE", "hue": "Gray"},
        {"name": "其他", "hue": "Gray"},
    ]},
    {"type": "text", "name": "逻辑模型", "description": "canonical_model：轮换锁定模型"},
    {"type": "select", "name": "质量等级", "options": [
        {"name": "T0", "hue": "Red", "lightness": "Dark"},
        {"name": "T1", "hue": "Blue"},
        {"name": "T2", "hue": "Gray"},
    ]},
    {"type": "select", "name": "调用方式", "options": [
        {"name": "HTTP_REST", "hue": "Green"},
        {"name": "OPENCLI_BROWSER", "hue": "Blue"},
        {"name": "CLI_TOOL", "hue": "Gray"},
    ]},
    {"type": "text", "name": "adapter_id", "description": "本地 adapter 标识，知道如何注入 Secret"},
    {"type": "text", "name": "协议版本"},
    {"type": "select", "name": "认证方案", "description": "auth_scheme（不存模板）", "options": [
        {"name": "bearer", "hue": "Green"},
        {"name": "api_key", "hue": "Blue"},
        {"name": "none", "hue": "Gray"},
    ]},
    {"type": "text", "name": "允许主机", "description": "allowed_hosts：Secret 只允许发到这里"},
    {"type": "text", "name": "模型族"},
    {"type": "text", "name": "endpoint", "description": "调用地址"},
    {"type": "text", "name": "请求体模板", "description": "payload_json，{{MODEL}} 运行时替换；不含 Secret"},
    {"type": "text", "name": "健康探测", "description": "health_probe_id"},
    {"type": "text", "name": "路由组", "description": "routing_group（唯一真源在此），默认=capability_id"},
    {"type": "text", "name": "免费额度描述", "description": "权益描述（人读）"},
    {"type": "text", "name": "请求模板版本"},
    {"type": "select", "name": "状态", "options": [
        {"name": "可用", "hue": "Green"},
        {"name": "待验证", "hue": "Orange"},
        {"name": "失效", "hue": "Red"},
        {"name": "暂停", "hue": "Gray"},
    ]},
]

TABLE4_FIELDS = [
    {"type": "text", "name": "instance_id", "description": "唯一键"},
    {"type": "text", "name": "平台"},
    {"type": "text", "name": "实际模型名", "description": "provider_model_name"},
    {"type": "number", "name": "额度总量", "style": {"type": "plain", "thousands_separator": True}},
    {"type": "select", "name": "额度单位", "options": [
        {"name": "token", "hue": "Blue"},
        {"name": "元", "hue": "Green"},
        {"name": "次", "hue": "Orange"},
        {"name": "分钟", "hue": "Purple"},
    ]},
    {"type": "number", "name": "剩余额度快照", "description": "quota_remaining_snapshot（运行时真源在 SQLite）"},
    {"type": "select", "name": "重置规则", "options": [
        {"name": "周期重置", "hue": "Green"},
        {"name": "一次性", "hue": "Orange"},
        {"name": "不重置", "hue": "Gray"},
    ]},
    {"type": "datetime", "name": "额度重置日", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "额度到期日", "style": {"format": "yyyy-MM-dd"}},
    {"type": "number", "name": "安全余量", "description": "低于此即 EXHAUSTED"},
    {"type": "text", "name": "限速", "description": "rate_limit_rpm / tpm"},
    {"type": "number", "name": "路由优先级", "description": "route_priority：越小越优先"},
    {"type": "number", "name": "配置版本", "description": "config_version：模板/凭证变更递增"},
    {"type": "text", "name": "需人工登录URL", "description": "AI 无法自动时给人工"},
    {"type": "text", "name": "缺失环境变量"},
    {"type": "text", "name": "获取方式备注", "description": "领取路径"},
    {"type": "select", "name": "验证策略", "options": [
        {"name": "HTTP探测", "hue": "Green"},
        {"name": "需浏览器", "hue": "Orange"},
        {"name": "需人工", "hue": "Red"},
    ]},
    {"type": "datetime", "name": "上次验证", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "下次验证", "style": {"format": "yyyy-MM-dd"}},
    {"type": "text", "name": "验证指纹", "description": "verification_fingerprint（哈希）"},
    {"type": "select", "name": "状态", "options": [
        {"name": "可用", "hue": "Green"},
        {"name": "额度耗尽", "hue": "Red"},
        {"name": "冷却中", "hue": "Orange"},
        {"name": "失效", "hue": "Red"},
        {"name": "待验证", "hue": "Orange"},
    ]},
    {"type": "text", "name": "备注"},
]

TABLE2_FIELDS = [
    {"type": "text", "name": "credential_id", "description": "唯一键，对应本地 credentials.json 键名"},
    {"type": "select", "name": "凭证类型", "options": [
        {"name": "API_KEY", "hue": "Blue"},
        {"name": "OAUTH_TOKEN", "hue": "Purple"},
        {"name": "账号密码", "hue": "Orange"},
    ]},
    {"type": "select", "name": "状态", "options": [
        {"name": "可用", "hue": "Green"},
        {"name": "停用", "hue": "Gray"},
        {"name": "额度耗尽", "hue": "Red"},
        {"name": "需人工", "hue": "Orange"},
    ]},
    {"type": "datetime", "name": "有效期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "select", "name": "本地存储后端", "options": [
        {"name": "credentials.json", "hue": "Blue"},
        {"name": "OS keychain", "hue": "Purple"},
    ]},
    {"type": "datetime", "name": "上次本地检查", "style": {"format": "yyyy-MM-dd"}},
    {"type": "text", "name": "备注", "description": "坑、使用限制"},
]

TABLE1_FIELDS = [
    {"type": "text", "name": "account_id", "description": "稳定唯一键，不用平台名当关系键"},
    {"type": "text", "name": "平台名称"},
    {"type": "text", "name": "账号标识", "description": "区分同平台多账号"},
    {"type": "select", "name": "认证方式", "description": "auth_method", "options": [
        {"name": "密码", "hue": "Blue"},
        {"name": "Google OAuth", "hue": "Green"},
        {"name": "手机短信", "hue": "Orange"},
        {"name": "微信扫码", "hue": "Purple"},
    ]},
    {"type": "select", "name": "会话状态", "description": "session_state", "options": [
        {"name": "LOGGED_IN", "hue": "Green"},
        {"name": "EXPIRED", "hue": "Orange"},
        {"name": "NEEDS_HUMAN", "hue": "Red"},
    ]},
    {"type": "checkbox", "name": "绑定手机"},
    {"type": "text", "name": "浏览器Profile", "description": "browser_profile_ref：本地独立 Chrome Profile 逻辑 ID（不存 cookie）"},
    {"type": "datetime", "name": "上次会话验证", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "下次会话验证", "style": {"format": "yyyy-MM-dd"}},
    {"type": "text", "name": "人工介入原因"},
    {"type": "select", "name": "状态", "options": [
        {"name": "在用", "hue": "Green"},
        {"name": "停用", "hue": "Gray"},
        {"name": "待绑定", "hue": "Orange"},
    ]},
    {"type": "text", "name": "备注", "description": "待办、坑"},
]

TABLE6_FIELDS = [
    {"type": "text", "name": "task_id", "description": "唯一"},
    {"type": "select", "name": "任务类型", "options": [
        {"name": "调研", "hue": "Blue"},
        {"name": "验证", "hue": "Green"},
        {"name": "领取", "hue": "Purple"},
        {"name": "抓额度", "hue": "Orange"},
        {"name": "调度", "hue": "Red"},
        {"name": "清理", "hue": "Gray"},
        {"name": "校验", "hue": "Gray"},
    ]},
    {"type": "text", "name": "幂等键", "description": "idempotency_key = task_type + target_id + verifier_version + target_config_hash"},
    {"type": "text", "name": "目标配置哈希", "description": "target_config_hash = hash(endpoint+headers+payload+verification_policy)"},
    {"type": "text", "name": "验证器版本", "description": "verifier_version（= 模板哈希或人工版本）"},
    {"type": "text", "name": "执行Agent", "description": "created_by"},
    {"type": "text", "name": "领取人", "description": "leased_by（SQLite 里做 UNIQUE/事务）"},
    {"type": "datetime", "name": "领取到期", "description": "lease_until：过期由清理任务捞回", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "number", "name": "尝试次数", "description": "attempt_no：上限 3，超限转 NEEDS_HUMAN"},
    {"type": "select", "name": "状态", "options": [
        {"name": "PENDING", "hue": "Gray"},
        {"name": "LEASED", "hue": "Blue"},
        {"name": "RUNNING", "hue": "Orange"},
        {"name": "SUCCEEDED", "hue": "Green"},
        {"name": "FAILED", "hue": "Red"},
        {"name": "NEEDS_HUMAN", "hue": "Red", "lightness": "Dark"},
    ]},
    {"type": "datetime", "name": "开始时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "datetime", "name": "结束时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "text", "name": "结果码", "description": "QUOTA_EXHAUSTED / RATE_LIMIT / CRED_INVALID / CONFIG_INVALID / OK"},
    {"type": "text", "name": "证据哈希", "description": "evidence_hash（脱敏摘要哈希，不传整页截图）"},
    {"type": "select", "name": "同步状态", "options": [
        {"name": "PENDING", "hue": "Orange"},
        {"name": "ACK", "hue": "Green"},
    ]},
    {"type": "text", "name": "替代任务", "description": "supersedes_task_id"},
    {"type": "text", "name": "错误信息", "description": "白名单式：只记允许字段，禁止凭证/header/URL query"},
]

def create_table(name, fields, jq=None):
    """创建表（首字段为主字段）。"""
    args = [NODE, RUN_JS, "base", "+table-create",
            "--base-token", BASE_TOKEN, "--name", name, "--as", "user",
            "--fields", json.dumps(fields, ensure_ascii=False)]
    if jq:
        args += ["-q", jq, "--format", "json"]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f"== create table [{name}] exit={p.returncode}")
    if p.returncode == 0:
        try:
            d = json.loads(p.stdout)
            # 找 table_id
            tid = d.get("data", {}).get("table_id") or d.get("data", {}).get("table", {}).get("table_id")
            print("  table_id:", tid)
            return tid
        except Exception as e:
            print("  PARSE:", p.stdout[:1000])
            return None
    else:
        print("  ERR:", p.stderr[:2000])
        return None

def get_table_id(name):
    d = lark("base", "+table-list", "--base-token", BASE_TOKEN, "--as", "user")
    if not d:
        return None
    for t in d.get("data", {}).get("tables", []):
        if t.get("name") == name:
            return t["id"]
    return None

def add_field(table_name, field_json):
    """在指定表追加一个字段。"""
    args = [NODE, RUN_JS, "base", "+field-create",
            "--base-token", BASE_TOKEN, "--table-id", table_name, "--as", "user",
            "--json", json.dumps(field_json, ensure_ascii=False)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0
    fname = field_json.get("name")
    print(f"  +field [{table_name}]{fname} exit={p.returncode} {'OK' if ok else p.stderr[:300]}")
    return ok

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "table3"
    if step == "table3":
        create_table("资源能力规格表", TABLE3_FIELDS)
    elif step == "table4":
        create_table("资源实例表", TABLE4_FIELDS)
    elif step == "table2":
        create_table("凭证池", TABLE2_FIELDS)
    elif step == "table1":
        create_table("账号资产汇总", TABLE1_FIELDS)
    elif step == "table6":
        create_table("自动化任务日志", TABLE6_FIELDS)
    elif step == "link_fields":
        # 表4 资源实例表：所属能力→表3、凭证ID→表2
        for f in [{"type": "link", "name": "所属能力", "link_table": "资源能力规格表",
                   "bidirectional": True, "bidirectional_link_field_name": "实例列表"},
                  {"type": "link", "name": "凭证ID", "link_table": "凭证池",
                   "bidirectional": True, "bidirectional_link_field_name": "使用实例"}]:
            add_field("资源实例表", f)
        # 表2 凭证池：所属账号→表1
        add_field("凭证池", {"type": "link", "name": "所属账号", "link_table": "账号资产汇总",
                             "bidirectional": True, "bidirectional_link_field_name": "凭证列表"})
        # 表6 自动化任务日志：关联实例→表4
        add_field("自动化任务日志", {"type": "link", "name": "关联实例", "link_table": "资源实例表",
                                     "bidirectional": True, "bidirectional_link_field_name": "任务列表"})
    elif step == "verify":
        print(json.dumps(lark("base", "+table-list", "--base-token", BASE_TOKEN, "--as", "user"),
                         ensure_ascii=False, indent=1))
    else:
        print("unknown step", step)
