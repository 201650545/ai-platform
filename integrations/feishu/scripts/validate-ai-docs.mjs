// scripts/validate-ai-docs.mjs — Validate AI documentation files exist, are non-empty, and pass security scan.
// Checks summary.md, agent-guide.md, semantic.json, routing.json, AI-README.md for all projects.

import fs from "node:fs/promises";
import path from "node:path";

import { loadHubConfig, loadAllProjects } from "../lib/config.mjs";
import { assertNoSecrets, scanContent } from "../lib/security.mjs";

const ROOT = path.resolve(".");
const PUBLIC_DIR = path.join(ROOT, "public");

async function main() {
  const hubConfig = await loadHubConfig();
  const projects = await loadAllProjects();
  let errors = 0;
  let warnings = 0;

  console.log("=== AI 文档校验 ===\n");

  for (const { slug } of projects) {
    console.log(`[${slug}] 校验 AI 文档...`);
    const projectDir = path.join(PUBLIC_DIR, hubConfig.output.projects_dir, slug);

    // Required AI docs per project
    const requiredFiles = [
      { name: "summary.md", minSize: 500, description: "项目说明" },
      { name: "agent-guide.md", minSize: 200, description: "AI 使用规则" },
      { name: "semantic.json", minSize: 50, description: "语义映射" },
      { name: "schema.json", minSize: 50, description: "数据结构" },
      { name: "manifest.json", minSize: 50, description: "数据清单" },
      { name: "status.json", minSize: 20, description: "同步状态" },
    ];

    for (const { name, minSize, description } of requiredFiles) {
      const filePath = path.join(projectDir, name);
      try {
        const content = await fs.readFile(filePath, "utf8");

        // Check size
        if (content.trim().length < minSize) {
          console.error(`  ✗ ${name} 内容过短（<${minSize} 字符）— ${description}`);
          errors++;
          continue;
        }

        // Security scan
        const scanResult = scanContent(content, { strict: false, context: `${slug}/${name}` });
        if (!scanResult.passed) {
          console.error(`  ✗ ${name} 安全扫描发现问题：${scanResult.issues.join("; ")}`);
          errors++;
          continue;
        }

        console.log(`  ✓ ${name} (${content.length} 字符)`);
      } catch {
        console.error(`  ✗ ${name} 不存在 — ${description}`);
        errors++;
      }
    }

    // Validate summary.md has required sections
    const summaryPath = path.join(projectDir, "summary.md");
    try {
      const summary = await fs.readFile(summaryPath, "utf8");
      const requiredSections = [
        "项目用途", "核心目标", "主要数据表", "表之间的关系",
        "常见分析问题", "推荐读取顺序", "数据更新时间与时效性",
        "数据公开范围", "已知限制", "不应做出的推断"
      ];
      for (const section of requiredSections) {
        if (!summary.includes(section)) {
          console.error(`  ✗ summary.md 缺少章节：${section}`);
          errors++;
        }
      }
      console.log(`  ✓ summary.md 章节完整`);
    } catch {
      // Already caught above
    }

    // Validate agent-guide.md has required sections
    const guidePath = path.join(projectDir, "agent-guide.md");
    try {
      const guide = await fs.readFile(guidePath, "utf8");
      const requiredSections = [
        "适用任务", "不适用任务", "分析优先级", "读取顺序",
        "计划制定规则", "错误分析规则", "时间范围处理",
        "数据不足时的处理", "禁止推断", "输出要求"
      ];
      for (const section of requiredSections) {
        if (!guide.includes(section)) {
          console.error(`  ✗ agent-guide.md 缺少章节：${section}`);
          errors++;
        }
      }
      console.log(`  ✓ agent-guide.md 章节完整`);
    } catch {
      // Already caught above
    }

    console.log();
  }

  // Validate hub-level AI docs
  console.log("[全局] 校验 Hub 级 AI 文档...");

  const hubFiles = [
    { name: "AI-README.md", minSize: 500, description: "AI 入口指南" },
    { name: "catalog.json", minSize: 100, description: "全局目录" },
    { name: "routing.json", minSize: 100, description: "路由规则" },
  ];

  for (const { name, minSize, description } of hubFiles) {
    const filePath = path.join(PUBLIC_DIR, name);
    try {
      const content = await fs.readFile(filePath, "utf8");

      if (content.trim().length < minSize) {
        console.error(`  ✗ ${name} 内容过短（<${minSize} 字符）— ${description}`);
        errors++;
        continue;
      }

      // Security scan
      const scanResult = scanContent(content, { strict: false, context: name });
      if (!scanResult.passed) {
        console.error(`  ✗ ${name} 安全扫描发现问题：${scanResult.issues.join("; ")}`);
        errors++;
        continue;
      }

      console.log(`  ✓ ${name} (${content.length} 字符)`);
    } catch {
      console.error(`  ✗ ${name} 不存在 — ${description}`);
      errors++;
    }
  }

  // Validate AI-README.md has required content
  const aiReadmePath = path.join(PUBLIC_DIR, "AI-README.md");
  try {
    const readme = await fs.readFile(aiReadmePath, "utf8");
    const requiredContent = [
      "推荐读取流程",
      "catalog.json",
      "routing.json",
      "summary.md",
      "agent-guide.md",
      "semantic.json",
      "schema.json",
      "manifest.json",
      "禁止扫描全部数据",
      "数据不足",
      "只读",
      "安全边界"
    ];
    for (const content of requiredContent) {
      if (!readme.includes(content)) {
        console.error(`  ✗ AI-README.md 缺少内容：${content}`);
        errors++;
      }
    }
    console.log(`  ✓ AI-README.md 内容完整`);
  } catch {
    // Already caught above
  }

  // Validate routing.json has required intents
  const routingPath = path.join(PUBLIC_DIR, "routing.json");
  try {
    const routing = JSON.parse(await fs.readFile(routingPath, "utf8"));
    const requiredIntents = [
      "list_projects", "project_health", "study_planning",
      "english_review", "civil_service_error_analysis"
    ];
    for (const intent of requiredIntents) {
      if (!routing.intents?.[intent]) {
        console.error(`  ✗ routing.json 缺少 intent：${intent}`);
        errors++;
      }
    }
    console.log(`  ✓ routing.json intents 完整`);
  } catch {
    // Already caught above
  }

  // Summary
  console.log(`\n=== 校验结果 ===`);
  console.log(`错误：${errors}`);
  console.log(`警告：${warnings}`);

  if (errors > 0) {
    console.error("\n❌ AI 文档校验未通过");
    process.exit(1);
  } else {
    console.log("\n✅ AI 文档校验全部通过");
  }
}

main().catch(err => {
  console.error(`校验失败：${err.message}`);
  process.exit(1);
});
