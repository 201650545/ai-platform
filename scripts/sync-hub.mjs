// scripts/sync-hub.mjs — Data Hub orchestrator.
// Discovers all projects, syncs each with fault isolation, builds catalog and homepage.
// Normal failures (timeout, API error) affect only the failing project.
// Security failures stop the entire deployment.

import fs from "node:fs/promises";
import path from "node:path";
import { execSync } from "node:child_process";

import { loadHubConfig, loadCredentialProfiles, loadAllProjects, loadProjectConfig } from "../lib/config.mjs";
import { assertNoSecrets } from "../lib/security.mjs";
import { writeJson, generateBuildId, buildHubHomepage } from "../lib/output.mjs";
import { syncProject } from "./sync-project.mjs";
import { hydrateExistingProject } from "./hydrate-existing-project.mjs";

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

    projectEntries.push({
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
      total_records: manifest?.tables?.reduce((sum, t) => sum + t.record_count, 0) || 0
    });
  }

  // Sort by slug for stable output
  projectEntries.sort((a, b) => a.slug.localeCompare(b.slug));

  return {
    catalog_version: 1,
    build_id: buildId,
    generated_at: new Date().toISOString(),
    hub: {
      title: hubConfig.hub.title,
      description: hubConfig.hub.description
    },
    projects: projectEntries
  };
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
