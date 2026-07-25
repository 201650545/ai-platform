// scripts/validate-output.mjs — Validates the public output directory.
// Checks catalog.json, each project's manifest/schema/status/summary/index,
// verifies checksums for fields.json and record files, checks record counts,
// detects duplicate record_ids, and validates relation target slugs.

import fs from "node:fs/promises";
import path from "node:path";

import { loadHubConfig } from "../lib/config.mjs";
import { sha256 } from "../lib/security.mjs";
import { walkDir } from "../lib/output.mjs";

/**
 * Read and parse a JSON file.
 * @param {string} filePath - Absolute path to the JSON file.
 * @returns {Promise<object>} - Parsed JSON object.
 */
async function readJson(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return JSON.parse(text);
}

/**
 * Check if a file exists.
 * @param {string} filePath - Absolute path to check.
 * @returns {Promise<boolean>}
 */
async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validate the public output directory.
 * Collects all errors rather than stopping at the first failure.
 * @param {string} [rootDir] - Root output directory (defaults to hub config output.root_dir).
 * @returns {Promise<object>} - { errors, stats }
 */
export async function validateOutput(rootDir) {
  const errors = [];
  const stats = {
    projects: 0,
    tables: 0,
    records: 0,
    filesChecked: 0,
    totalFiles: 0,
  };

  const hubConfig = await loadHubConfig();
  const outputDir = rootDir || path.resolve(".", hubConfig.output.root_dir);
  const projectsDir = hubConfig.output.projects_dir || "projects";
  const catalogFile = hubConfig.output.catalog_file || "catalog.json";

  console.log(`输出目录：${outputDir}`);

  // 1. Validate catalog.json exists, is parseable, has catalog_version=1 and projects array
  const catalogPath = path.join(outputDir, catalogFile);
  let catalog = null;
  try {
    catalog = await readJson(catalogPath);
    if (catalog.catalog_version !== 1) {
      errors.push(`catalog.json: catalog_version 必须为 1，当前为 ${catalog.catalog_version}`);
      console.error(`[失败] catalog.json: catalog_version 必须为 1，当前为 ${catalog.catalog_version}`);
    }
    if (!Array.isArray(catalog.projects)) {
      errors.push("catalog.json: projects 必须为数组");
      console.error("[失败] catalog.json: projects 必须为数组");
    }
    console.log(`[通过] catalog.json 验证通过（catalog_version=${catalog.catalog_version}, ${catalog.projects?.length || 0} 个项目）`);
  } catch (error) {
    errors.push(`catalog.json: ${error.message}`);
    console.error(`[失败] catalog.json 验证失败：${error.message}`);
    // Cannot continue without catalog
    return { errors, stats };
  }

  // 2. Validate each project in catalog
  for (const entry of catalog.projects || []) {
    const slug = entry.slug;
    if (!slug) {
      errors.push("catalog: 存在缺少 slug 的项目条目");
      console.error("[失败] catalog: 存在缺少 slug 的项目条目");
      continue;
    }

    stats.projects++;
    const projectDir = path.join(outputDir, projectsDir, slug);

    try {
      await validateProjectOutput(projectDir, slug, errors, stats);
    } catch (error) {
      errors.push(`项目 ${slug}: ${error.message}`);
      console.error(`[失败] 项目 ${slug} 验证失败：${error.message}`);
    }
  }

  // 3. Validate legacy compatibility paths (data/manifest.json, data/schema.json) if they exist
  await validateLegacyPaths(outputDir, errors, stats);

  // 4. Count total files in output directory using walkDir
  try {
    const allFiles = await walkDir(outputDir);
    stats.totalFiles = allFiles.length;
  } catch {
    stats.totalFiles = 0;
  }

  return { errors, stats };
}

/**
 * Validate a single project's output directory.
 * @param {string} projectDir - Absolute path to the project output directory.
 * @param {string} slug - Project slug.
 * @param {string[]} errors - Shared errors array to push to.
 * @param {object} stats - Shared stats object to update.
 */
async function validateProjectOutput(projectDir, slug, errors, stats) {
  // manifest.json — must exist, be parseable, have schema_version=2
  const manifestPath = path.join(projectDir, "manifest.json");
  let manifest = null;
  try {
    manifest = await readJson(manifestPath);
    if (manifest.schema_version !== 2) {
      errors.push(`${slug}/manifest.json: schema_version 必须为 2，当前为 ${manifest.schema_version}`);
      console.error(`[失败] ${slug}/manifest.json: schema_version 必须为 2，当前为 ${manifest.schema_version}`);
    }
    if (!Array.isArray(manifest.tables)) {
      errors.push(`${slug}/manifest.json: tables 必须为数组`);
      console.error(`[失败] ${slug}/manifest.json: tables 必须为数组`);
    }
  } catch (error) {
    throw new Error(`manifest.json: ${error.message}`);
  }

  // schema.json — must exist, be parseable, have schema_version=1
  const schemaPath = path.join(projectDir, "schema.json");
  let schema = null;
  try {
    schema = await readJson(schemaPath);
    if (schema.schema_version !== 1) {
      errors.push(`${slug}/schema.json: schema_version 必须为 1，当前为 ${schema.schema_version}`);
      console.error(`[失败] ${slug}/schema.json: schema_version 必须为 1，当前为 ${schema.schema_version}`);
    }
    if (!Array.isArray(schema.tables)) {
      errors.push(`${slug}/schema.json: tables 必须为数组`);
      console.error(`[失败] ${slug}/schema.json: tables 必须为数组`);
    }
  } catch (error) {
    throw new Error(`schema.json: ${error.message}`);
  }

  // status.json — must exist and be parseable
  const statusPath = path.join(projectDir, "status.json");
  try {
    await readJson(statusPath);
  } catch (error) {
    throw new Error(`status.json: ${error.message}`);
  }

  // summary.md — must exist
  const summaryPath = path.join(projectDir, "summary.md");
  if (!(await fileExists(summaryPath))) {
    throw new Error("summary.md 不存在");
  }

  // index.html — must exist
  const indexPath = path.join(projectDir, "index.html");
  if (!(await fileExists(indexPath))) {
    throw new Error("index.html 不存在");
  }

  // Build known slugs set from manifest tables
  const knownSlugs = new Set((manifest.tables || []).map(t => t.slug));

  // Validate each table in manifest
  for (const table of manifest.tables || []) {
    stats.tables++;
    await validateTableOutput(projectDir, table, errors, slug, stats);
  }

  // Schema table count must match manifest
  if (schema.tables && manifest.tables) {
    if (schema.tables.length !== manifest.tables.length) {
      errors.push(`${slug}: schema 表数(${schema.tables.length})与 manifest(${manifest.tables.length})不一致`);
      console.error(`[失败] ${slug}: schema 表数(${schema.tables.length})与 manifest(${manifest.tables.length})不一致`);
    }
  }

  // Validate relation target_table_slug — must be in known slugs when resolved=true
  for (const sTable of schema.tables || []) {
    if (!sTable.slug || !knownSlugs.has(sTable.slug)) {
      errors.push(`${slug}: schema 中的 slug "${sTable.slug}" 不在 manifest 中`);
      console.error(`[失败] ${slug}: schema 中的 slug "${sTable.slug}" 不在 manifest 中`);
      continue;
    }
    for (const field of sTable.fields || []) {
      if (field.relation && field.relation.resolved === true) {
        if (!field.relation.target_table_slug) {
          errors.push(`${slug}/${sTable.slug}.${field.field_name}: resolved=true 但缺少 target_table_slug`);
          console.error(`[失败] ${slug}/${sTable.slug}.${field.field_name}: resolved=true 但缺少 target_table_slug`);
        } else if (!knownSlugs.has(field.relation.target_table_slug)) {
          errors.push(`${slug}/${sTable.slug}.${field.field_name}: 关联目标 slug "${field.relation.target_table_slug}" 不在公开表中`);
          console.error(`[失败] ${slug}/${sTable.slug}.${field.field_name}: 关联目标 slug "${field.relation.target_table_slug}" 不在公开表中`);
        }
      }
    }
  }

  const totalRecords = (manifest.tables || []).reduce((sum, t) => sum + (t.record_count || 0), 0);
  console.log(`[通过] 项目 ${slug} 验证通过（${(manifest.tables || []).length} 张表，${totalRecords} 条记录）`);
}

/**
 * Validate a single table's output (fields.json and record files).
 * @param {string} projectDir - Absolute path to the project output directory.
 * @param {object} table - Table entry from manifest.
 * @param {string[]} errors - Shared errors array to push to.
 * @param {string} projectSlug - Project slug for error messages.
 * @param {object} stats - Shared stats object to update.
 */
async function validateTableOutput(projectDir, table, errors, projectSlug, stats) {
  const tableName = table.name || "(unknown)";

  // fields.json — must exist, checksums must match (fields_bytes, fields_sha256)
  const fieldsPath = path.join(projectDir, table.fields_file);
  try {
    const fieldsText = await fs.readFile(fieldsPath, "utf8");
    const fieldsData = JSON.parse(fieldsText);

    if (Buffer.byteLength(fieldsText) !== table.fields_bytes) {
      errors.push(`${projectSlug}/${tableName}: fields.json 字节数不一致：manifest=${table.fields_bytes}, 实际=${Buffer.byteLength(fieldsText)}`);
      console.error(`[失败] ${projectSlug}/${tableName}: fields.json 字节数不一致`);
    }
    if (sha256(fieldsText) !== table.fields_sha256) {
      errors.push(`${projectSlug}/${tableName}: fields.json SHA-256 不一致`);
      console.error(`[失败] ${projectSlug}/${tableName}: fields.json SHA-256 不一致`);
    }
    if (!Array.isArray(fieldsData.fields)) {
      errors.push(`${projectSlug}/${tableName}: fields.json 缺少 fields 数组`);
      console.error(`[失败] ${projectSlug}/${tableName}: fields.json 缺少 fields 数组`);
    }
    stats.filesChecked++;
  } catch (error) {
    errors.push(`${projectSlug}/${tableName}: fields.json: ${error.message}`);
    console.error(`[失败] ${projectSlug}/${tableName}: fields.json 验证失败：${error.message}`);
  }

  // Validate each record file — path must exist, checksums must match, record_count must match
  let totalRecords = 0;
  const recordIds = new Set();

  for (const rf of table.record_files || []) {
    const localPath = path.join(projectDir, rf.path);
    try {
      const text = await fs.readFile(localPath, "utf8");
      const payload = JSON.parse(text);

      if (!Array.isArray(payload.records)) {
        errors.push(`${projectSlug}/${tableName}: ${rf.path} records 不是数组`);
        console.error(`[失败] ${projectSlug}/${tableName}: ${rf.path} records 不是数组`);
        continue;
      }
      if (Buffer.byteLength(text) !== rf.bytes) {
        errors.push(`${projectSlug}/${tableName}: ${rf.path} 字节数不一致：manifest=${rf.bytes}, 实际=${Buffer.byteLength(text)}`);
        console.error(`[失败] ${projectSlug}/${tableName}: ${rf.path} 字节数不一致`);
      }
      if (sha256(text) !== rf.sha256) {
        errors.push(`${projectSlug}/${tableName}: ${rf.path} SHA-256 不一致`);
        console.error(`[失败] ${projectSlug}/${tableName}: ${rf.path} SHA-256 不一致`);
      }
      if (payload.records.length !== rf.record_count) {
        errors.push(`${projectSlug}/${tableName}: ${rf.path} 记录数不一致：manifest=${rf.record_count}, 实际=${payload.records.length}`);
        console.error(`[失败] ${projectSlug}/${tableName}: ${rf.path} 记录数不一致`);
      }

      // Check for duplicate record_ids within the table
      for (const record of payload.records) {
        if (record.record_id) {
          if (recordIds.has(record.record_id)) {
            errors.push(`${projectSlug}/${tableName}: 重复 record_id：${record.record_id}`);
            console.error(`[失败] ${projectSlug}/${tableName}: 重复 record_id：${record.record_id}`);
          } else {
            recordIds.add(record.record_id);
          }
        }
      }

      totalRecords += payload.records.length;
      stats.records += payload.records.length;
      stats.filesChecked++;
    } catch (error) {
      errors.push(`${projectSlug}/${tableName}: ${rf.path}: ${error.message}`);
      console.error(`[失败] ${projectSlug}/${tableName}: ${rf.path} 验证失败：${error.message}`);
    }
  }

  // Total record count must match manifest
  if (totalRecords !== table.record_count) {
    errors.push(`${projectSlug}/${tableName}: 记录总数不一致：manifest=${table.record_count}, 实际=${totalRecords}`);
    console.error(`[失败] ${projectSlug}/${tableName}: 记录总数不一致：manifest=${table.record_count}, 实际=${totalRecords}`);
  }
}

/**
 * Validate legacy compatibility paths (data/manifest.json, data/schema.json).
 * Only validates if the files exist — they are optional.
 * @param {string} outputDir - Root output directory.
 * @param {string[]} errors - Shared errors array to push to.
 * @param {object} stats - Shared stats object to update.
 */
async function validateLegacyPaths(outputDir, errors, stats) {
  const legacyManifestPath = path.join(outputDir, "data", "manifest.json");
  const legacySchemaPath = path.join(outputDir, "data", "schema.json");

  if (await fileExists(legacyManifestPath)) {
    try {
      const manifest = await readJson(legacyManifestPath);
      if (manifest.schema_version !== 2) {
        errors.push(`遗留路径 data/manifest.json: schema_version 必须为 2，当前为 ${manifest.schema_version}`);
        console.error(`[失败] 遗留路径 data/manifest.json: schema_version 必须为 2，当前为 ${manifest.schema_version}`);
      } else {
        console.log(`[通过] 遗留路径 data/manifest.json 验证通过`);
      }
      stats.filesChecked++;
    } catch (error) {
      errors.push(`遗留路径 data/manifest.json: ${error.message}`);
      console.error(`[失败] 遗留路径 data/manifest.json 验证失败：${error.message}`);
    }
  }

  if (await fileExists(legacySchemaPath)) {
    try {
      const schema = await readJson(legacySchemaPath);
      if (schema.schema_version !== 1) {
        errors.push(`遗留路径 data/schema.json: schema_version 必须为 1，当前为 ${schema.schema_version}`);
        console.error(`[失败] 遗留路径 data/schema.json: schema_version 必须为 1，当前为 ${schema.schema_version}`);
      } else {
        console.log(`[通过] 遗留路径 data/schema.json 验证通过`);
      }
      stats.filesChecked++;
    } catch (error) {
      errors.push(`遗留路径 data/schema.json: ${error.message}`);
      console.error(`[失败] 遗留路径 data/schema.json 验证失败：${error.message}`);
    }
  }
}

/**
 * Main entry point for CLI execution.
 */
async function main() {
  try {
    console.log("=== 公开输出验证 ===\n");

    const result = await validateOutput();

    console.log("\n=== 验证摘要 ===");
    console.log(`项目数：${result.stats.projects}`);
    console.log(`数据表：${result.stats.tables}`);
    console.log(`记录数：${result.stats.records}`);
    console.log(`校验文件：${result.stats.filesChecked}`);
    console.log(`输出文件总数：${result.stats.totalFiles}`);
    console.log(`错误数：${result.errors.length}`);

    if (result.errors.length > 0) {
      console.error("\n公开输出验证失败，错误列表：");
      for (const err of result.errors) {
        console.error(`  - ${err}`);
      }
      process.exitCode = 1;
    } else {
      console.log("\n所有公开输出验证通过。");
    }
  } catch (error) {
    console.error(`输出验证异常：${error.message}`);
    process.exitCode = 1;
  }
}

// CLI entry point — runs when executed directly via `node scripts/validate-output.mjs`
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/validate-output.mjs")) {
  main();
}
