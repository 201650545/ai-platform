// scripts/validate-config.mjs — Validates all configuration files.
// Checks hub.yaml, credential-profiles.yaml, and all project YAMLs
// for structural integrity, slug uniqueness, and forbidden field names.

import path from "node:path";

import {
  loadHubConfig,
  loadCredentialProfiles,
  discoverProjects,
  loadProjectConfig,
  FORBIDDEN_FIELD_NAMES,
} from "../lib/config.mjs";

/**
 * Validate all configuration files in the config/ directory.
 * Collects all errors rather than stopping at the first failure.
 * @returns {Promise<object>} - { hub, profiles, projects, errors }
 */
export async function validateConfig() {
  const errors = [];
  let hub = null;
  let profiles = null;
  const projects = [];

  // 1. Validate hub.yaml (loadHubConfig checks hub_version, hub.title, output.root_dir)
  try {
    hub = await loadHubConfig();
    console.log(`[通过] hub.yaml 验证通过（hub_version=${hub.hub_version}, title="${hub.hub.title}"）`);
  } catch (error) {
    errors.push(`hub.yaml: ${error.message}`);
    console.error(`[失败] hub.yaml 验证失败：${error.message}`);
  }

  // 2. Validate credential-profiles.yaml (loadCredentialProfiles checks profiles object)
  try {
    profiles = await loadCredentialProfiles();
    const profileNames = Object.keys(profiles.profiles || {});
    console.log(`[通过] credential-profiles.yaml 验证通过（${profileNames.length} 个凭据配置：${profileNames.join(", ")}）`);
  } catch (error) {
    errors.push(`credential-profiles.yaml: ${error.message}`);
    console.error(`[失败] credential-profiles.yaml 验证失败：${error.message}`);
  }

  // 3. Discover all project YAMLs in config/projects/
  let slugs = [];
  try {
    slugs = await discoverProjects();
  } catch (error) {
    errors.push(`发现项目失败：${error.message}`);
    console.error(`[失败] 发现项目失败：${error.message}`);
  }

  // 4. Check slug uniqueness across projects and validate each project config
  const seenProjectSlugs = new Set();

  for (const slug of slugs) {
    try {
      const config = await loadProjectConfig(slug);

      // Check project.slug uniqueness across all projects
      const projectSlug = config.project.slug;
      if (seenProjectSlugs.has(projectSlug)) {
        errors.push(`项目 slug 重复：${projectSlug}（出现在多个项目配置中）`);
        console.error(`[失败] 项目 slug 重复：${projectSlug}`);
      } else {
        seenProjectSlugs.add(projectSlug);
      }

      // 5. Explicitly check forbidden field names using FORBIDDEN_FIELD_NAMES
      //    (loadProjectConfig also checks, but we double-check here for completeness)
      if (Array.isArray(config.tables)) {
        for (const tc of config.tables) {
          if (Array.isArray(tc.fields)) {
            for (const fn of tc.fields) {
              const normalized = String(fn).trim().toLowerCase();
              if (FORBIDDEN_FIELD_NAMES.has(normalized)) {
                errors.push(`${slug}/${tc.table_name}: 禁止公开敏感字段名：${fn}`);
                console.error(`[失败] ${slug}/${tc.table_name}: 禁止公开敏感字段名：${fn}`);
              }
            }
          }
        }
      }

      // Cross-check: credential_profile referenced by project exists in profiles
      if (profiles && config.source?.credential_profile) {
        if (!profiles.profiles?.[config.source.credential_profile]) {
          errors.push(`${slug}: 凭据配置 "${config.source.credential_profile}" 不存在于 credential-profiles.yaml`);
          console.error(`[失败] ${slug}: 凭据配置 "${config.source.credential_profile}" 不存在`);
        }
      }

      projects.push({ slug, config });
      const tableCount = Array.isArray(config.tables) ? config.tables.length : 0;
      console.log(`[通过] 项目 ${slug} 验证通过（${tableCount} 张表）`);
    } catch (error) {
      errors.push(`${slug}: ${error.message}`);
      console.error(`[失败] 项目 ${slug} 验证失败：${error.message}`);
    }
  }

  if (slugs.length === 0 && errors.length === 0) {
    errors.push("config/projects/ 目录下没有发现任何项目配置文件");
    console.error("[失败] 没有发现任何项目配置文件");
  }

  return { hub, profiles, projects, errors };
}

/**
 * Main entry point for CLI execution.
 */
async function main() {
  try {
    console.log("=== 配置文件验证 ===\n");

    const result = await validateConfig();

    console.log("\n=== 验证摘要 ===");
    console.log(`项目数：${result.projects.length}`);
    console.log(`错误数：${result.errors.length}`);

    if (result.errors.length > 0) {
      console.error("\n配置验证失败，错误列表：");
      for (const err of result.errors) {
        console.error(`  - ${err}`);
      }
      process.exitCode = 1;
    } else {
      console.log("\n所有配置文件验证通过。");
    }
  } catch (error) {
    console.error(`配置验证异常：${error.message}`);
    process.exitCode = 1;
  }
}

// CLI entry point — runs when executed directly via `node scripts/validate-config.mjs`
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/validate-config.mjs")) {
  main();
}
