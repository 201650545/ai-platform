#!/usr/bin/env node
/**
 * 生成每日复习计划（打通复习调度闭环）
 *
 * 逻辑：从 vocabulary 表「下次复习」字段筛出到期词（due <= 今天），
 * 输出单词清单 + 可直接执行的 lark-cli 写入命令，写回飞书 daily-plan 表。
 * 复习结果写回 learning-log 后，由 FSRS 更新「下次复习」，进入 hourly/daily 同步闭环。
 *
 * 用法：
 *   node scripts/generate_daily_review.mjs                # 默认今天
 *   node scripts/generate_daily_review.mjs --date 2026-08-11
 *
 * 数据源：GitHub Pages 导出（只读，无需本地飞书凭据）
 * 写入：输出 lark-cli 命令，由 lark-cli（已配置 qclaw 凭据）执行
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const DAILY_PLAN_TABLE_ID = "tblAgZiB1GtJzd9R"; // 每日计划
const BASE_TOKEN = "K15hbHNwtaY3BWs1STLcG092n4g"; // learning-english base

// ---- 参数解析 ----
const args = process.argv.slice(2);
// 默认用机器本地时区计算"今天"（与飞书数据的自然日对齐）
const now = new Date();
let dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--date") dateStr = args[++i];
}

// ---- 1. 读取 vocabulary 导出（本地优先，缺省走 GitHub Pages）----
function readLocalRecords(dir) {
  if (!existsSync(dir)) return null;
  const files = readdirSync(dir, { recursive: true }).filter((f) => f.endsWith(".json"));
  const recs = [];
  for (const f of files) {
    const data = JSON.parse(readFileSync(resolve(dir, f), "utf-8"));
    recs.push(...(data.records ?? []));
  }
  return recs.length ? recs : null;
}

async function loadVocabulary() {
  const local = readLocalRecords(resolve("data/projects/learning-english/tables/vocabulary"))
    ?? readLocalRecords(resolve("site/data/projects/learning-english/tables/vocabulary"));
  if (local) return local;

  const base = "https://201650545.github.io/feishu-data-hub/projects/learning-english/";
  const manifest = await (await fetch(base + "manifest.json")).json();
  const vocab = manifest.tables.find((t) => t.slug === "vocabulary");
  const recs = [];
  for (const rf of vocab.record_files) {
    const data = await (await fetch(base + rf.path)).json();
    recs.push(...(data.records ?? []));
  }
  return recs;
}

// ---- 2. 筛选到期词 ----
const dueDate = Date.parse(dateStr + "T23:59:59+08:00");
const recs = await loadVocabulary();
const dueWords = recs
  .map((r) => r.fields)
  .filter((f) => {
    const v = f["下次复习"];
    if (v == null) return false;
    const ts = typeof v === "number" ? v : Date.parse(v);
    return Number.isFinite(ts) && ts <= dueDate;
  })
  .sort((a, b) => (a["下次复习"] ?? 0) - (b["下次复习"] ?? 0));

console.log(`[generate-daily-review] 日期=${dateStr} 到期词=${dueWords.length}`);
if (!dueWords.length) {
  console.log("今日无到期词，无需生成计划。");
  process.exit(0);
}

// ---- 3. 输出单词清单 ----
const wordList = dueWords.map((f) => f["单词"]).filter(Boolean);
console.log(`单词数=${wordList.length}`);
console.log(`单词列表: ${wordList.join(",")}`);

// ---- 4. 输出 lark-cli 写入命令 ----
const row = JSON.stringify([
  dateStr + " 08:00:00",
  String(wordList.length),
  wordList.join(","),
  "未开始",
  "0",
  null,
  "复习",
]);
const cmd = [
  `lark-cli base +record-batch-create --base-token "${BASE_TOKEN}" --table-id "${DAILY_PLAN_TABLE_ID}" --as user`,
  `  --json '{"fields":["日期","复习词数","单词列表","完成状态","新词数","正确率","计划类型"],"rows":[${row}]}'`,
].join(" \\\n  ");
console.log("\n=== 写入飞书（复制以下命令执行）===");
console.log(cmd);
console.log("\n注意：写前建议先用 --dry-run 预览。");
