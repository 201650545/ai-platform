S5-PIPELINE-DESIGN-2026 阶段5（资源接入流水线）设计问诊。请全文实读后再裁定；回复首行与末行都原样输出令牌 S5-PIPELINE-DESIGN-2026，并按文末输出格式作答。本文所有材料已整份内嵌，你无需访问任何外网链接。

== 背景与角色 ==
你在 2026-08-29 完成阶段4（资源控制平面）终审，裁定有条件关账；两项必改已于同日落地并归档（credential_refs 语义 resolved→mapped/unmapped+semantics=channel_name_mapped，ai-hub 50b7be6；判据7 最小 wire 演练：非生产配对 (modelscope, Qwen/Qwen2.5-72B-Instruct) 发布 active+过期→route-plan resource_expired→空代恢复 resource_block=null，PID 36440 全程不变，报告 ai-resource-hub e177317）。判据4/7 提升 PASS，阶段4 已正式关账。你的 R6 原文裁定：「阶段5 严格先于阶段6；先把现有一次性控制平面变成可靠的持续供给链：sync --loop 进正式 scheduler、单实例/租约约束、进程 watchdog、失败退避与抖动、连续失败告警、publish ACK/rollback 观测、禁止多 writer、重启后的 generation/last-good 恢复，以及避免坏上游数据形成高速 publish/rollback 振荡」。本次问诊=给阶段5 出设计意见：逐题给推荐方案与理由，指出我未列出的风险。实现仍由 QoderWork Agent 于获你裁定后执行（延续授权「你都完成啊」）。

== A. 现状事实（阶段4 关账态） ==
A1. 运行环境：Windows 单机；网关=NSSM 服务 API3100Gateway 监听 127.0.0.1:3100（专用账户，改动服务需 UAC 提权，Exit 行为已映射 3102 绑定失败/3103 存储未就绪/3104 配置错误，默认崩溃自愈 Restart）；已有计划任务 Watchdog3100Alert（SYSTEM/每5分钟/允许电池）做 healthz 探测→事件日志 3105+告警文件+30 分钟去抖。资源数据目录 D:\项目\data\search_gateway\（live=gateway_resources.json、last_good、resource_reload.log 512KB rotate JSONL、resource_history/<gen>.json 保留20份）。
A2. 控制面（D:\ai-resource-hub\control_plane，资源仓）：fetch→dedup→normalize→compile→validate→publish 单链已通。publish.py：validate fail-closed→canonical_sha256 相同 noop_same_sha 幂等→tmp.<pid>+fsync+os.replace 原子替换 live→前代归档→轮询 GET /api/resource-config/status（wait_ack 默认10s）直到 active_generation_id==新 gen；超时回滚前代字节或删残留；rollback --previous 可手动回退。sync.py：run_once 一次性；--publish 发布；--loop [秒] 默认 60s+0-10s 抖动常驻（异常不退出，但无退避曲线、无单实例约束、无 watchdog、无告警、无观测产物——这些正是阶段5 要补的）。
A3. 网关消费端：resource_config.py 热加载（stat→sha 去重→解析→二次校验→immutable snapshot 指针换→失败保持 last-good+fail_count）；status 端点免鉴权输出 active_generation_id/active_sha256/loaded_at/resource_count/last_reload_status/reload_count/fail_count/precedences/credential_refs{mapped,unmapped,semantics}；配对级 gating（客户端名优先、上游名兜底）+limits shadow 对照+capabilities 矩阵门，precedence 默认全保守（shadow/static=零行为变更）。
A4. 数据准入态：live=空 generation（0 资源=无 gating 基线）。真实 candidate 发布被 (dashscope, qwen3.8-flash) 飞书数据矛盾阻塞（你 R5 序：a 修正飞书 active>c 显式 quarantine>b local-skip；待用户/资源所有者拍板）。阶段5 基建必须先于真实 candidate 部署就位，即持续供给链先跑在"空代+noop"上。
A5. 纪律约束：禁人工压力/烧 token 测试（只许 wire 证据或真实使用自然落盘）；每步代码改动单独提交；GPT 评审意见须实读（令牌验证）。

== B. 请给设计意见的问题 ==
Q1. scheduler 形态：--loop 常驻化选哪种？a) 第二个 NSSM 服务（如 API3100ControlPlane，随 API3100Gateway 启动顺序依赖，同 Exit 码语义）；b) 计划任务开机自启（SYSTEM，复用 Watchdog3100Alert 注册套路）；c) 不做独立进程，把 sync 嵌进 :3100 网关进程内定时线程。考虑：单写者最简实现、重启顺序（控制面依赖网关 ACK 端点）、与现有 NSSM 生态一致性、崩溃自愈。
Q2. 单实例租约：文件锁（O_CREAT|O_EXCL 建 lock 文件含 pid+心跳 mtime，陈旧阈值后可接管）还是 Windows 命名互斥体？失去租约时进程应退出（哪个退出码）还是空转？接管语义怎么定才不会双写？
Q3. watchdog：新增计划任务（如 WatchdogControlPlane，SYSTEM/5分钟）探什么？进程存活/心跳 mtime 新鲜度/状态产物 gen 停滞（超过 N 倍轮询周期未换代=可疑）？告警复用事件日志 3105 套路还是新事件 ID？要不要顺带探 ACK 回滚频发？
Q4. 退避与抖动：连续失败时的间隔曲线建议（fetch 失败/validate 失败/ACK 超时三类是否区分？指数退避基值与上限？抖动区间？）；validate 连续失败（毒 candidate）要不要熔断成"停发+告警+人工介入"态？
Q5. 防振荡：坏上游数据造成 publish/rollback 高速抖动的守卫，最小集合是什么？候选：同 sha noop（已有）；ACK 回滚后强制冷却期；单位时间代际上限；候选内容稳定性门（连续 K 次 canonical_sha256 相同才允许发布）；最小发布间隔。哪些该进 v1，哪些过度设计？
Q6. 重启恢复：网关重启已有 last-good 链。控制面重启后第一轮该做什么（先 run_once 成功才发布 vs 直接发上次内存态 vs 立即全量 run_once+publish）？长停机后 gen 明显陈旧时的策略？要不要把"控制面自身状态"（最近成功 run/publish 时间、连续失败计数）落一个 control_plane_state.json 供重启恢复与 watchdog 共读？
Q7. 观测：publish/ACK/回滚/退避的观测产物放哪？控制面无 HTTP 端点——a) 只写独立 control_plane.log(JSONL rotate)；b) 状态文件 control_plane_state.json（单文件覆写，watchdog 与人共读）；c) 扩展网关 status 端点透传控制面状态。推荐哪个最小集合？哪些字段必须有？
Q8. 范围边界：阶段5 是否顺带做 per-key credential 真实解析（你 R3 曾说放阶段5）？还是维持 channel_name_mapped 口径、per-key 继续后置？渠道级 gating 语义（现在只做配对级）与飞书数据治理对齐是否继续 defer？请给明确裁决。
Q9. 验收判据：阶段5 关账需要哪几条 wire 判据（建议 6-10 条，含禁压测替代法）？例如：双实例启动第二把必拒、毒 candidate 熔断、ACK 超时回滚、watchdog 告警端到端、重启恢复、退避曲线实测。

== C. 输出格式 ==
首行：S5-PIPELINE-DESIGN-2026
第二部分：Q1-Q9 逐条（推荐方案+理由+关键参数建议值；你认为问错的题直接指出并给正题）
第三部分：我未列出但阶段5 必须考虑的风险清单
第四部分：总裁决（设计通过可实施 / 有条件通过列必改 / 需再问诊）与建议实施顺序
末行：S5-PIPELINE-DESIGN-2026
