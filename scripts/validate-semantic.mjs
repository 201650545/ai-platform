// scripts/validate-semantic.mjs — Validate semantic configs against schema and controlled vocabulary.
// Run after sync to ensure semantic.json files are correct and consistent.

import fs from "node:fs/promises";
import path from "node:path";

import { loadHubConfig, loadAllProjects } from "../lib/config.mjs";
import { loadSemanticConfig, validateSemanticConfig, SEMANTIC_TYPES, TABLE_ROLES, ENTITY_TYPES } from "../lib/semantic.mjs";

const ROOT = path.resolve(".");
const PUBLIC_DIR = path.join(ROOT, "public");

async function main() {
  const hubConfig = await loadHubConfig();
  const projects = await loadAllProjects();
  let totalErrors = 0;
  let totalWarnings = 0;

  console.log("=== 语义配置校验 ===\n");

  for (const { slug, config } of projects) {
    console.log(`[${slug}] 校验语义配置...`);
    const semanticConfig = await loadSemanticConfig(slug);

    if (!semanticConfig) {
      console.error(`  ✗ 缺少 config/semantics/${slug}.yaml`);
      totalErrors++;
      continue;
    }

    // Load schema.json from public output
    const schemaPath = path.join(PUBLIC_DIR, hubConfig.output.projects_dir, slug, "schema.json");
    let schema;
    try {
      const schemaText = await fs.readFile(schemaPath, "utf8");
      schema = JSON.parse(schemaText);
    } catch {
      console.error(`  ✗ 无法读取 ${schemaPath} — 请先运行同步`);
      totalErrors++;
      continue;
    }

    // Validate
    const { errors, warnings } = validateSemanticConfig(semanticConfig, schema, config);

    if (errors.length > 0) {
      for (const e of errors) console.error(`  ✗ ${e}`);
      totalErrors += errors.length;
    } else {
      console.log(`  ✓ 语义配置校验通过`);
    }

    for (const w of warnings) {
      console.log(`  ⚠ ${w}`);
      totalWarnings++;
    }

    // Check semantic.json exists in public output
    const semanticJsonPath = path.join(PUBLIC_DIR, hubConfig.output.projects_dir, slug, "semantic.json");
    try {
      await fs.access(semanticJsonPath);
      console.log(`  ✓ semantic.json 已生成`);
    } catch {
      console.error(`  ✗ semantic.json 不存在于公开输出`);
      totalErrors++;
    }

    // Validate agent-guide.md exists
    const agentGuidePath = path.join(PUBLIC_DIR, hubConfig.output.projects_dir, slug, "agent-guide.md");
    try {
      const content = await fs.readFile(agentGuidePath, "utf8");
      if (content.trim().length < 100) {
        console.error(`  ✗ agent-guide.md 内容过短（<100 字符）`);
        totalErrors++;
      } else {
        console.log(`  ✓ agent-guide.md 存在且内容充分`);
      }
    } catch {
      console.error(`  ✗ agent-guide.md 不存在于公开输出`);
      totalErrors++;
    }

    // Validate summary.md exists and is substantial
    const summaryPath = path.join(PUBLIC_DIR, hubConfig.output.projects_dir, slug, "summary.md");
    try {
      const content = await fs.readFile(summaryPath, "utf8");
      if (content.trim().length < 500) {
        console.error(`  ✗ summary.md 内容过短（<500 字符）`);
        totalErrors++;
      } else {
        console.log(`  ✓ summary.md 存在且内容充分`);
      }
    } catch {
      console.error(`  ✗ summary.md 不存在于公开输出`);
      totalErrors++;
    }

    console.log();
  }

  // Validate routing.json
  console.log("[全局] 校验 routing.json...");
  const routingPath = path.join(PUBLIC_DIR, "routing.json");
  try {
    const routingText = await fs.readFile(routingPath, "utf8");
    const routing = JSON.parse(routingText);

    // Check required intents exist
    const requiredIntents = ["list_projects", "project_health", "study_planning", "english_review", "civil_service_error_analysis", "teacher_cert_review"];
    for (const intent of requiredIntents) {
      if (!routing.intents?.[intent]) {
        console.error(`  ✗ routing.json 缺少 intent: ${intent}`);
        totalErrors++;
      }
    }

    // Validate routing logic
    const studyPlanning = routing.intents?.study_planning;
    if (studyPlanning) {
      const expected = ["civil-service-exam", "learning-english", "teacher-cert-exam"];
      const candidate = studyPlanning.candidate_projects;
      // Check that all three projects are included (order may vary)
      const hasAll = expected.every(s => candidate?.includes(s));
      if (!hasAll) {
        console.error(`  ✗ study_planning 候选项目不正确：${JSON.stringify(candidate)}（应包含 ${JSON.stringify(expected)}）`);
        totalErrors++;
      } else {
        console.log(`  ✓ study_planning 路由正确（${candidate.length} 个项目）`);
      }
    }

    const englishReview = routing.intents?.english_review;
    if (englishReview) {
      if (englishReview.candidate_projects.length !== 1 || englishReview.candidate_projects[0] !== "learning-english") {
        console.error(`  ✗ english_review 候选项目不正确：${JSON.stringify(englishReview.candidate_projects)}`);
        totalErrors++;
      } else {
        console.log(`  ✓ english_review 路由正确（仅英语项目）`);
      }
    }

    const civilServiceError = routing.intents?.civil_service_error_analysis;
    if (civilServiceError) {
      if (civilServiceError.candidate_projects.length !== 1 || civilServiceError.candidate_projects[0] !== "civil-service-exam") {
        console.error(`  ✗ civil_service_error_analysis 候选项目不正确：${JSON.stringify(civilServiceError.candidate_projects)}`);
        totalErrors++;
      } else {
        console.log(`  ✓ civil_service_error_analysis 路由正确（仅公考项目）`);
      }
    }

    // Check list_projects and project_health don't require records
    for (const intent of ["list_projects", "project_health"]) {
      const intentDef = routing.intents?.[intent];
      if (intentDef && intentDef.record_data_required !== false) {
        console.error(`  ✗ ${intent} 不应需要记录数据`);
        totalErrors++;
      } else if (intentDef) {
        console.log(`  ✓ ${intent} 不需要记录数据`);
      }
    }

    console.log(`  ✓ routing.json 校验通过`);
  } catch (err) {
    console.error(`  ✗ routing.json 校验失败：${err.message}`);
    totalErrors++;
  }

  // Validate catalog.json has new fields
  console.log("\n[全局] 校验 catalog.json 新增字段...");
  const catalogPath = path.join(PUBLIC_DIR, "catalog.json");
  try {
    const catalogText = await fs.readFile(catalogPath, "utf8");
    const catalog = JSON.parse(catalogText);

    // Check top-level indexes
    if (!catalog.capabilities) {
      console.error("  ✗ catalog.json 缺少顶层 capabilities 索引");
      totalErrors++;
    } else {
      console.log(`  ✓ 顶层 capabilities 索引存在（${Object.keys(catalog.capabilities).length} 个能力）`);
    }

    if (!catalog.domains) {
      console.error("  ✗ catalog.json 缺少顶层 domains 索引");
      totalErrors++;
    } else {
      console.log(`  ✓ 顶层 domains 索引存在（${Object.keys(catalog.domains).length} 个领域）`);
    }

    // Check each project has new fields
    for (const proj of catalog.projects) {
      const requiredNew = ["domains", "capabilities", "entity_types", "supported_queries", "semantic", "agent_guide", "freshness", "access_mode"];
      for (const field of requiredNew) {
        if (proj[field] === undefined) {
          console.error(`  ✗ ${proj.slug} 缺少新字段: ${field}`);
          totalErrors++;
        }
      }

      // Check old fields still exist
      const requiredOld = ["slug", "title", "description", "group", "tags", "status", "sync_status", "is_stale", "last_success_at", "manifest", "schema", "summary", "homepage", "table_count", "total_records"];
      for (const field of requiredOld) {
        if (proj[field] === undefined) {
          console.error(`  ✗ ${proj.slug} 缺少旧字段: ${field}`);
          totalErrors++;
        }
      }
    }

    // Check top-level indexes are consistent with project declarations
    for (const [cap, slugs] of Object.entries(catalog.capabilities || {})) {
      for (const slug of slugs) {
        const proj = catalog.projects.find(p => p.slug === slug);
        if (!proj || !proj.capabilities?.includes(cap)) {
          console.error(`  ✗ 顶层 capabilities.${cap} 包含 ${slug}，但项目未声明此能力`);
          totalErrors++;
        }
      }
    }

    for (const [dom, slugs] of Object.entries(catalog.domains || {})) {
      for (const slug of slugs) {
        const proj = catalog.projects.find(p => p.slug === slug);
        if (!proj || !proj.domains?.includes(dom)) {
          console.error(`  ✗ 顶层 domains.${dom} 包含 ${slug}，但项目未声明此领域`);
          totalErrors++;
        }
      }
    }

    console.log(`  ✓ catalog.json 新增字段校验通过`);
  } catch (err) {
    console.error(`  ✗ catalog.json 校验失败：${err.message}`);
    totalErrors++;
  }

  // Validate AI-README.md exists
  console.log("\n[全局] 校验 AI-README.md...");
  const aiReadmePath = path.join(PUBLIC_DIR, "AI-README.md");
  try {
    const content = await fs.readFile(aiReadmePath, "utf8");
    if (content.length < 500) {
      console.error("  ✗ AI-README.md 内容过短");
      totalErrors++;
    } else {
      console.log("  ✓ AI-README.md 存在且内容充分");
    }
  } catch {
    console.error("  ✗ AI-README.md 不存在");
    totalErrors++;
  }

  // Summary
  console.log(`\n=== 校验结果 ===`);
  console.log(`错误：${totalErrors}`);
  console.log(`警告：${totalWarnings}`);

  if (totalErrors > 0) {
    console.error("\n❌ 语义配置校验未通过");
    process.exit(1);
  } else {
    console.log("\n✅ 语义配置校验全部通过");
  }
}

main().catch(err => {
  console.error(`校验失败：${err.message}`);
  process.exit(1);
});
