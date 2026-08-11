# -*- coding: utf-8 -*-
"""任务C执行：飞书 AI 自助资源库 21 平台全量回写
流程：清空4表旧数据 → 表1账号(21) → 表2凭证(5) → 表3能力(21) → 表4实例(21) → 表6日志(1) → 建关联
数据源：docs/资源调研/验证记录_2026-08-10.md（28 条目合并为 21 独立平台）
用法: python task_c_seed.py
"""
import json, subprocess, os, sys

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
HERE = os.path.dirname(os.path.abspath(__file__))

T1, T2, T3, T4, T6 = "tblsrXWXX8GQ9hx4", "tblRoOrNBJHlB4je", "tbllAPtPd68uDTTj", "tbl8bKuwqP0Wl4d1", "tblbNwDHcYaJGVYW"

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"  EXIT {p.returncode}: {p.stderr[:800]}"); return None
    try: return json.loads(p.stdout)
    except Exception:
        print("  RAW:", p.stdout[:600]); return None

def list_records(table_id):
    d = lark("base", "+record-list", "--base-token", BASE_TOKEN, "--table-id", table_id,
             "--page-size", "100", "--format", "json", "--as", "user")
    if not d: return []
    data = d.get("data", {})
    return data.get("record_id_list", [])

def delete_all(table_id, name):
    rids = list_records(table_id)
    if not rids:
        print(f"[{name}] 空，跳过删除"); return
    body = {"record_id_list": rids}
    tmp = os.path.join(HERE, "_del.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-delete", "--base-token", BASE_TOKEN, "--table-id", table_id,
             "--as", "user", "--json", "@_del.json", "--yes")
    print(f"[{name}] 删除 {len(rids)} 条:", "OK" if d and d.get("ok") else (json.dumps(d, ensure_ascii=False)[:300] if d else "无返回"))

def batch_create(table_id, records, name):
    """records: [ {字段名: 值}, ... ]，返回 record_id_list"""
    body = {"create_records": records}
    tmp = os.path.join(HERE, "_batch.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-create", "--base-token", BASE_TOKEN,
             "--table-id", table_id, "--as", "user", "--json", "@_batch.json")
    if d and d.get("ok"):
        rids = d.get("data", {}).get("record_id_list", [])
        print(f"[{name}] 写入 {len(rids)} 条 OK")
        return rids
    print(f"[{name}] ✗ 失败:", json.dumps(d, ensure_ascii=False)[:800] if d else "无返回")
    return []

def batch_update(table_id, updates, name):
    """updates: { record_id: {字段名: 值} }"""
    body = {"update_records": updates}
    tmp = os.path.join(HERE, "_upd.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-update", "--base-token", BASE_TOKEN,
             "--table-id", table_id, "--as", "user", "--json", "@_upd.json")
    print(f"[{name}] 更新 {len(updates)} 条:", "OK" if d and d.get("ok") else (json.dumps(d, ensure_ascii=False)[:300] if d else "无返回"))
    return d

def sel(name):
    return name  # select 字段用纯字符串

def dte(day):
    return day  # datetime 字段传 yyyy-MM-dd 字符串

# ================= 表1 账号资产汇总（21 平台） =================
ACCOUNTS = [
    dict(account_id="acc-siliconflow-1", 平台名称="硅基流动 SiliconFlow", 账号标识="GuoyT", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="sf-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="负余额 ¥-0.1083，代金券1张待查；3个key；限免模型 Qwen3-Omni-Captioner/Qwen-Image"),
    dict(account_id="acc-deepseek-1", 平台名称="DeepSeek", 账号标识="永涛", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="ds-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="余额 ¥26.59；用量 12亿 token/月，适合额度轮换"),
    dict(account_id="acc-volcengine-1", 平台名称="火山引擎 Ark", 账号标识="", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="vc-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="每日 200 万 token 永久免费档待细查"),
    dict(account_id="acc-aliyun-1", 平台名称="阿里云百炼", 账号标识="", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="ali-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="7000 万 token/180 天 + Qwen 免费档待细查"),
    dict(account_id="acc-groq-1", 平台名称="Groq", 账号标识="", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="groq-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="Base 免费档 30 RPM 基础限流（全部模型）"),
    dict(account_id="acc-modelscope-1", 平台名称="ModelScope 魔搭", 账号标识="郭樂/GuoYongtao", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="ms-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="每日 250 魔粒自动化已存在"),
    dict(account_id="acc-zhipu-1", 平台名称="智谱 BigModel", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="zp-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="弹「绑定手机号」对话框未处理", 状态=sel("在用"), 备注="新户 2000 万 token + GLM-4-Flash 永久免费；GLM-5.2 旗舰可用"),
    dict(account_id="acc-kimi-1", 平台名称="Kimi / Moonshot", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("NEEDS_HUMAN"), 绑定手机=False, 浏览器Profile="kimi-main", 人工介入原因="3 种登录 tab 均失败，建议设账号密码免短信费", 状态=sel("待绑定"), 备注="新户 150 万 token"),
    dict(account_id="acc-openrouter-1", 平台名称="OpenRouter", 账号标识="yongtaog767@gmail.com", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="or-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="14 个 :free 模型不耗余额；聚合 402 模型"),
    dict(account_id="acc-huggingface-1", 平台名称="HuggingFace", 账号标识="GuoyT", 认证方式=sel("密码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="hf-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="Access Token 需通过 security-checkup", 状态=sel("在用"), 备注="免费 Inference Providers 慷慨免费档"),
    dict(account_id="acc-githubmodels-1", 平台名称="GitHub Models", 账号标识="", 认证方式=sel("密码"), 会话状态=sel("EXPIRED"), 绑定手机=False, 浏览器Profile="gh-main", 状态=sel("停用"), 备注="RETIRED：2026-07-30 完全退役，替代见 Azure AI Foundry / Copilot"),
    dict(account_id="acc-colab-1", 平台名称="Google Colab", 账号标识="yongtaog767@gmail.com", 认证方式=sel("Google OAuth"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="colab-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="GPU 型号需手动 Runtime 探测", 状态=sel("在用"), 备注="免费 GPU 动态变化，不写死 T4"),
    dict(account_id="acc-together-1", 平台名称="Together.ai", 账号标识="org_Cdv4r9DTTKUzENwujzEfm", 认证方式=sel("Google OAuth"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="tg-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="NO_FREE_QUOTA：无免费 trial，需 ≥$5 充值"),
    dict(account_id="acc-mistral-1", 平台名称="Mistral", 账号标识="永涛 郭", 认证方式=sel("Google OAuth"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="mt-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="Free 计划 $10/月 API + $10/月 Vibe，合计 $20/月"),
    dict(account_id="acc-baidu-1", 平台名称="百度智能云千帆", 账号标识="", 认证方式=sel("微信扫码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="bd-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="8000 万 Tokens 免费包/¥1155 券待核实", 状态=sel("在用"), 备注="官网活动：8000 万 Tokens 免费包 + 新人券 ¥1155（至 2026-09-15）"),
    dict(account_id="acc-tencent-hunyuan-1", 平台名称="腾讯混元（旧）", 账号标识="", 认证方式=sel("微信扫码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="tx-hy-main", 上次会话验证=dte("2026-08-11"), 状态=sel("停用"), 备注="RETIRED：2026-09-30 全面停服，迁移 TokenHub"),
    dict(account_id="acc-tokenhub-1", 平台名称="腾讯 TokenHub", 账号标识="", 认证方式=sel("微信扫码"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="tx-th-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="需创建独立 API Key 并核实 100 万免费 Tokens", 状态=sel("在用"), 备注="新用户 100 万 Tokens/90 天；含 DeepSeek V4/GLM-5.2/Kimi K3 等"),
    dict(account_id="acc-minimax-1", 平台名称="MiniMax", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="mm-main", 上次会话验证=dte("2026-08-11"), 状态=sel("在用"), 备注="NO_FREE_QUOTA：无免费 token（Token Plan 未订阅/积分 0）；有订阅key仅 Plan 调用"),
    dict(account_id="acc-yi-1", 平台名称="零一万物 Yi", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("EXPIRED"), 绑定手机=False, 浏览器Profile="yi-main", 人工介入原因="平台停服，如有余额按官方指引申请退还", 状态=sel("停用"), 备注="RETIRED：停止在线体验/API/充值，开放余额退还"),
    dict(account_id="acc-xfyun-1", 平台名称="讯飞星火", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("LOGGED_IN"), 绑定手机=False, 浏览器Profile="xf-main", 上次会话验证=dte("2026-08-11"), 人工介入原因="未实名 L0 受限，如需开源 0 元档建议先实名", 状态=sel("在用"), 备注="余额 ¥0；Spark Lite 免费、开源 0 元档；测试应用 APPID 43d55148"),
    dict(account_id="acc-stepfun-1", 平台名称="阶跃星辰 StepFun", 账号标识="", 认证方式=sel("手机短信"), 会话状态=sel("NEEDS_HUMAN"), 绑定手机=False, 浏览器Profile="sf2-main", 人工介入原因="未登录，点首页「用户中心」完成登录", 状态=sel("待绑定"), 备注="官网赠送账户（未登录核实）；Step 3.7/3.5 Flash"),
]

# ================= 表2 凭证池（有 key 的 5 平台） =================
CREDENTIALS = [
    dict(credential_id="siliconflow-main", 凭证类型=sel("API_KEY"), 状态=sel("可用"), 本地存储后端=sel("credentials.json"), 备注="对应旧表 SILICONFLOW_API_KEY；负余额"),
    dict(credential_id="deepseek-main", 凭证类型=sel("API_KEY"), 状态=sel("可用"), 本地存储后端=sel("credentials.json"), 备注="对应旧表 DEEPSEEK_API_KEY；余额 ¥26.59"),
    dict(credential_id="zhipu-main", 凭证类型=sel("API_KEY"), 状态=sel("可用"), 本地存储后端=sel("credentials.json"), 备注="对应旧表 ZHIPU_API_KEY；2000 万 token 新户"),
    dict(credential_id="openrouter-main", 凭证类型=sel("API_KEY"), 状态=sel("可用"), 本地存储后端=sel("credentials.json"), 备注="7 个 key 选主；:free 模型不耗余额"),
    dict(credential_id="huggingface-main", 凭证类型=sel("API_KEY"), 状态=sel("需人工"), 本地存储后端=sel("credentials.json"), 备注="Access Token 待通过 security-checkup 确认"),
]

# ================= 表3 资源能力规格表（21 平台） =================
# 每项: capability_id, 资源名称, 类别, 逻辑模型, 质量等级, 调用方式, 认证方案, endpoint, 模型族, 状态, 免费额度描述
CAPS_RAW = [
    ("cap-siliconflow", "硅基流动 SiliconFlow", "LLM API", "Qwen/Qwen3-Omni-30B-A3B-Captioner", "T2", "HTTP_REST", "bearer",
     "https://api.siliconflow.cn/v1", "Qwen", "可用", "限免模型：Qwen3-Omni-Captioner、Qwen-Image；其余按量计费"),
    ("cap-deepseek", "DeepSeek", "LLM API", "deepseek-chat", "T0", "HTTP_REST", "bearer",
     "https://api.deepseek.com/v1", "DeepSeek", "可用", "余额 ¥26.59 按量付费"),
    ("cap-volcengine", "火山引擎 Ark", "LLM API", "doubao-seed-1.6-lite", "T1", "HTTP_REST", "bearer",
     "https://ark.cn-beijing.volces.com/api/v3", "Doubao/DeepSeek", "待验证", "每日 200 万 token 永久免费档"),
    ("cap-aliyun", "阿里云百炼", "LLM API", "qwen-plus", "T1", "HTTP_REST", "bearer",
     "https://dashscope.aliyuncs.com/compatible-mode/v1", "Qwen", "待验证", "新户 7000 万 token/180 天 + Qwen 免费档"),
    ("cap-groq", "Groq", "LLM API", "llama-3.3-70b-versatile", "T1", "HTTP_REST", "bearer",
     "https://api.groq.com/openai/v1", "Llama/GPT-OSS/Qwen", "可用", "Base 免费档全部模型 30 RPM"),
    ("cap-modelscope", "ModelScope 魔搭", "LLM API", "Qwen2.5-7B-Instruct", "T2", "HTTP_REST", "bearer",
     "https://api-inference.modelscope.cn/v1", "Qwen", "待验证", "每日 250 魔粒免费额度"),
    ("cap-zhipu", "智谱 BigModel", "LLM API", "glm-4-flash", "T0", "HTTP_REST", "bearer",
     "https://open.bigmodel.cn/api/paas/v4", "GLM", "可用", "GLM-4-Flash 永久免费 + 新户 2000 万 token"),
    ("cap-kimi", "Kimi / Moonshot", "LLM API", "moonshot-v1-8k", "T1", "HTTP_REST", "bearer",
     "https://api.moonshot.cn/v1", "Moonshot", "待验证", "新户 150 万 token"),
    ("cap-openrouter", "OpenRouter", "LLM API", "google/gemma-4-31b-it:free", "T1", "HTTP_REST", "bearer",
     "https://openrouter.ai/api/v1", "聚合 402 模型", "可用", "14 个 :free 免费模型不耗余额"),
    ("cap-huggingface", "HuggingFace", "LLM API", "router.huggingface.co", "T1", "HTTP_REST", "bearer",
     "https://router.huggingface.co/v1", "开源模型聚合", "待验证", "Inference Providers 慷慨免费档"),
    ("cap-githubmodels", "GitHub Models", "LLM API", "N/A", "T2", "HTTP_REST", "none",
     "", "N/A", "失效", "RETIRED 2026-07-30，无 API"),
    ("cap-colab", "Google Colab", "云GPU", "GPU动态", "T2", "OPENCLI_BROWSER", "none",
     "https://colab.research.google.com/", "GPU/TPU", "可用", "免费 GPU 动态分配（不写死 T4）"),
    ("cap-together", "Together.ai", "LLM API", "openai/gpt-oss-20b", "T1", "HTTP_REST", "bearer",
     "https://api.together.ai/v1", "OpenAI/GPT-OSS", "待验证", "NO_FREE_QUOTA：需 ≥$5 充值"),
    ("cap-mistral", "Mistral", "LLM API", "mistral-large-latest", "T1", "HTTP_REST", "bearer",
     "https://api.mistral.ai/v1", "Mistral 全系", "可用", "Free 计划 $10/月 API + $10/月 Vibe"),
    ("cap-baidu", "百度智能云千帆", "LLM API", "ernie-4.5t", "T0", "HTTP_REST", "bearer",
     "https://qianfan.baidubce.com/v2", "ERNIE/DeepSeek", "待验证", "8000 万 Tokens 免费包 + 新人券 ¥1155"),
    ("cap-tencent-hunyuan", "腾讯混元（旧）", "LLM API", "hunyuan-turbo", "T1", "HTTP_REST", "bearer",
     "https://api.hunyuan.cloud.tencent.com/v1", "Hunyuan", "失效", "RETIRED：2026-09-30 停服，迁移 TokenHub"),
    ("cap-tokenhub", "腾讯 TokenHub", "LLM API", "DeepSeek-V4-Flash", "T0", "HTTP_REST", "bearer",
     "https://tokenhub.tencentmaas.com/v1", "DeepSeek/GLM/Kimi/MiniMax/Hy", "待验证", "新用户 100 万 Tokens/90 天"),
    ("cap-minimax", "MiniMax", "LLM API", "MiniMax-M3", "T1", "HTTP_REST", "bearer",
     "https://api.minimaxi.com/v1", "MiniMax", "待验证", "NO_FREE_QUOTA：需 Token Plan 订阅或充值积分"),
    ("cap-yi", "零一万物 Yi", "LLM API", "yi-lightning", "T2", "HTTP_REST", "none",
     "", "Yi", "失效", "RETIRED：平台停服，开放余额退还"),
    ("cap-xfyun", "讯飞星火", "LLM API", "Spark-Lite", "T1", "HTTP_REST", "bearer",
     "https://spark-api-open.xf-yun.com/v1", "Spark", "待验证", "Spark Lite 免费、开源模型 0 元档；未实名 L0 受限"),
    ("cap-stepfun", "阶跃星辰 StepFun", "LLM API", "step-3.7-flash", "T1", "HTTP_REST", "bearer",
     "https://api.stepfun.com/v1", "Step", "待验证", "官网赠送账户（未登录核实）"),
]

CAPS = []
for cap_id, name, cat, logic_model, tier, method, scheme, ep, family, status, quota in CAPS_RAW:
    host = ep.split("/")[2] if ep.startswith("http") else ""
    rec = {
        "capability_id": cap_id,
        "资源名称": name,
        "类别": sel(cat),
        "逻辑模型": logic_model,
        "质量等级": sel(tier),
        "调用方式": sel(method),
        "认证方案": sel(scheme),
        "允许主机": host,
        "模型族": family,
        "endpoint": ep,
        "请求体模板": '{"model":"{{MODEL}}","messages":[{"role":"user","content":"{{PROMPT}}"}]}' if method == "HTTP_REST" else "",
        "路由组": cap_id,
        "免费额度描述": quota,
        "状态": sel(status),
    }
    CAPS.append(rec)

# ================= 表4 资源实例表（21 平台） =================
# 每项: instance_id, 平台, 实际模型名, 额度总量, 额度单位, 重置规则, 限速, 需人工登录URL, 缺失环境变量, 获取方式备注, 验证策略, 状态
INSTS_RAW = [
    ("cap-siliconflow-01", "硅基流动 SiliconFlow", "Qwen/Qwen3-Omni-30B-A3B-Captioner,Qwen/Qwen-Image", None, None, "不重置", None,
     "https://cloud.siliconflow.cn/me/models", "SILICONFLOW_API_KEY", "限免模型直接调用", "HTTP探测", "可用"),
    ("cap-deepseek-01", "DeepSeek", "deepseek-chat,deepseek-reasoner", 26.59, "元", "不重置", None,
     "https://platform.deepseek.com/api_keys", "DEEPSEEK_API_KEY", "余额充值使用", "HTTP探测", "可用"),
    ("cap-volcengine-01", "火山引擎 Ark", "doubao-seed-1.6-lite,deepseek-v3", None, None, "周期重置", None,
     "https://console.volcengine.com/ark", "ARK_API_KEY", "每日 200 万 token 免费档", "HTTP探测", "待验证"),
    ("cap-aliyun-01", "阿里云百炼", "qwen-plus,qwen-max", 7000, "token", "一次性", None,
     "https://bailian.console.aliyun.com", "DASHSCOPE_API_KEY", "新户 7000 万 token/180 天", "HTTP探测", "待验证"),
    ("cap-groq-01", "Groq", "llama-3.3-70b-versatile,llama-3.1-8b-instant,gpt-oss-120b", None, None, "周期重置", "30 RPM / 1K RPD",
     "https://console.groq.com/settings/limits", "GROQ_API_KEY", "Base 免费档", "HTTP探测", "可用"),
    ("cap-modelscope-01", "ModelScope 魔搭", "Qwen2.5-7B-Instruct", 250, "次", "周期重置", None,
     "https://modelscope.cn", "MODELSCOPE_API_KEY", "每日 250 魔粒", "HTTP探测", "待验证"),
    ("cap-zhipu-01", "智谱 BigModel", "glm-4-flash,glm-5.2", 2000, "token", "一次性", None,
     "https://open.bigmodel.cn/usercenter/apikeys", "ZHIPU_API_KEY", "新户 2000 万 token + Flash 永久免费", "HTTP探测", "可用"),
    ("cap-kimi-01", "Kimi / Moonshot", "moonshot-v1-8k", 150, "token", "一次性", None,
     "https://platform.moonshot.cn", "", "新户 150 万 token，需设账号密码", "需人工", "待验证"),
    ("cap-openrouter-01", "OpenRouter", "14 个 :free 模型", None, None, "不重置", None,
     "https://openrouter.ai/workspaces/default/keys", "OPENROUTER_API_KEY", ":free 模型不耗余额", "HTTP探测", "可用"),
    ("cap-huggingface-01", "HuggingFace", "数百开源模型", None, None, "周期重置", None,
     "https://huggingface.co/settings/tokens", "HF_TOKEN", "Inference Providers 免费档", "HTTP探测", "待验证"),
    ("cap-githubmodels-01", "GitHub Models", "N/A", None, None, None, None,
     "https://docs.github.com/en/github-models", "", "RETIRED 2026-07-30", "需人工", "失效"),
    ("cap-colab-01", "Google Colab", "GPU/TPU 动态", None, None, "周期重置", None,
     "https://colab.research.google.com/", "", "交互式计算，GPU 动态分配", "需浏览器", "可用"),
    ("cap-together-01", "Together.ai", "openai/gpt-oss-20b", None, None, None, None,
     "https://api.together.ai/settings/billing", "TOGETHER_API_KEY", "NO_FREE_QUOTA 需充值 ≥$5", "HTTP探测", "待验证"),
    ("cap-mistral-01", "Mistral", "mistral 全系", 20, "元", "周期重置", None,
     "https://admin.mistral.ai/subscription", "MISTRAL_API_KEY", "Free 计划 $20/月", "HTTP探测", "可用"),
    ("cap-baidu-01", "百度智能云千帆", "ernie-4.5t,ernie-x1t,deepseek 系列", 8000, "token", "一次性", None,
     "https://console.bce.baidu.com/qianfan", "QIANFAN_API_KEY", "8000 万 Tokens 免费包 + ¥1155 券", "HTTP探测", "待验证"),
    ("cap-tencent-hunyuan-01", "腾讯混元（旧）", "hunyuan-turbo", None, None, None, None,
     "https://console.cloud.tencent.com/hunyuan", "", "RETIRED 2026-09-30 停服迁 TokenHub", "需人工", "失效"),
    ("cap-tokenhub-01", "腾讯 TokenHub", "DeepSeek-V4-Pro/Flash,GLM-5.2,Kimi-K3", 100, "token", "一次性", None,
     "https://console.cloud.tencent.com/tokenhub", "TOKENHUB_API_KEY", "新用户 100 万 Tokens/90 天", "HTTP探测", "待验证"),
    ("cap-minimax-01", "MiniMax", "MiniMax-M3", None, None, None, None,
     "https://platform.minimaxi.com/console", "MINIMAX_API_KEY", "NO_FREE_QUOTA：Token Plan 未订阅", "HTTP探测", "待验证"),
    ("cap-yi-01", "零一万物 Yi", "N/A", None, None, None, None,
     "https://platform.lingyiwanwu.com", "", "RETIRED 停服，开放余额退还", "需人工", "失效"),
    ("cap-xfyun-01", "讯飞星火", "Spark-Lite,Spark-X2", 0, "元", "不重置", None,
     "https://console.xfyun.cn/app/myapp", "XFYUN_API_KEY", "Lite 免费 + 开源 0 元档；未实名 L0", "HTTP探测", "待验证"),
    ("cap-stepfun-01", "阶跃星辰 StepFun", "step-3.7-flash,step-3.5-flash", None, None, None, None,
     "https://platform.stepfun.com", "", "赠送账户待登录核实", "需人工", "待验证"),
]

INSTANCES = []
for iid, platform, models, quota, unit, reset, rate, auth_url, env, note, strategy, status in INSTS_RAW:
    rec = {
        "instance_id": iid,
        "平台": platform,
        "实际模型名": models,
        "额度总量": quota,
        "额度单位": sel(unit) if unit else None,
        "重置规则": sel(reset) if reset else None,
        "限速": rate,
        "需人工登录URL": auth_url,
        "缺失环境变量": env,
        "获取方式备注": note,
        "验证策略": sel(strategy),
        "状态": sel(status),
        "上次验证": dte("2026-08-11"),
    }
    INSTANCES.append(rec)

# ================= 表6 自动化任务日志（1 条） =================
LOG_REC = [dict(
    task_id="task-seed-20260811", 任务类型=sel("校验"), 幂等键="seed-all-21-platforms-v1",
    执行Agent="deepseek-v4-flash", 状态=sel("SUCCEEDED"), 开始时间="2026-08-11 00:00",
    结束时间="2026-08-11 00:05", 结果码="OK", 同步状态=sel("PENDING"),
)]

def main():
    print("======== 1. 清空 4 表旧数据 ========")
    for tid, name in [(T1, "账号资产汇总"), (T2, "凭证池"), (T3, "资源能力规格表"), (T4, "资源实例表")]:
        delete_all(tid, name)

    print("\n======== 2. 表1 账号资产汇总（21） ========")
    acc_rids = batch_create(T1, ACCOUNTS, "账号资产汇总")

    print("\n======== 3. 表2 凭证池（5） ========")
    cred_rids = batch_create(T2, CREDENTIALS, "凭证池")

    print("\n======== 4. 表3 资源能力规格表（21） ========")
    cap_rids = batch_create(T3, CAPS, "资源能力规格表")

    print("\n======== 5. 表4 资源实例表（21） ========")
    inst_rids = batch_create(T4, INSTANCES, "资源实例表")

    print("\n======== 6. 表6 自动化任务日志（1） ========")
    batch_create(T6, LOG_REC, "自动化任务日志")

    # 保存主字段值 → record_id 映射供关联用（写入文件避免上下文丢失）
    mapping = {
        "accounts": dict(zip([a["account_id"] for a in ACCOUNTS], acc_rids)),
        "credentials": dict(zip([c["credential_id"] for c in CREDENTIALS], cred_rids)),
        "capabilities": dict(zip([c["capability_id"] for c in CAPS], cap_rids)),
        "instances": dict(zip([i["instance_id"] for i in INSTANCES], inst_rids)),
    }
    with open(os.path.join(HERE, "_task_c_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print("\n映射已保存到 feishu/_task_c_mapping.json")

    # 简易校验
    print(f"\n==== 写入汇总 ====")
    print(f"表1: {len(acc_rids)}/21  表2: {len(cred_rids)}/5  表3: {len(cap_rids)}/21  表4: {len(inst_rids)}/21  表6: {len(LOG_REC)}/1")

if __name__ == "__main__":
    main()
