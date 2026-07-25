// scripts/hydrate-existing-project.mjs — Fault recovery for failed projects.
// When a project fails to sync normally, this script restores the last successful
// output and marks it as stale. The old output survives because sync-project.mjs
// uses atomic directory replacement (sync to temp, rename on success).

import fs from "node:fs/promises";
import path from "node:path";

import { writeJson } from "../lib/output.mjs";

/**
 * Restore a project's previous successful output after a sync failure.
 * The previous output is still on disk because sync-project.mjs uses atomic swap.
 * This function only updates status.json to mark the project as stale.
 *
 * @param {string} slug - Project slug.
 * @param {object} hubConfig - Hub configuration.
 * @param {string} outputDir - Root output directory.
 * @param {string} buildId - Current build_id (for status tracking).
 * @returns {object|null} - { slug, manifest, status } or null if no previous output.
 */
export async function hydrateExistingProject(slug, hubConfig, outputDir, buildId) {
  const projectsDir = hubConfig.output.projects_dir;
  const projectDir = path.join(outputDir, projectsDir, slug);
  const manifestPath = path.join(projectDir, "manifest.json");
  const statusPath = path.join(projectDir, "status.json");

  // Check if previous output exists
  try {
    await fs.access(manifestPath);
  } catch {
    return null; // No previous output to restore
  }

  // Read the existing manifest
  const manifestText = await fs.readFile(manifestPath, "utf8");
  const manifest = JSON.parse(manifestText);

  // Read the existing status (to preserve last_success_at)
  let previousStatus = {};
  try {
    const statusText = await fs.readFile(statusPath, "utf8");
    previousStatus = JSON.parse(statusText);
  } catch { /* no previous status */ }

  // Update status to mark as stale
  const now = new Date().toISOString();
  const newStatus = {
    project_slug: slug,
    build_id: buildId,
    sync_status: "failed",
    is_stale: true,
    last_attempt_at: now,
    last_success_at: previousStatus.last_success_at || previousStatus.last_attempt_at || manifest.generated_at || null,
    source_record_count: manifest.tables?.reduce((sum, t) => sum + t.record_count, 0) || 0,
    published_record_count: manifest.tables?.reduce((sum, t) => sum + t.record_count, 0) || 0,
    warnings: [`项目同步失败，已恢复上次成功版本 (stale since ${now})`]
  };

  // Write updated status.json
  await writeJson(projectDir, "status.json", newStatus, []);
  console.log(`[${slug}] status.json updated to stale`);

  // Read the existing schema for the return value
  let schema = null;
  try {
    const schemaText = await fs.readFile(path.join(projectDir, "schema.json"), "utf8");
    schema = JSON.parse(schemaText);
  } catch { /* schema may not exist */ }

  return {
    slug,
    manifest,
    schema,
    status: newStatus,
    warnings: newStatus.warnings
  };
}

// CLI entry point
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/hydrate-existing-project.mjs")) {
  const slug = process.argv[2];
  if (!slug) {
    console.error("用法: node scripts/hydrate-existing-project.mjs <project-slug>");
    process.exit(1);
  }

  const { loadHubConfig } = await import("../lib/config.mjs");
  const hubConfig = await loadHubConfig();
  const outputDir = path.resolve(".", hubConfig.output.root_dir);
  const buildId = "hydrate-local";

  hydrateExistingProject(slug, hubConfig, outputDir, buildId)
    .then(result => {
      if (result) {
        console.log(`项目 ${slug} 已恢复上次成功版本`);
      } else {
        console.log(`项目 ${slug} 无可恢复的历史版本`);
        process.exitCode = 1;
      }
    })
    .catch(e => {
      console.error(`恢复失败：${e.message}`);
      process.exitCode = 1;
    });
}
