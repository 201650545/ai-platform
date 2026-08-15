# M1 最小闭环调度器

单进程 + SQLite(WAL) + localhost base_url 代理。
多 canonical model × 多厂商实例 × 多凭证（免费/低价优先，额度耗尽自动切换）。

当前实例池（config.json，route_priority 升序 = 消耗顺序，免费/低价优先）：
- **deepseek-v4-flash**：ZenMux免费(1) → opencode-go(10) → 魔塔(20) → 商汤(30) → ZSCC(40) → 硅基(50,余额0跳过) → OpenRouter(60) → DeepSeek官方(70)
- **glm-5.2**：魔塔(20) → 商汤(30) → ZSCC(40) → 硅基(50,余额0跳过) → OpenRouter(60)
> 厂商 key 统一经 scheduler/credentials.json 读取（源自 C:/Users/郭永涛/.dsh/.credentials.yaml）；
> 硅基流动实测余额不足，已置 quota_remaining=0 直接跳过（免 402 白试）；
> 转发需带浏览器 UA（默认 urllib UA 会被 opencode.go/OpenRouter 等 403 拦截，已修复）。

> 模型名映射：canonical_model 是统一逻辑名（客户端请求名）；各厂商实际名不同，
> 由实例的 actual_model 字段在转发前改写（如 siliconflow 的 deepseek-ai/DeepSeek-V4-Flash、
> openrouter 的 deepseek/deepseek-v4-flash）。

## 快速开始

```bash
cd scheduler
python scheduler.py            # 默认 127.0.0.1:8789
python test_m1.py              # 三验收 + 附加验收（15 项断言）
```

## 三验收

| # | 场景 | 预期 |
|---|------|------|
| ① | 正常请求 | 路由到实例 A（priority 1） |
| ② | A 标 EXHAUSTED（额度耗尽） | 自动切 B，事件留 FAILOVER |
| ③ | 请求另一模型（gpt-5） | 404 model_not_found，拒绝偷换模型 |

附加：上游报 quota_exhausted 自动触发切换；stream=true 流式透传；事件留痕。

## 模块（对应方案书 §4.1）

- **Proxy**：`ThreadingHTTPServer`，127.0.0.1 代理 `/v1/chat/completions`（本地 base_url）
- **Router**：过滤（模型匹配/状态可用/未冷却/额度>安全余量）→ 排序（route_priority，剩余额度）
- **Provider Adapter**：`mock`（可编程错误，验收用）/ `openai-compatible`（真实转发，M3 接飞书后启用）
- **Quota Ledger**：SQLite 运行态，额度扣减 + 硬停止（低于安全余量即不再候选）
- **SQLite**：WAL 模式，`instances` + `events` 两表

## 错误分类

| 上游现象 | 分类 | 状态写入 | 动作 |
|---------|------|---------|------|
| quota_exhausted | EXHAUSTED | 额度耗尽 | 自动切同能力下一实例 |
| 429（非 quota） | COOLDOWN | 冷却中 +60s | 自动切 |
| 401/403 | CRED_INVALID | 失效 | 立即失败，不切 |
| model_not_found/404 | CONFIG_INVALID | 失效 | 立即失败，不切 |
| 5xx | RETRYABLE_5XX | 冷却中 +30s | 自动切 |
| 200 包错误（choices 缺失/finish_reason=error） | COOLDOWN | 冷却中 | 不重放 |

流式安全：切换决策发生在向客户端输出第一字节前；已透传即不再重放。

## Secret 边界

- 凭证只从本地 `credentials.json`（受信平面）读取，**不入 SQLite、不进飞书**
- 日志 detail 白名单化（instance/model/kind/status），不记录请求体与 Authorization
- `openai-compatible` adapter 用 `Bearer <key>` 注入上游

## 管理端点（curl）

```bash
curl http://127.0.0.1:8789/healthz                 # 存活 + 实例数
curl http://127.0.0.1:8789/__admin/instances        # 实例运行态
curl http://127.0.0.1:8789/__admin/events           # 事件日志
curl -X POST http://127.0.0.1:8789/__admin/instances/mock-a-01/status \
  -H "Content-Type: application/json" -d '{"status":"额度耗尽"}'
```

## M2/M3 状态（已落地）

- **M2 数据桥真源同步**（`sync.py`）：读数据桥产物（manifest 字节哈希校验）→ 字段映射 SQLite；退役能力过滤；`credential_id`/`route_priority` 走本地 `credential_map.json` 安全平面。用法：`python sync.py [--remote]` 后再启动调度器。
- **M2 并发路由**：per-instance 原子预留（`reserve`/`release`）+ 原子扣减（`debit_atomic`）+ 启动清理残留预留。
- **M3 真实上游 + 流式逐块**：`call_stream` SSE 逐行读转发（readline，不整读）；`stream_prepare` 流式前置预留。

## 已知偏差（待办）

1. **真实 key 空占位**：`credentials.json` 目前只有 `siliconflow-main`/`deepseek-main` 两个空 key 占位。真实 key 值需用户填入本地 `credentials.json`（受信平面）后，`openai-compatible` 真实转发才可用。
2. 精确额度初始值在本地安全平面（数据桥只给区间）；运行时 SQLite 扣减为准。
3. 调度器需先 `python sync.py` 同步数据桥产物，再启动 `python scheduler.py`。