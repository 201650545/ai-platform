# Claude 问诊回复 — 记忆线/记忆路由（多 Agent 多项目，交叉校验 #2）

> 问诊对象：多 Agent 多项目共享记忆的"记忆线"设计——读写不串台、路由机制、堆积处理、落地形式
> 时间：2026-08-14 ｜ 模型：Claude Sonnet 5（claude.ai，High 思考）
> 执行：v4 Flash ｜ 提示词：内嵌版（无链接）
> 输入来源：AI 搜索网关（元宝）已给出命名空间隔离方向，本条为 Claude 独立意见
> 状态：待与 GPT 镜像回复合并后定稿方案

---

一句话结论
融合缓存分层与项目隔离，以工作目录自动路由实现记忆无串台。

融合缓存分层与项目隔离，以工作目录自动路由实现记忆无串台。
一句话结论

用 "CPU 缓存分层做物理隔离 + 人类情景记忆/语义记忆做内容分类"的混合模型：L1=当前会话上下文（不落盘）、L2=项目专属记忆（物理路径隔离，你现有的 STATE/DECISIONS/CHANGELOG）、L3=跨项目共享的稳定事实（IDENTITY.md，低频、人工审核写入）；"当前项目"不靠 Agent 自报,而是由启动时的物理路径/环境变量决定,hook 只做机械校验,不做语义判断。

一、记忆线数据结构

放弃"单仓库单目录、靠文件名区分项目"的隐式结构,改成路径即身份:

ai-hub-memory/
├── global/
│   ├── IDENTITY.md          # 跨项目稳定事实,人工/低频写入,不给 Agent 自动写权限
│   └── ROUTING.json         # 项目注册表(下面详解)
│
├── projects/
│   ├── teaching/
│   │   ├── STATE.md         # 当前快照,有行数上限
│   │   ├── DECISIONS.md     # 只增不删,append-only
│   │   ├── CHANGELOG.md     # 当前季度滚动日志
│   │   ├── LINKS.json       # 显式声明对其他项目线的引用(见下)
│   │   ├── index.json       # 轻量索引,可重建,非唯一真源
│   │   └── archive/
│   │       └── 2026-Q1.md
│   ├── courseware/
│   │   └── (同结构)
│   └── memory-system/
│       └── (同结构)
│
└── _shared/
    ├── hooks/                # pre-commit / pre-write 校验
    └── scripts/
        └── memctl.sh         # 唯一读写入口

ROUTING.json(单一注册表,决定"项目"这个概念本身):

json
{
  "teaching":     { "path": "projects/teaching",     "prefix": "TEACH" },
  "courseware":   { "path": "projects/courseware",    "prefix": "CWARE" },
  "memory-system":{ "path": "projects/memory-system",  "prefix": "MEMSYS" }
}

S-ID 在你现有基础上加项目前缀(TEACH-2026-0142),这样即使未来合并归档,单看 ID 就知道归属线,不依赖目录也能追溯。

二、读写路由机制(核心,不靠 Agent 自觉)

关键原则:"当前项目"是环境事实,不是 Agent 的自我认知。Agent 说自己在哪个项目不算数,路径/环境变量算数。

确定优先级(严格顺序,fail-closed):

启动脚本注入的环境变量 CURRENT_PROJECT(由你手动切换 Agent 时通过 start-agent.sh teaching 设置,这一步是唯一允许人工介入的地方)
若无该变量,退化到 cwd 路径前缀匹配 ROUTING.json 里的 path
两者都拿不到 → 拒绝写入,拒绝读取,报错要求人工指定,绝不"猜一个默认项目"

读: 所有读操作走 memctl.sh read,该脚本只 cat $CURRENT_PROJECT 对应目录下的文件 + global/IDENTITY.md(只读)。跨项目读默认禁止;如果 memory-system 项目确实需要知道 teaching 项目的某个决策,必须在 memory-system/LINKS.json 里显式声明:

json
{ "refs": [{ "project": "teaching", "sid": "TEACH-2026-0087", "reason": "复用课件生成的分级标准" }] }

这样跨线引用是可审计的 git diff,而不是 Agent 运行时静默串读。

写: 所有写操作走 memctl.sh write,hook 做三件机械校验,不做语义判断:

目标文件路径是否在 $CURRENT_PROJECT 对应目录下 → 不是则拒绝
commit message / S-ID 前缀是否与 $CURRENT_PROJECT 的 prefix 一致 → 不一致则拒绝
global/ 下的文件默认拒绝 Agent 写入(只有显式 --allow-global 标志 + 人工确认才放行)

这套机制的价值在于:即使 Agent 在对话中"以为"自己在处理教学项目,只要环境变量/路径显示的是课件项目,它物理上就写不进教学线,不依赖它记住或承认这一点。

三、堆积处理(遗忘/归档/分级)

对应人类记忆的"巩固-衰减"机制,但落地成事件触发而非定时任务(避免你不想要的调度平台):

层级	类比	策略
STATE.md	工作记忆	有行数上限(如 500 行),写入时 hook 检测超限,触发在 pre-commit 里的 compact 脚本,把被覆盖的旧状态压成一行摘要挪进 archive
CHANGELOG.md	短期情景记忆	按季度滚动,超过当前季度的条目自动挪入 archive/YYYY-Qn.md
DECISIONS.md	语义记忆/长期巩固	只增不删,永不压缩、永不归档——这是低容量高价值信息,直接对标人脑"陈述性知识"层
git log	深层存档	你不需要在活跃文件里保留完整历史,git 本身就是无限深的冷存储,git log --grep 随时可检索,archive 文件只需要保留可被 index.json 定位的摘要指针

index.json 定位为可重建的缓存,不是真源——建议它由脚本扫描目录 + git log 自动生成,而不是手工维护。这样即使某次合并把它写坏了,重新跑一次生成脚本就能恢复,不会成为单点故障。

四、落地形式建议

混合式,职责二分:

脚本/hook 负责"必须机械正确"的部分:路由判定、读写隔离、超限触发归档、S-ID 前缀校验。这类逻辑不能依赖 LLM 的"理解和自觉",必须是确定性代码。
Skill(SKILL.md)负责"需要判断"的部分:什么情况该开新 S-ID、DECISIONS.md 该怎么措辞、何时该往 LINKS.json 里加跨线引用。这是给任意一个 Agent 实例看的操作手册,教它怎么调用 memctl.sh、怎么解读 ROUTING.json,而不是让它自己发明协议。

具体建议每个 Agent 启动时的唯一入口是:

bash
./start-agent.sh teaching   # 设置 CURRENT_PROJECT,cd 到对应目录,加载对应 SKILL.md

一次会话只服务一个项目线,切换项目 = 重启会话,而不是同一个长会话里中途切换——这一点很关键,因为哪怕文件层面隔离得再干净,同一个对话上下文(L1)里残留的上一个项目的内容也无法被 hook 拦截。

五、风险
上下文残留是文件隔离解决不了的:如果你在同一个对话里跨项目切换而不重启 Agent 会话,L1(模型自身上下文)仍会混着两条线的信息。机制上的硬隔离只管文件读写,管不了模型"记不记得"上一轮说了什么——这是你必须靠"一会话一项目"的操作纪律弥补的部分,脚本做不到。
global/ 是唯一的共享可写区,也是唯一的冲突风险点:多个 Agent 并发操作时,IDENTITY.md/ROUTING.json 如果允许 Agent 自动写,会有并发冲突;建议这两个文件对 Agent 永远只读,任何变更走人工 PR。
fail-closed 的代价是偶尔"卡住":环境变量没设对时,系统会拒绝操作而不是猜测——这是有意为之(防止串台),但意味着你的启动脚本必须足够可靠,否则会频繁打断工作流。
index.json 若被当成真源而非缓存会腐化:一旦有人开始手工改它而不是靠脚本重建,它和实际文件会逐渐漂移,失去校验价值。

