# -*- coding: utf-8 -*-
"""迁移免费资源旧表 6 条 → v0.3 表3(资源能力)/表4(资源实例)
旧字段 → 新字段映射（headers 含 ${API_KEY} 模板丢弃，改 auth_scheme+allowed_hosts）
"""
import json, subprocess, os

BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
NODE = r"D:\Program Files\nodejs\node.exe"
RUN_JS = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@larksuite\cli\scripts\run.js")
TABLE3 = "资源能力规格表"
TABLE4 = "资源实例表"

def lark(*args):
    p = subprocess.run([NODE, RUN_JS] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(f"EXIT {p.returncode}: {p.stderr[:1500]}")
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        print("RAW:", p.stdout[:800])
        return None

def batch_create(table, records):
    """批量写记录，records 为 [ {字段名: CellValue}, ... ]"""
    body = {"create_records": records}
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_migrate_batch.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    d = lark("base", "+record-batch-create", "--base-token", BASE_TOKEN,
             "--table-id", table, "--as", "user", "--json", "@_migrate_batch.json")
    if d and d.get("ok"):
        rid = d.get("data", {}).get("record_id_list", [])
        print(f"  → 写入 {len(rid)} 条到 [{table}]", rid[:3])
        return rid
    print("  ✗ 写入失败:", json.dumps(d, ensure_ascii=False)[:800] if d else "无返回")
    return []

# ---------- 旧记录（取自 free_resources_dump.json） ----------
# 每条: (resource_id, status, endpoint, models_list, exec_type, human_auth_url, env, payload, headers)
OLD = [
    ("api_siliconflow_deepseek", "READY_API",
     "https://api.siliconflow.cn/v1/chat/completions",
     "deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-R1,Qwen/Qwen2.5-7B-Instruct",
     "HTTP_REST", "https://cloud.siliconflow.cn/account/ak",
     "SILICONFLOW_API_KEY",
     '{"model":"deepseek-ai/DeepSeek-R1","messages":[{"role":"user","content":"${PROMPT}"}]}',
     '{"Authorization":"Bearer ${SILICONFLOW_API_KEY}","Content-Type":"application/json"}'),
    ("api_zhipu_glm4", "READY_API",
     "https://open.bigmodel.cn/api/paas/v4/chat/completions",
     "glm-4-flash",
     "HTTP_REST", "https://open.bigmodel.cn/usercenter/apikeys",
     "ZHIPU_API_KEY",
     '{"model":"glm-4-flash","messages":[{"role":"user","content":"${PROMPT}"}]}',
     '{"Authorization":"Bearer ${ZHIPU_API_KEY}","Content-Type":"application/json"}'),
    ("gpu_colab_t4", "READY_BROWSER",
     "https://colab.research.google.com/#create=true",
     "NVIDIA_T4_16GB",
     "OPENCLI_BROWSER", "https://colab.research.google.com/",
     "NONE_USES_CHROME_SESSION",
     '{"opencli_cmd":"opencli browser ms open \\"https://colab.research.google.com/#create=true\\"","action":"select_T4_gpu"}',
     '{"Cookie":"<CHROME_SESSION_COOKIE>"}'),
    ("gpu_kaggle_kernels", "READY_BROWSER",
     "https://www.kaggle.com/code",
     "NVIDIA_P100,NVIDIA_T4_X2",
     "OPENCLI_BROWSER", "https://www.kaggle.com/",
     "NONE_USES_CHROME_SESSION",
     '{"opencli_cmd":"opencli browser ms open \\"https://www.kaggle.com/code\\"","action":"new_notebook_P100"}',
     '{"Cookie":"<CHROME_SESSION_COOKIE>"}'),
    ("gpu_huggingface_zerogpu", "READY_BROWSER",
     "https://huggingface.co/spaces",
     "RTX_Pro_6000",
     "OPENCLI_BROWSER", "https://huggingface.co/settings/tokens",
     "HF_TOKEN",
     '{"decorator":"@spaces.GPU","hardware":"ZeroGPU_RTX_Pro_6000"}',
     '{"Authorization":"Bearer ${HF_TOKEN}"}'),
    ("pack_github_student", "NEEDS_HUMAN_AUTH",
     "https://education.github.com/pack",
     "Copilot_Claude_3_5_Sonnet,Copilot_GPT4o",
     "CLI_TOOL", "https://education.github.com/pack",
     "GITHUB_STUDENT_AUTH",
     '{"feature":"github_copilot_free","status_check":"vscode_extension_auth"}',
     "{}"),
]

def host_of(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc

def main():
    # 表3 能力记录（6 条）
    caps = []
    for rid, status, ep, models, exectype, auth_url, env, payload, headers in OLD:
        cap_id = "cap-" + rid
        # 认证方案：含 Bearer → bearer；纯浏览器 → none
        scheme = "bearer" if "Bearer" in headers else ("none" if "CHROME_SESSION_COOKIE" in headers or headers == "{}" else "bearer")
        category = "LLM API" if exectype == "HTTP_REST" and "gpu" not in rid else ("云GPU" if "gpu" in rid else "其他")
        # 逻辑模型取 models 首项（逗号分隔第一个）
        first_model = models.split(",")[0]
        rec = {
            "capability_id": cap_id,
            "资源名称": rid,
            "类别": category,
            "逻辑模型": first_model,
            "调用方式": exectype,
            "认证方案": scheme,
            "允许主机": host_of(ep),
            "模型族": first_model.split("/")[0] if "/" in first_model else first_model,
            "endpoint": ep,
            "请求体模板": payload,
            "路由组": cap_id,
            "状态": "可用",
        }
        caps.append(rec)

    print("== 写入表3 资源能力规格表 ==")
    cap_rids = batch_create(TABLE3, caps)

    # 表4 实例记录（6 条，对应 6 能力）
    instances = []
    for i, (rid, status, ep, models, exectype, auth_url, env, payload, headers) in enumerate(OLD):
        inst_id = rid + "-01"
        cap_id = "cap-" + rid
        rec = {
            "instance_id": inst_id,
            "平台": rid.split("_")[1] if "_" in rid else rid,
            "实际模型名": models,
            "缺失环境变量": env if env != "NONE_USES_CHROME_SESSION" else "",
            "需人工登录URL": auth_url,
            "获取方式备注": f"源自旧表 {rid}（{status}）",
            "验证策略": "需人工" if status == "NEEDS_HUMAN_AUTH" else ("需浏览器" if exectype == "OPENCLI_BROWSER" else "HTTP探测"),
            "状态": "待验证",
        }
        instances.append(rec)

    print("== 写入表4 资源实例表 ==")
    inst_rids = batch_create(TABLE4, instances)

if __name__ == "__main__":
    main()
