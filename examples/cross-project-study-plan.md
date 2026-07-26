# 跨项目综合学习计划示范

> 本文件展示如何使用 Data Hub 的语义层和路由规则，从两个项目（英语学习和公考备考）中提取数据并制定综合学习计划。
>
> **重要：** 本文件是流程示范，不是实时建议。示例输出中的数据是基于数据结构的格式参考，不代表当前实际学习状态。

## 示范问题

```
请根据英语学习和公考项目，制定今天的综合学习计划。
```

## 执行流程

### 步骤 1：读取 catalog.json，识别学习项目

读取 `catalog.json`，查看所有项目的 `capabilities` 和 `domains`：

- `learning-english`：domains=[learning, language]，capabilities=[study_planning, review_prioritization, error_analysis, ...]
- `civil-service-exam`：domains=[exam, learning]，capabilities=[study_planning, error_analysis, exam_analysis, ...]

两个项目都具有 `study_planning` 能力，因此综合学习计划需要同时使用两个项目。

### 步骤 2：根据 study_planning capability 选择项目

查看 `routing.json` 中 `study_planning` 意图：

```json
{
  "candidate_projects": ["civil-service-exam", "learning-english"],
  "recommended_first_files": [
    "catalog.json",
    "projects/<slug>/summary.md",
    "projects/<slug>/agent-guide.md",
    "projects/<slug>/semantic.json"
  ],
  "recommended_tables": [
    "daily-plan", "study-tasks", "daily-study-plan",
    "competency-state", "knowledge-points", "vocabulary"
  ],
  "record_data_required": true
}
```

### 步骤 3：读取两个项目的 summary.md

读取以下文件理解项目用途：
- `projects/learning-english/summary.md`
- `projects/civil-service-exam/summary.md`

### 步骤 4：读取两个项目的 agent-guide.md

读取以下文件了解分析规则：
- `projects/learning-english/agent-guide.md`
- `projects/civil-service-exam/agent-guide.md`

### 步骤 5：读取 semantic.json

读取以下文件理解表和字段含义：
- `projects/learning-english/semantic.json`
- `projects/civil-service-exam/semantic.json`

### 步骤 6：找到计划、任务、事件和状态相关表

根据 semantic.json 中的表角色：

**英语项目相关表：**
| 表 | 角色 | 用途 |
|---|---|---|
| `daily-plan` | plan | 每日学习计划 |
| `study-tasks` | plan | 具体学习任务 |
| `vocabulary` | knowledge | 词汇复习调度 |
| `competency-state` | metric | 能力维度状态 |
| `error-remediation` | error_log | 顽固错误 |

**公考项目相关表：**
| 表 | 角色 | 用途 |
|---|---|---|
| `daily-study-plan` | plan | 每日学习计划 |
| `knowledge-points` | knowledge | 知识点复习调度 |
| `practice-records` | event_log | 刷题记录 |
| `exam-patterns` | analysis | 命题规律和复习优先级 |

### 步骤 7：只读取相关记录分片

根据推荐表列表，读取以下分片（不扫描全部记录）：

1. `projects/learning-english/tables/daily-plan/records-0001.json` — 筛选今日计划
2. `projects/learning-english/tables/study-tasks/records-0001.json` — 筛选今日待办任务
3. `projects/learning-english/tables/vocabulary/records-0001.json` — 筛选到期复习词
4. `projects/learning-english/tables/competency-state/records-0001.json` — 筛选到期测试维度
5. `projects/civil-service-exam/tables/daily-study-plan/records-0001.json` — 筛选今日计划
6. `projects/civil-service-exam/tables/knowledge-points/records-0001.json` — 筛选到期复习知识点
7. `projects/civil-service-exam/tables/exam-patterns/records-0001.json` — 筛选高优先级考点

### 步骤 8：说明使用了哪些数据

在输出计划时，明确列出数据来源：
- 数据同步时间（从 `status.json` 的 `last_success_at`）
- 是否 stale（从 `status.json` 的 `is_stale`）
- 各项目的记录数量
- 具体读取了哪些表的哪些分片

### 步骤 9：数据不足时明确说明

如果某些数据不足（如刷题记录仅 3 条），在计划中标注：
> 注意：英语学习会话仅有 3 条记录，无法进行趋势分析，相关建议仅供参考。

### 步骤 10：输出有时间分配、任务依据和优先级的计划

## 示例输出格式

```markdown
# 综合学习计划

**生成时间：** 2026-07-26
**数据同步时间：** 2026-07-26T08:17:00Z（英语）、2026-07-26T08:17:00Z（公考）
**数据状态：** 两个项目均正常（is_stale: false）

## 数据来源

| 项目 | 读取的表 | 记录数 | 说明 |
|---|---|---|---|
| learning-english | daily-plan | 9 | 筛选今日计划 |
| learning-english | study-tasks | 508 | 筛选计划日期=今日且未完成的任务 |
| learning-english | vocabulary | 6,000 | 筛选 next_review <= 今日的到期词 |
| learning-english | competency-state | 646 | 筛选 next_review_time <= 今日的到期维度 |
| civil-service-exam | daily-study-plan | N | 筛选今日计划 |
| civil-service-exam | knowledge-points | N | 筛选 next_review <= 今日的到期知识点 |
| civil-service-exam | exam-patterns | N | 筛选高复习优先级考点 |

## 今日计划

### 上午（08:00 - 12:00）

| 时间 | 任务 | 项目 | 依据 | 优先级 |
|---|---|---|---|---|
| 08:00-08:30 | 英语词汇复习（到期 N 词） | learning-english | vocabulary.下次复习 <= 今日 | 高 |
| 08:30-09:30 | 公考知识点复习（到期 N 个） | civil-service-exam | knowledge-points.下次复习 <= 今日 | 高 |
| 09:30-10:30 | 公考刷题（高频考点） | civil-service-exam | exam-patterns.复习优先级 = 高 | 中 |
| 10:30-12:00 | 英语阅读（选择文本） | learning-english | text-library.使用状态 = 可用 | 中 |

### 下午（14:00 - 18:00）

| 时间 | 任务 | 项目 | 依据 | 优先级 |
|---|---|---|---|---|
| 14:00-15:00 | 英语能力训练（到期维度） | learning-english | competency-state.下次复习时间 <= 今日 | 高 |
| 15:00-16:00 | 英语错误改进 | learning-english | error-remediation.是否已解决 = 否 | 中 |
| 16:00-18:00 | 公考真题练习 | civil-service-exam | practice-records 最近表现分析 | 中 |

### 晚上（19:00 - 21:00）

| 时间 | 任务 | 项目 | 依据 | 优先级 |
|---|---|---|---|---|
| 19:00-20:00 | 完成今日待办任务 | learning-english | study-tasks.状态 = 待办 | 高 |
| 20:00-21:00 | 总结与复盘 | 两个项目 | daily-plan / daily-study-plan | 低 |

## 注意事项

1. 数据是每小时同步的快照，非实时数据
2. 如计划执行中有新测验或复习，下次同步后数据会更新
3. 优先处理到期复习任务（高优先级），其次安排新学习内容（中优先级）

## 数据限制说明

- 英语 `study-sessions` 仅 3 条记录，无法分析学习会话趋势
- 英语 `error-remediation` 仅 8 条记录，错误模式分析仅供参考
- 以上计划基于 2026-07-26T08:17:00Z 的数据快照生成
```

## 路由测试

以下命令可用于验证路由逻辑是否正确：

```bash
# 验证语义配置
node scripts/validate-semantic.mjs

# 验证 AI 文档存在性
node scripts/validate-ai-docs.mjs

# 验证路由规则（通过检查 routing.json）
node -e "
const fs = require('fs');
const routing = JSON.parse(fs.readFileSync('public/routing.json', 'utf8'));
const tests = [
  { intent: 'english_review', expectProjects: ['learning-english'] },
  { intent: 'civil_service_error_analysis', expectProjects: ['civil-service-exam'] },
  { intent: 'study_planning', expectProjects: ['civil-service-exam', 'learning-english'] },
  { intent: 'list_projects', expectNoRecords: true },
  { intent: 'project_health', expectNoRecords: true },
];
let pass = 0, fail = 0;
for (const t of tests) {
  const intent = routing.intents[t.intent];
  if (!intent) { console.log('FAIL: ' + t.intent + ' — intent not found'); fail++; continue; }
  if (t.expectProjects) {
    const match = JSON.stringify(intent.candidate_projects) === JSON.stringify(t.expectProjects);
    console.log((match ? 'PASS' : 'FAIL') + ': ' + t.intent + ' — candidates: ' + JSON.stringify(intent.candidate_projects));
    match ? pass++ : fail++;
  }
  if (t.expectNoRecords) {
    const match = intent.record_data_required === false;
    console.log((match ? 'PASS' : 'FAIL') + ': ' + t.intent + ' — record_data_required: ' + intent.record_data_required);
    match ? pass++ : fail++;
  }
}
console.log('\\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail > 0 ? 1 : 0);
"
```
