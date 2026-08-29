"""控制平面配置：Base/表 allowlist + 字段 allowlist（污染防护第一门）。

飞书是业务数据源，本模块是编译链路的唯一配置真源。
任何新表/新字段必须先在此声明才能进入 fetch；敏感字段一律禁止读取。
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / "runtime" / "control-plane"
RAW_DIR = RUNTIME_DIR / "raw"
CANDIDATE_DIR = RUNTIME_DIR / "candidate"
REPORTS_DIR = RUNTIME_DIR / "reports"
STATE_DIR = RUNTIME_DIR / "state"

# lark-cli 路径可用 LARK_CLI 环境变量覆盖
LARK_CLI = os.environ.get(
    "LARK_CLI",
    r"C:\Users\郭永涛\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\lark-cli.cmd",
)

# 目标 Base（全网免费资源与自动化控制中心）
BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "StmDbTXQWaujshs9NpIc3UFpnAc")

# 阶段4允许读取的表：{表名: {table_id, kind}}
# kind: instances=资源主记录 / capabilities=能力 / accounts=凭证元数据 / channel_intel=渠道发现
TABLES = {
    "资源实例表":   {"table_id": "tbl8bKuwqP0Wl4d1",   "kind": "instances"},
    "资源能力规格表": {"table_id": "tbllAPtPd68uDTTj",  "kind": "capabilities"},
    "账号资产汇总":  {"table_id": "tblsrXWXX8GQ9hx4",  "kind": "accounts"},
    "模型资源总表":  {"table_id": "tbl5ONs0gzE7I5xI",  "kind": "channel_intel"},
}

# 字段 allowlist：只读这些列（从零构造，不做黑名单删除）
FIELD_ALLOWLIST = {
    "资源实例表": [
        "instance_id", "平台", "实际模型名", "所属能力", "状态", "路由优先级",
        "限速", "额度总量", "剩余额度快照", "安全余量", "额度单位", "重置规则",
        "额度重置日", "额度到期日", "配置版本", "验证策略", "缺失环境变量",
        "获取方式备注", "上次验证", "下次验证", "备注",
    ],
    "资源能力规格表": [
        "capability_id", "资源名称", "类别", "逻辑模型", "质量等级", "模型族",
        "协议版本", "请求模板版本", "调用方式", "adapter_id", "endpoint",
        "认证方案", "路由组", "允许主机", "健康探测", "状态", "实例列表", "免费额度描述",
    ],
    "账号资产汇总": [
        "account_id", "平台名称", "认证方式", "状态", "会话状态",
        "账号标识", "上次会话验证", "下次会话验证", "备注",
    ],
    "模型资源总表": [
        "渠道/活动名称", "渠道类型", "厂商/模型系", "具体模型", "能力",
        "核实状态", "是否免费", "网关落地状态", "免费额度", "API接入",
        "额度/价格", "截止时间", "有效期", "限制说明", "地区", "来源表",
        "官网链接", "落地证据/位置",
    ],
}

# 敏感字段黑名单：即使误入 allowlist 也强制剔除（双保险）
SENSITIVE_FIELDS = {
    "需人工登录URL", "验证指纹", "任务列表", "绑定手机", "浏览器Profile",
    "人工介入原因", "凭证ID", "密钥", "密码", "app_token", "app_secret",
    "credential", "api_key", "token", "secret", "access_token", "入口链接", "领取方式",
}


def allowed_fields(table_name):
    """某表最终允许读取的字段（allowlist 再剔除敏感字段）。"""
    return [f for f in FIELD_ALLOWLIST.get(table_name, []) if f not in SENSITIVE_FIELDS]


def ensure_runtime_dirs():
    for d in (RAW_DIR, CANDIDATE_DIR, REPORTS_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR
