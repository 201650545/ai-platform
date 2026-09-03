# 阶段5 验收 wire 证据清单（持续更新，2026-08-29）

依据：S5-PIPELINE-DESIGN-2026（Claude Sonnet 5 High 兜底裁定）Q9 九条验收判据。
纪律：禁人工压力/烧 token 测试（用户 2026-08-29 明令），全部证据来自真实运行
wire 记录或单测级证明；单元测试 27 例见 tests/test_control_plane_stage5.py。

## 一、实施落点

| Claude 裁定项 | 落地 | 提交 |
|---|---|---|
| Q2 单实例文件租约 | lease.py：O_CREAT\|O_EXCL + 30s 心跳线程 + 150s 陈旧 + 原子接管；3110/3111 | 932c6c2 |
| Q4 ①fetch 退避 | sync.py：60s×2 上限 1800s ±20% 抖动 | 932c6c2 |
| Q4 ②validate 熔断 | 同一原始输入哈希连续 3 次失败 → halted + 3205，仅 --clear-halt 解除；halted 期只 fetch 探活 | 932c6c2 |
| Q4 ③ACK 超时 | 同 candidate 短固定重试（loop 节奏），连续 3 次或 24h 回滚 6 次 → 3204（去抖 10min） | 932c6c2 |
| Q5 防振荡 v1 | noop_same_sha + 回滚冷却 5×loop + 最小发布间隔 60s；代际上限/K 稳定门明确不做 | 932c6c2 |
| Q6 重启恢复 | 无特殊逻辑；启动 halted 保持 halted | 932c6c2 |
| Q7 观测 | state.py：control_plane_state.json 原子覆写 + control_plane.log JSONL 512KB 轮转 + alert 文件 + 事件 3201-3205（源 API3100ControlPlane） | 932c6c2 |
| Q3 watchdog | watchdog_control_plane.ps1 + 计划任务 WatchdogControlPlane（SYSTEM/5min/允许电池）；3203 禁用告警仅记录（必改②）；休眠唤醒 5 分钟保护（风险#2） | 932c6c2（脚本） |
| Q8 范围边界 | per-key 解析与渠道级 gating 全部 defer，维持 channel_name_mapped | 见 STATE |

## 二、Q9 逐条 wire 证据

1. **双实例启动拒绝（3110）**：✅ **wire 已取得**——用户任务 pid 34608 持锁中，手动起
   第二 `--loop` 实例（17:50:49）：`exit_code=3110 lease occupied by pid=34608`，不空转；
   control_plane.log `lease_refused` + 3201 alert 文件
   alerts/lease_conflict_20260829T175049.json 双落盘。注：3201 的 Windows 事件日志缺席，
   系 loop 侧 eventcreate 为 best-effort（非提权用户上下文），alert 文件+JSONL 为主通道。
2. **陈旧租约接管 / 失去租约**：✅ **wire 已取得（两条）**——
   ① 失去租约：手动 loop（pid 16572）运行中 lease.lock 被移除 → 心跳线程下一周期
   `lease_lost`（12:18:42）→ 主循环 `exit_code=3111 lease lost` 干净退出。
   ② 陈旧接管：任务实例 pid 34608 被 Stop-ScheduledTask 突然终止（17:52:47，锁残留），
   重启后新实例（18:00:55）`lease_takeover stale=true prev_pid=34608
   last_heartbeat_age_s=515` → `lease_acquire_after_takeover`（pid 41232）健康 tick。
3. **毒 candidate 熔断（halted+3205）**：单测级 3 例
   （test_validate_circuit_halts_after_3_same_input / test_input_change_resets_counter /
   test_halted_fetch_only_never_validates）。wire 级：真实畸形候选需上游 Feishu 侧注入，
   为不污染生产数据源，留待真实 validate 失败自然发生（3205 自动触发）或用户授权受控注入。
   已配套 pending_vf 强制全量重算修正（revision 去重不会饿死熔断计数）。
4. **ACK 超时回滚+冷却链**：单测 4 例（rolled_back 冷却/重试/升级/超阈值停止）；
   wire 级复用阶段4 判据7 手法，本次未发布（R5 阻塞），留待首次真实发布时顺带取证。
5. **watchdog 端到端告警**：✅ **wire 已取得**——事件源 API3100ControlPlane 真实告警：
   服务时代 `state_stale E3202`（15:52/16:22/16:52/17:27，pid=1244 状态文件 21-23 分钟
   未更新）；17:42:04 `heartbeat_stale E3202`「用户已登录但 ControlPlaneLoop 任务未运行
   （State=Ready）」——正是服务移除后、任务启动前的空窗，任务感知分支实战命中。
   30 分钟同 kind 去抖实测生效（17:52 故意停任务后 17:57 周期无重复告警）。
6. **重启恢复（正常态 noop）**：✅ **wire 已取得**——服务移除后启动用户任务（17:47:20
   lease_acquire pid=34608）：fetch 成功（用户态 lark-cli UAT 可用）→ revision 未变
   → `last_run_result=noop`、fetch_failures=0（17:48:36 state 文件）；陈旧接管重启
   （18:00:55 pid=41232）同样恢复 noop 节奏（tick 1/2）。
7. **重启恢复（halted 保持）**：单测覆盖 _tick_halted / clear-halt；wire 级同 3。
8. **退避曲线真实观测**：✅ **wire 已取得**——SYSTEM 服务期 fetch 因 UAT 不可达连续失败，
   control_plane.log：n=1 next_backoff_s=60 → n=2 next_backoff_s=120（12:20:53/12:21:47），
   服务 stdout `{"tick": 2, "wait_s": 120}` 实证倍增；后续 n=12..15 封顶
   next_backoff_s=1800 实证上限。
9. **NSSM 依赖顺序**：不适用（见下——loop 已不依赖网关排序， DependOnService 随 NSSM
   方案一并取消；发布 ACK 仅在发布时需要网关，且有超时重试+3204 兜底）。

**附：用户态 fetch 成功实证（DPAPI 变更的闭环）**：同一 lark-cli、同一 Base token，
SYSTEM 服务态 `token_missing need_user_authorization`（n=1..15），用户会话态
（17:48:36）fetch 成功 → noop。结构性结论：控制面 loop 必须随用户会话运行。

## 三、方案变更（Claude Q1 → 用户会话计划任务）

- **实证**：NSSM SYSTEM 服务（AppEnvironmentExtra USERPROFILE/HOME 指向用户 profile）
  下 lark-cli 二进制可运行，但 `token_missing need_user_authorization`——UAT 存储绑定
  用户（DPAPI/用户态加密，config.json 仅 app 凭证与 user openid，无 token 文件可迁移）。
- **变更**：API3100ControlPlane NSSM 服务移除；loop 改为登录触发计划任务
  **ControlPlaneLoop**（pythonw -m control_plane.sync --loop 60 --daemon，WorkingDirectory
  D:\ai-resource-hub，无执行时限、允许电池、IgnoreNew）。watchdog 缺锁分支同步改为
  「有人登录且任务未运行才告警；无人登录=预期停跑」。
- **损失评估**：DependOnService 启动排序对 loop 无实际意义（loop 不依赖网关进程；
  发布 ACK 超时本就有重试+3204）。崩溃自愈由计划任务+watchdog+租约接管覆盖。
- **保留**：服务名 API3100ControlPlane 作为事件源（3201-3205）继续使用。

## 四、运行时现状与韧性配置

- **ControlPlaneLoop**（登录触发，pythonw --loop 60 --daemon，无 --publish）：
  RestartCount=3 / RestartInterval=1min（崩溃自重启；3110 早退重试可跨过 150s 陈旧窗口
  触发接管）+ 无执行时限 + 允许电池 + IgnoreNew。
- **WatchdogControlPlane**（SYSTEM，5min）：任务感知版实战验证（17:42:04 告警）。
- **调优备忘（非缺陷）**：fetch 失败退避封顶 1800s > watchdog state_stale 阈值 20min，
  长退避期会出现 state_stale 告警噪音（服务时代 15:52~17:27 即此模式）。真实发布开启后
  如确认扰人，二选一：阈值调至 35min，或进入退避等待时额外刷新 state.updated_at。

## 五、遗留

- 真实 candidate 发布（R5 dashscope/qwen3.8-flash 拍板）→ 发布后顺带补 Q9#4 wire。
- GPT 镜像恢复后对阶段5 实施做交叉复核（问诊包+本报告归档 docs/ai-advice/）。
- 拔电+reboot 验收（用户亲手）。
- loop 侧 3201/3204/3205 的 Windows 事件通道为 best-effort（非提权 eventcreate 可能
  失败，今日 3201 实测缺席）；alert 文件 + JSONL 为主通道，如需强事件可由 watchdog
  扫描 alerts/ 目录代发（暂缓，待真实告警出现再定）。
