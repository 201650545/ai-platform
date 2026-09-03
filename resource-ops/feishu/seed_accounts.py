# -*- coding: utf-8 -*-
"""表1 账号资产汇总 + 表2 凭证池 初始填充
数据来源：docs/资源调研/验证记录_2026-08-10.md（10 平台登录态实测）
"""
import json, subprocess, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
HERE = os.path.dirname(os.path.abspath(__file__))

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"EXIT {p.returncode}: {p.stderr[:1200]}")
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        print("RAW:", p.stdout[:800])
        return None

def batch_create(table, records):
    body = {"create_records": records}
    tmp = os.path.join(HERE, "_seed.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-create", "--base-token", BASE_TOKEN,
             "--table-id", table, "--as", "user", "--json", "@_seed.json")
    if d and d.get("ok"):
        rids = d.get("data", {}).get("record_id_list", [])
        print(f"  → 写入 {len(rids)} 条到 [{table}]")
        return rids
    print("  ✗ 写入失败:", json.dumps(d, ensure_ascii=False)[:500] if d else "无返回")
    return []

# 表1 账号资产汇总（10 平台，基于验证记录）
ACCOUNTS = [
    dict(account_id="acc-siliconflow-1", 平台名称="硅基流动", 账号标识="GuoyT", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="负余额 ¥-0.1083，代金券 1 张待查；3 个 API key"),
    dict(account_id="acc-deepseek-1", 平台名称="DeepSeek", 账号标识="永涛", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="余额 ¥26.59，API key 在用"),
    dict(account_id="acc-volcengine-1", 平台名称="火山引擎 Ark", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="每日 200 万 token 永久免费档待细查"),
    dict(account_id="acc-aliyun-1", 平台名称="阿里云百炼", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="7000 万 token / 180 天；Qwen 免费档待细查"),
    dict(account_id="acc-groq-1", 平台名称="Groq", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="免费层模型与限额待细查"),
    dict(account_id="acc-modelscope-1", 平台名称="ModelScope 魔搭", 账号标识="郭樂/GuoYongtao", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="每日 250 魔粒自动化已存在"),
    dict(account_id="acc-zhipu-1", 平台名称="智谱 BigModel", 认证方式="手机短信", 会话状态="NEEDS_HUMAN", 状态="待绑定",
         人工介入原因="弹「绑定手机号」对话框未处理", 备注="新户 2000 万 token + GLM-4-Flash 永久免费；GLM-5.2 可用"),
    dict(account_id="acc-kimi-1", 平台名称="Kimi / Moonshot", 认证方式="手机短信", 会话状态="NEEDS_HUMAN", 状态="待绑定",
         人工介入原因="3 种登录 tab 均失败（微信/手机短信/账号密码）", 备注="建议设账号密码免短信费；新户 150 万 token"),
    dict(account_id="acc-openrouter-1", 平台名称="OpenRouter", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注=":free 前缀免费模型不花余额；密钥页待查"),
    dict(account_id="acc-huggingface-1", 平台名称="HuggingFace", 账号标识="GuoyT", 认证方式="密码", 会话状态="LOGGED_IN", 状态="在用",
         备注="免费 Serverless Inference API；Access Tokens 待查"),
]

# 表2 凭证池（已知有 key 的 3 平台 + 可预期扩展）
CREDENTIALS = [
    dict(credential_id="siliconflow-main", 凭证类型="API_KEY", 状态="可用", 本地存储后端="credentials.json",
         备注="对应旧表 SILICONFLOW_API_KEY；负余额"),
    dict(credential_id="zhipu-main", 凭证类型="API_KEY", 状态="可用", 本地存储后端="credentials.json",
         备注="对应旧表 ZHIPU_API_KEY；新户 2000 万 token"),
    dict(credential_id="huggingface-main", 凭证类型="API_KEY", 状态="可用", 本地存储后端="credentials.json",
         备注="对应旧表 HF_TOKEN；免费推理额度"),
]

def main():
    print("== 表1 账号资产汇总 ==")
    batch_create("账号资产汇总", ACCOUNTS)
    print("== 表2 凭证池 ==")
    batch_create("凭证池", CREDENTIALS)

if __name__ == "__main__":
    main()
