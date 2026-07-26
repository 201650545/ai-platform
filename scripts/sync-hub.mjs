// scripts/sync-hub.mjs — Data Hub orchestrator.
// Discovers all projects, syncs each with fault isolation, builds catalog and homepage.
// Normal failures (timeout, API error) affect only the failing project.
// Security failures stop the entire deployment.

import fs from "node:fs/promises";
import path from "node:path";
import { execSync } from "node:child_process";

import { loadHubConfig, loadCredentialProfiles, loadAllProjects, loadProjectConfig } from "../lib/config.mjs";
import { assertNoSecrets } from "../lib/security.mjs";
import { writeJson, writeText, generateBuildId, buildHubHomepage } from "../lib/output.mjs";
import { syncProject } from "./sync-project.mjs";
import { hydrateExistingProject } from "./hydrate-existing-project.mjs";
import { loadSemanticConfig, loadRoutingConfig, buildRoutingJson } from "../lib/semantic.mjs";

/**
 * Main orchestrator — syncs all projects and builds the hub output.
 * @param {object} options - { projectSlug, syncAll, force, dryRun, tier }
 */
async function syncHub(options = {}) {
  const env = process.env;
  const hubConfig = await loadHubConfig();
  const credentialProfiles = await loadCredentialProfiles();
  const outputDir = path.resolve(".", hubConfig.output.root_dir);

  // Get git SHA for build_id
  let gitSha = "local";
  try {
    gitSha = execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  } catch { /* local run */ }

  const buildId = generateBuildId(gitSha);
  console.log(`Data Hub sync starting — build_id: ${buildId}`);

  // Discover projects
  let projects;
  if (options.projectSlug) {
    // Single-project mode
    const config = await loadProjectConfig(options.projectSlug);
    projects = [{ slug: options.projectSlug, config }];
  } else {
    projects = await loadAllProjects();
  }

  // Filter by schedule tier if specified
  if (options.tier) {
    projects = projects.filter(p => (p.config.schedule?.tier || "hourly") === options.tier);
  }

  console.log(`发现 ${projects.length} 个项目待同步`);

  // Prepare output directory.
  // DON'T wipe the entire output — we need to preserve old project outputs
  // for fault recovery (hydrate-existing-project.mjs). Each project's sync
  // uses atomic directory replacement, so old outputs survive sync failures.
  // We only clean up project directories that no longer exist in config after sync.
  await fs.mkdir(outputDir, { recursive: true });

  // Sync each project with fault isolation
  const results = [];
  const securityErrors = [];

  for (const { slug, config } of projects) {
    try {
      const result = await syncProject(slug, hubConfig, credentialProfiles, env, buildId, {
        outputDir,
        force: options.force,
        dryRun: options.dryRun
      });
      results.push(result);
      console.log(`[${slug}] ✓ 同步成功`);
    } catch (error) {
      // Distinguish security errors from normal errors
      const isSecurityError = isSecurityFailure(error);
      if (isSecurityError) {
        console.error(`[${slug}] ✗ 安全故障：${error.message}`);
        securityErrors.push({ slug, error: error.message });
      } else {
        console.error(`[${slug}] ✗ 普通故障：${error.message}`);
        results.push({ slug, status: "failed", error: error.message, manifest: null, schema: null, warnings: [] });

        // Attempt to hydrate from last successful build
        try {
          console.log(`[${slug}] 尝试恢复上一次成功发布版本……`);
          const hydrated = await hydrateExistingProject(slug, hubConfig, outputDir, buildId);
          if (hydrated) {
            console.log(`[${slug}] ✓ 已恢复上一版本`);
            results.push({ slug, status: "stale", ...hydrated });
          } else {
            console.log(`[${slug}] 无可恢复的历史版本`);
          }
        } catch (hydrateError) {
          console.error(`[${slug}] 恢复失败：${hydrateError.message}`);
        }
      }
    }
  }

  // Security failures stop the entire deployment
  if (securityErrors.length > 0) {
    console.error(`\n安全故障 ${securityErrors.length} 个，中止整个部署：`);
    for (const e of securityErrors) {
      console.error(`  [${e.slug}] ${e.error}`);
    }
    process.exit(1);
  }

  // Clean up project directories that no longer exist in config (full sync only)
  if (!options.projectSlug) {
    const currentSlugs = new Set(projects.map(p => p.slug));
    const projectsOutputDir = path.join(outputDir, hubConfig.output.projects_dir);
    try {
      const entries = await fs.readdir(projectsOutputDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory() && !currentSlugs.has(entry.name)) {
          console.log(`清理已移除的项目目录：${entry.name}`);
          await fs.rm(path.join(projectsOutputDir, entry.name), { recursive: true, force: true });
        }
      }
    } catch { /* projects dir may not exist yet */ }
  }

  // Build global catalog
  console.log("\n构建全局 catalog.json……");
  const catalog = await buildCatalog(hubConfig, results, buildId, outputDir);
  await writeJson(outputDir, hubConfig.output.catalog_file, catalog, []);
  console.log("catalog.json written");

  // Write versioned catalog for cache busting
  const versionedDir = path.join(outputDir, hubConfig.output.catalog_versioned_dir);
  await fs.mkdir(versionedDir, { recursive: true });
  await writeJson(outputDir, `${hubConfig.output.catalog_versioned_dir}/${buildId}.json`, catalog, []);
  console.log(`Versioned catalog: ${hubConfig.output.catalog_versioned_dir}/${buildId}.json`);

  // Build routing.json
  console.log("\n构建 routing.json……");
  const routingConfig = await loadRoutingConfig();
  if (routingConfig) {
    const routingJson = buildRoutingJson(routingConfig, catalog);
    await writeJson(outputDir, "routing.json", routingJson, []);
    console.log("routing.json written");
  } else {
    console.warn("⚠ config/query-routing.yaml 不存在 — routing.json 未生成");
  }

  // Build AI-README.md
  console.log("\n构建 AI-README.md……");
  const aiReadme = buildAiReadme(catalog);
  assertNoSecrets(aiReadme, [], "AI-README.md");
  await fs.writeFile(path.join(outputDir, "AI-README.md"), aiReadme, "utf8");
  console.log("AI-README.md written");

  // Build hub homepage
  const homepage = buildHubHomepage(catalog, buildId);
  assertNoSecrets(homepage, [], "hub homepage");
  await fs.writeFile(path.join(outputDir, hubConfig.output.homepage_file), homepage, "utf8");
  console.log("Hub homepage written");

  // Summary
  const ok = results.filter(r => r.status === "ok").length;
  const stale = results.filter(r => r.status === "stale").length;
  const failed = results.filter(r => r.status === "failed").length;
  console.log(`\n=== Data Hub 同步完成 ===`);
  console.log(`Build ID: ${buildId}`);
  console.log(`项目总数: ${results.length}`);
  console.log(`成功: ${ok} | 恢复旧版: ${stale} | 失败: ${failed}`);
  console.log(`输出目录: ${outputDir}`);

  if (failed > 0 && ok === 0) {
    console.error("所有项目均失败，退出码 1");
    process.exit(1);
  }
}

/**
 * Determine if an error is a security failure (should stop everything)
 * vs a normal failure (should only affect this project).
 */
function isSecurityFailure(error) {
  const msg = error.message || "";
  const securityKeywords = [
    "凭证值", "敏感信息", "secret", "token", "authorization",
    "private key", "cookie", "app_secret", "bearer"
  ];
  return securityKeywords.some(kw => msg.toLowerCase().includes(kw.toLowerCase()));
}

/**
 * Build the global catalog.json from all project results.
 * Extends with semantic metadata: domains, capabilities, entity_types,
 * supported_queries, semantic/agent_guide paths, freshness.
 */
async function buildCatalog(hubConfig, results, buildId, outputDir) {
  const projectsDir = hubConfig.output.projects_dir;

  const projectEntries = [];
  for (const result of results) {
    const slug = result.slug;
    const projectDir = path.join(outputDir, projectsDir, slug);
    const projectConfig = await loadProjectConfig(slug).catch(() => null);

    let manifest = result.manifest;
    let status = { sync_status: result.status, is_stale: result.status === "stale" };

    // If project was synced OK, read the manifest from disk
    if (result.status === "ok" && manifest) {
      // Use the in-memory manifest
    } else if (result.status === "stale") {
      // Read from hydrated output
      try {
        const manifestText = await fs.readFile(path.join(projectDir, "manifest.json"), "utf8");
        manifest = JSON.parse(manifestText);
      } catch { /* leave null */ }
    }

    // Read status.json if available
    try {
      const statusText = await fs.readFile(path.join(projectDir, "status.json"), "utf8");
      status = JSON.parse(statusText);
    } catch { /* use default */ }

    // Load semantic config for extended fields
    const semanticConfig = await loadSemanticConfig(slug);

    // Build freshness info from status
    const freshness = {
      expected_update: status.expected_update_interval || projectConfig?.schedule?.tier || "hourly",
      last_success_at: status.last_success_at || null,
      is_stale: status.is_stale ?? (result.status === "stale"),
    };

    projectEntries.push({
      // Original fields (preserved for backward compatibility)
      slug,
      title: projectConfig?.project?.title || slug,
      description: projectConfig?.project?.description || "",
      group: projectConfig?.project?.group || "",
      tags: projectConfig?.project?.tags || [],
      status: projectConfig?.project?.status || "active",
      sync_status: status.sync_status || result.status,
      is_stale: status.is_stale ?? (result.status === "stale"),
      last_success_at: status.last_success_at || null,
      manifest: `${projectsDir}/${slug}/manifest.json`,
      schema: `${projectsDir}/${slug}/schema.json`,
      summary: `${projectsDir}/${slug}/summary.md`,
      homepage: `${projectsDir}/${slug}/index.html`,
      table_count: manifest?.tables?.length || 0,
      total_records: manifest?.tables?.reduce((sum, t) => sum + t.record_count, 0) || 0,
      // New semantic fields
      domains: semanticConfig?.project?.domains || [],
      capabilities: semanticConfig?.project?.capabilities || [],
      entity_types: semanticConfig?.project?.entity_types || [],
      supported_queries: semanticConfig?.project?.supported_queries || [],
      semantic: `${projectsDir}/${slug}/semantic.json`,
      agent_guide: `${projectsDir}/${slug}/agent-guide.md`,
      freshness,
      access_mode: "public-readonly",
    });
  }

  // Sort by slug for stable output
  projectEntries.sort((a, b) => a.slug.localeCompare(b.slug));

  // Build top-level capability and domain indexes
  const capabilities = {};
  const domains = {};
  for (const proj of projectEntries) {
    for (const cap of proj.capabilities) {
      if (!capabilities[cap]) capabilities[cap] = [];
      capabilities[cap].push(proj.slug);
    }
    for (const dom of proj.domains) {
      if (!domains[dom]) domains[dom] = [];
      domains[dom].push(proj.slug);
    }
  }
  // Sort for stable output
  for (const k of Object.keys(capabilities)) capabilities[k].sort();
  for (const k of Object.keys(domains)) domains[k].sort();

  return {
    catalog_version: 1,
    build_id: buildId,
    generated_at: new Date().toISOString(),
    hub: {
      title: hubConfig.hub.title,
      description: hubConfig.hub.description
    },
    projects: projectEntries,
    // Top-level indexes for AI routing
    capabilities,
    domains,
  };
}

/**
 * Build the AI-README.md — the entry point for AI agents.
 */
function buildAiReadme(catalog) {
  const projectList = catalog.projects.map(p =>
    `- **${p.title}** (\`${p.slug}\`): ${p.description} — domains: ${p.domains.join(", ")} | capabilities: ${p.capabilities.join(", ")} | tables: ${p.table_count} | records: ${p.total_records} | status: ${p.sync_status}`
  ).join("\n");

  return `# AI Data Hub 入口指南

> 本文件面向 AI 代理和其他自动化消费者，说明如何使用本 Data Hub。

## 本 Hub 是什么

Feishu Data Hub 是一个**只读的公开数据层**，从飞书多维表格导出个人学习数据，以静态 JSON 部署在 GitHub Pages 上。AI 代理可以通过这些数据理解用户的学习状态、制定计划和进行分析。

**安全边界：** 本 Hub 是纯只读的。不存在写入接口，不暴露飞书凭据，不提供修改能力。

## Catalog 地址

- **全局目录：** \`catalog.json\`
- **路由规则：** \`routing.json\`
- **版本化目录：** \`catalog-versioned/<build_id>.json\`

## 推荐读取流程

1. 读取 \`catalog.json\` — 发现所有可用项目
2. 根据 \`domains\` / \`capabilities\` 选择相关项目
3. 读取项目 \`summary.md\` — 理解项目用途和数据表
4. 读取项目 \`agent-guide.md\` — 了解分析规则和禁止事项
5. 读取 \`semantic.json\` — 理解表和字段的业务含义
6. 必要时读取 \`schema.json\` 和 \`manifest.json\` — 了解数据结构
7. **只读取回答问题所需的记录分片** — 不要扫描全部记录

## 如何选择项目

查看 \`catalog.json\` 中每个项目的 \`domains\` 和 \`capabilities\` 字段：
- \`domains\` 表示项目所属领域（如 learning, language, exam）
- \`capabilities\` 表示项目支持的分析能力（如 study_planning, error_analysis）

也可以查看 \`routing.json\` 中的 \`intents\`，找到匹配的意图和候选项目。

## 如何判断项目 stale

检查项目的 \`freshness.is_stale\` 或 \`sync_status\`：
- \`is_stale: false\` + \`sync_status: "ok"\` = 数据正常
- \`is_stale: true\` = 展示的是上一次成功同步的数据
- \`sync_status: "failed"\` = 同步失败，数据可能过期

始终在输出中告知用户数据的同步时间（\`last_success_at\`）和是否 stale。

## 文件职责

| 文件 | 职责 |
|---|---|
| \`catalog.json\` | 全局项目目录，包含所有项目的元数据和索引 |
| \`routing.json\` | 查询路由规则，将意图映射到候选项目 |
| \`AI-README.md\` | 本文件，AI 入口指南 |
| \`projects/<slug>/summary.md\` | 项目说明：用途、表、关系、限制 |
| \`projects/<slug>/agent-guide.md\` | AI 使用规则：适用任务、分析优先级、禁止推断 |
| \`projects/<slug>/semantic.json\` | 语义映射：表角色、字段含义、受控词表 |
| \`projects/<slug>/schema.json\` | 数据结构：字段类型、选项、关联 |
| \`projects/<slug>/manifest.json\` | 数据清单：表列表、记录数、校验和 |
| \`projects/<slug>/status.json\` | 同步状态：新鲜度、记录数、警告 |

## 禁止扫描全部数据的情况

以下情况**不应**读取业务记录：
- "列出所有项目" — 只读 \`catalog.json\`
- "哪个项目数据过期了" — 只读 \`catalog.json\` 和 \`status.json\`
- "项目有多少张表" — 只读 \`manifest.json\`

只有在回答具体业务问题（如"哪些词需要复习"）时才读取记录分片。

## 数据不足如何说明

当数据不足以做出可靠判断时：
1. 明确说明"当前数据不足，无法做出可靠判断"
2. 说明缺少哪些数据（如"刷题记录仅 3 条，无法进行趋势分析"）
3. 不根据少量样本推断总体趋势
4. 不编造数据或假设未记录的学习活动

## 只读安全边界

- 本 Hub **只有读权限**，不存在任何写入接口
- 飞书凭据**不会**出现在公开数据中
- GitHub Token **不会**暴露给浏览器端
- 不要尝试通过任何方式修改飞书数据
- 不要在输出中包含任何从数据中读到的敏感个人信息

## 当前项目列表

${projectList}

## Build ID

当前构建：\`${catalog.build_id}\`
生成时间：${catalog.generated_at}
`;
}

// CLI entry point
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/sync-hub.mjs")) {
  // Parse CLI args
  const args = process.argv.slice(2);
  const options = {};

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--project" || args[i] === "--project-slug") {
      options.projectSlug = args[++i];
    } else if (args[i] === "--sync-all") {
      options.syncAll = true;
    } else if (args[i] === "--force") {
      options.force = true;
    } else if (args[i] === "--dry-run") {
      options.dryRun = true;
    } else if (args[i] === "--tier") {
      options.tier = args[++i];
    }
  }

  syncHub(options).catch(e => {
    console.error(`Data Hub 同步失败：${e.message}`);
    process.exitCode = 1;
  });
}

export { syncHub };
