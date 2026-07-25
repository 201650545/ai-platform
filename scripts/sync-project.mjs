// scripts/sync-project.mjs — Sync a single project from Feishu to public output.
// This is the workhorse: discovers tables, reads records, transforms, writes output.
// Used by sync-hub.mjs for each project, or standalone via CLI.

import fs from "node:fs/promises";
import path from "node:path";

import { loadHubConfig, loadCredentialProfiles, loadProjectConfig, resolveCredentials } from "../lib/config.mjs";
import { getTenantAccessToken, listTables, listViews, listFields, listRecords, exactOne } from "../lib/feishu.mjs";
import { assertNoSecrets, sha256 } from "../lib/security.mjs";
import { selectRecord, buildSchemaEntry, escapeHtml } from "../lib/transform.mjs";
import { writeJson, writeText, generateBuildId, buildProjectIndexHtml } from "../lib/output.mjs";

/**
 * Sync a single project.
 * @param {string} slug - Project slug.
 * @param {object} hubConfig - Hub configuration from hub.yaml.
 * @param {object} credentialProfiles - Credential profiles.
 * @param {object} env - Environment variables (process.env).
 * @param {string} buildId - Global build_id for this sync run.
 * @param {object} options - { dryRun, force, outputDir }
 * @returns {object} - { slug, status, manifest, schema, warnings, error }
 */
export async function syncProject(slug, hubConfig, credentialProfiles, env, buildId, options = {}) {
  const projectConfig = await loadProjectConfig(slug);
  const projectName = projectConfig.project.title;
  const outputDir = options.outputDir || path.resolve(".", hubConfig.output.root_dir);
  const projectDir = path.join(outputDir, hubConfig.output.projects_dir, slug);

  console.log(`\n[${slug}] 开始同步项目：${projectName}`);

  // Resolve credentials
  const profileName = projectConfig.source.credential_profile;
  const profileConfig = credentialProfiles.profiles[profileName];
  if (!profileConfig) throw new Error(`[${slug}] 凭据配置 ${profileName} 不存在`);

  const creds = resolveCredentials(profileConfig, env, projectConfig.source.base_key);
  if (!creds) throw new Error(`[${slug}] 环境变量中缺少所需凭据`);

  const { appId, appSecret, appToken } = creds;
  const secretValues = [appSecret, appToken].filter(Boolean);

  // Get tenant access token
  console.log(`[${slug}] 获取飞书访问凭证……`);
  const tenantToken = await getTenantAccessToken(appId, appSecret);
  secretValues.push(tenantToken);

  const generatedAt = new Date().toISOString();
  const exportViewName = projectConfig.source.export_view_name || hubConfig.defaults.export_view_name;
  const chunkSize = projectConfig.export?.chunk_size || hubConfig.defaults.chunk_size;
  const includeRecordId = projectConfig.export?.include_record_id ?? hubConfig.defaults.include_record_id;
  const stableSort = projectConfig.export?.stable_sort ?? hubConfig.defaults.stable_sort;
  const maxTableBytes = hubConfig.defaults.max_table_bytes;

  // Sync to a temp directory first, then atomically replace on success.
  // This ensures that if sync fails midway, the previous successful output
  // remains intact for fault recovery (hydrate-existing-project.mjs).
  const tempDir = `${projectDir}.tmp`;
  await fs.rm(tempDir, { recursive: true, force: true });
  await fs.mkdir(tempDir, { recursive: true });

  console.log(`[${slug}] 读取数据表清单……`);
  const allTables = await listTables(tenantToken, appToken);

  // Determine which tables to export
  let tablesToExport;
  if (Array.isArray(projectConfig.tables) && projectConfig.tables.length > 0) {
    // Explicit table list in config
    tablesToExport = projectConfig.tables.filter(t => t.enabled !== false);
  } else {
    // Auto-discover tables with the export view
    console.log(`[${slug}] 自动发现带 "${exportViewName}" 视图的表……`);
    tablesToExport = [];
    for (const table of allTables) {
      const views = await listViews(tenantToken, appToken, table.table_id);
      if (views.some(v => v.view_name === exportViewName)) {
        // Auto-discover: use all fields (they'll be filtered by view)
        const fields = await listFields(tenantToken, appToken, table.table_id);
        tablesToExport.push({
          table_name: table.name,
          table_slug: slugify(table.name),
          view_name: exportViewName,
          enabled: true,
          fields: fields.map(f => f.field_name).filter(Boolean)
        });
      }
    }
    if (tablesToExport.length === 0) {
      throw new Error(`[${slug}] 没有找到带 "${exportViewName}" 视图的表`);
    }
  }

  // Build table_id → slug mapping for relation resolution
  const tableIdToSlug = new Map();
  for (const tc of tablesToExport) {
    const table = allTables.find(t => t.name === tc.table_name);
    if (table?.table_id) {
      tableIdToSlug.set(table.table_id, tc.table_slug);
      tableIdToSlug.set(table.table_id + ":name", tc.table_name);
    }
  }

  const manifest = {
    schema_version: 2,
    project_slug: slug,
    build_id: buildId,
    generated_at: generatedAt,
    base: { name: projectName },
    tables: []
  };
  const schemaTables = [];
  const warnings = [];

  for (const tc of tablesToExport) {
    console.log(`[${slug}] 同步数据表：${tc.table_name}`);
    const table = exactOne(allTables, "name", tc.table_name, `[${slug}] 数据表`);
    const tableId = table.table_id;
    if (!tableId) throw new Error(`[${slug}] 数据表缺少 table_id：${tc.table_name}`);

    const [views, fields] = await Promise.all([
      listViews(tenantToken, appToken, tableId),
      listFields(tenantToken, appToken, tableId)
    ]);

    const view = exactOne(views, "view_name", tc.view_name, `[${slug}] ${tc.table_name} 的视图`);
    const viewId = view.view_id;
    if (!viewId) throw new Error(`[${slug}] 视图缺少 view_id：${tc.view_name}`);

    // Build field metadata
    const fieldByName = new Map();
    for (const f of fields) {
      if (!f.field_name) continue;
      if (fieldByName.has(f.field_name)) throw new Error(`[${slug}] ${tc.table_name} 存在重名字段：${f.field_name}`);
      fieldByName.set(f.field_name, f);
    }

    // Validate configured fields exist
    const fieldMeta = {};
    for (const fn of tc.fields) {
      if (!fieldByName.has(fn)) {
        throw new Error(`[${slug}] ${tc.table_name} 缺少配置字段：${fn}`);
      }
      const f = fieldByName.get(fn);
      fieldMeta[fn] = { type: f.type, ui_type: f.ui_type };
    }

    const selectedFieldsMeta = tc.fields.map(name => {
      const f = fieldByName.get(name);
      return { field_name: name, field_id: f.field_id, type: f.type, ui_type: f.ui_type, property: f.property };
    });

    // Fetch and transform records
    const rawRecords = await listRecords(tenantToken, appToken, tableId, viewId, tc.fields);
    const records = rawRecords.map(r => selectRecord(r, tc.fields, fieldMeta, {
      include_record_id: includeRecordId,
      include_timestamps: projectConfig.export?.include_timestamps ?? false
    }));

    if (stableSort) {
      records.sort((a, b) => {
        const aid = a.record_id || "";
        const bid = b.record_id || "";
        return aid.localeCompare(bid);
      });
    }

    // Write fields.json (to temp dir)
    const basePath = `tables/${tc.table_slug}`;
    const fieldsWrite = await writeJson(tempDir, `${basePath}/fields.json`, {
      schema_version: 1,
      table_name: tc.table_name,
      view_name: tc.view_name,
      fields: selectedFieldsMeta.map(f => ({
        field_name: f.field_name,
        field_id: f.field_id,
        type: f.type,
        ui_type: f.ui_type
      }))
    }, secretValues);

    // Write record shards
    const recordFiles = [];
    let totalBytes = fieldsWrite.bytes;

    for (let offset = 0; offset < records.length; offset += chunkSize) {
      const chunkNum = Math.floor(offset / chunkSize) + 1;
      const filename = `records-${String(chunkNum).padStart(4, "0")}.json`;
      const chunkRecords = records.slice(offset, offset + chunkSize);
      const relPath = `${basePath}/${filename}`;
      const result = await writeJson(tempDir, relPath, {
        schema_version: 1,
        table_name: tc.table_name,
        view_name: tc.view_name,
        chunk: chunkNum,
        records: chunkRecords
      }, secretValues);
      totalBytes += result.bytes;
      recordFiles.push({ path: relPath, record_count: chunkRecords.length, bytes: result.bytes, sha256: result.sha256 });
    }

    // Ensure at least one shard even for empty tables
    if (records.length === 0) {
      const relPath = `${basePath}/records-0001.json`;
      const result = await writeJson(tempDir, relPath, {
        schema_version: 1, table_name: tc.table_name, view_name: tc.view_name, chunk: 1, records: []
      }, secretValues);
      totalBytes += result.bytes;
      recordFiles.push({ path: relPath, record_count: 0, bytes: result.bytes, sha256: result.sha256 });
    }

    if (totalBytes > maxTableBytes) {
      throw new Error(`[${slug}] ${tc.table_name} 输出 ${totalBytes} 字节超过上限 ${maxTableBytes}`);
    }

    // Convert paths to be relative to project dir (for manifest)
    manifest.tables.push({
      name: tc.table_name,
      slug: tc.table_slug,
      view_name: tc.view_name,
      field_count: tc.fields.length,
      record_count: records.length,
      fields_file: `${basePath}/fields.json`,
      fields_bytes: fieldsWrite.bytes,
      fields_sha256: fieldsWrite.sha256,
      record_files: recordFiles
    });

    schemaTables.push(buildSchemaEntry(tc, selectedFieldsMeta, tableIdToSlug, generatedAt));
    console.log(`[${slug}]   ${tc.table_name}: ${records.length} 条记录，${recordFiles.length} 个分片`);
  }

  // Sort by slug for stable diff
  manifest.tables.sort((a, b) => a.slug.localeCompare(b.slug));

  // Write manifest.json
  await writeJson(tempDir, "manifest.json", manifest, secretValues);
  console.log(`[${slug}] manifest.json written`);

  // Write schema.json
  const schema = {
    schema_version: 1,
    project_slug: slug,
    build_id: buildId,
    generated_at: generatedAt,
    base: { name: projectName },
    tables: schemaTables.sort((a, b) => a.slug.localeCompare(b.slug))
  };
  await writeJson(tempDir, "schema.json", schema, secretValues);
  console.log(`[${slug}] schema.json written`);

  // Write summary.md
  const summary = buildProjectSummary(projectConfig, manifest, schema);
  await writeText(tempDir, "summary.md", summary, secretValues);
  console.log(`[${slug}] summary.md written`);

  // Write status.json
  const status = {
    project_slug: slug,
    build_id: buildId,
    sync_status: "ok",
    is_stale: false,
    last_attempt_at: generatedAt,
    last_success_at: generatedAt,
    source_record_count: manifest.tables.reduce((sum, t) => sum + t.record_count, 0),
    published_record_count: manifest.tables.reduce((sum, t) => sum + t.record_count, 0),
    warnings
  };
  await writeJson(tempDir, "status.json", status, secretValues);
  console.log(`[${slug}] status.json written`);

  // Write project index.html
  const indexHtml = buildProjectIndexHtml(projectConfig, manifest, schema, buildId);
  assertNoSecrets(indexHtml, secretValues, "index.html");
  await fs.writeFile(path.join(tempDir, "index.html"), indexHtml, "utf8");
  console.log(`[${slug}] index.html written`);

  // Atomic swap: remove old project dir, rename temp to project
  await fs.rm(projectDir, { recursive: true, force: true });
  await fs.rename(tempDir, projectDir);
  console.log(`[${slug}] atomic swap complete`);

  // Mirror to legacy paths if configured (from the final projectDir)
  if (projectConfig.compatibility?.mirror_to_legacy_root) {
    const legacyBasePath = projectConfig.compatibility.legacy_base_path || "data";
    await mirrorToLegacyPaths(projectDir, outputDir, legacyBasePath, secretValues);
    console.log(`[${slug}] legacy paths mirrored to ${legacyBasePath}/`);
  }

  console.log(`[${slug}] 同步完成：${manifest.tables.length} 张表已公开导出。`);

  return { slug, status: "ok", manifest, schema, warnings, error: null };
}

/**
 * Mirror project output to legacy paths for backward compatibility.
 * Old URLs: /data/manifest.json, /data/schema.json, /data/<table-slug>/*
 * New URLs: /projects/<slug>/manifest.json, /projects/<slug>/tables/<table-slug>/*
 */
async function mirrorToLegacyPaths(projectDir, outputDir, legacyBasePath, secretValues) {
  const legacyDir = path.join(outputDir, legacyBasePath);

  // Copy manifest.json
  const manifestText = await fs.readFile(path.join(projectDir, "manifest.json"), "utf8");
  await fs.mkdir(legacyDir, { recursive: true });
  await fs.writeFile(path.join(legacyDir, "manifest.json"), manifestText, "utf8");

  // Copy schema.json
  const schemaText = await fs.readFile(path.join(projectDir, "schema.json"), "utf8");
  await fs.writeFile(path.join(legacyDir, "schema.json"), schemaText, "utf8");

  // Copy table directories
  const tablesDir = path.join(projectDir, "tables");
  try {
    const tableDirs = await fs.readdir(tablesDir, { withFileTypes: true });
    for (const entry of tableDirs) {
      if (entry.isDirectory()) {
        const srcDir = path.join(tablesDir, entry.name);
        const destDir = path.join(legacyDir, entry.name);
        await fs.mkdir(destDir, { recursive: true });
        const files = await fs.readdir(srcDir);
        for (const file of files) {
          await fs.copyFile(path.join(srcDir, file), path.join(destDir, file));
        }
      }
    }
  } catch {
    // tables dir may not exist in some edge cases
  }

  // Also write a legacy index.html that points to the new paths
  const manifest = JSON.parse(manifestText);
  const legacyIndex = buildLegacyIndexHtml(manifest);
  assertNoSecrets(legacyIndex, secretValues, "legacy index.html");
  await fs.writeFile(path.join(outputDir, "index.html"), legacyIndex, "utf8");
}

/**
 * Build a legacy-compatible index.html at the root level.
 * This maintains the old single-project homepage appearance.
 */
function buildLegacyIndexHtml(manifest) {
  const tablesHtml = manifest.tables.map(t => {
    const recordLinks = t.record_files.map(rf =>
      `      <li><a href="${rf.path}">${rf.path.split("/").pop()}</a> — ${rf.record_count} records, ${rf.bytes} bytes</li>`
    ).join("\n");
    return `  <section>
    <h2>${escapeHtml(t.name)}</h2>
    <p>Slug: <code>${escapeHtml(t.slug)}</code> | View: ${escapeHtml(t.view_name)} | Fields: ${t.field_count} | Records: ${t.record_count}</p>
    <ul>
      <li><a href="${t.fields_file}">fields.json</a></li>
${recordLinks}
    </ul>
  </section>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feishu Data Hub</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#333}
h1{border-bottom:2px solid #e0e0e0;padding-bottom:.5rem}
h2{margin-top:2rem;color:#1a73e8}
code{background:#f5f5f5;padding:.1em .3em;border-radius:3px;font-size:.9em}
section{border:1px solid #e0e0e0;border-radius:8px;padding:1rem 1.5rem;margin:1rem 0}
li{margin:.2rem 0}
a{color:#1a73e8;text-decoration:none}
a:hover{text-decoration:underline}
.meta{color:#666;font-size:.9rem}
.nav{margin:1rem 0;padding:.5rem 0;border-bottom:1px solid #eee}
.nav a{margin-right:1rem}
</style>
</head>
<body>
<h1>Feishu Data Hub</h1>
<p class="meta">Build: <code>${escapeHtml(manifest.build_id || "unknown")}</code> | Generated: ${escapeHtml(manifest.generated_at)} | Projects: <a href="catalog.json">catalog.json</a></p>
<div class="nav">
  <a href="catalog.json">catalog.json</a>
  <a href="data/manifest.json">data/manifest.json</a>
  <a href="data/schema.json">data/schema.json</a>
  <a href="projects/learning-english/">learning-english project</a>
</div>
${tablesHtml}
</body>
</html>
`;
}

/**
 * Build a human-readable summary.md for a project.
 */
function buildProjectSummary(projectConfig, manifest, schema) {
  const lines = [
    `# ${projectConfig.project.title}`,
    "",
    `**Slug:** \`${projectConfig.project.slug}\``,
    `**Description:** ${projectConfig.project.description || "—"}`,
    `**Group:** ${projectConfig.project.group || "—"}`,
    `**Status:** ${projectConfig.project.status || "active"}`,
    `**Build ID:** \`${manifest.build_id}\``,
    `**Generated:** ${manifest.generated_at}`,
    "",
    "## Tables",
    ""
  ];

  for (const t of manifest.tables) {
    lines.push(`### ${t.name} (\`${t.slug}\`)`);
    lines.push(`- **View:** ${t.view_name}`);
    lines.push(`- **Fields:** ${t.field_count}`);
    lines.push(`- **Records:** ${t.record_count}`);
    lines.push(`- **Files:** [fields.json](${t.fields_file})`);
    for (const rf of t.record_files) {
      lines.push(`  - [${rf.path.split("/").pop()}](${rf.path}) — ${rf.record_count} records`);
    }
    lines.push("");
  }

  // Add relation info from schema
  const relations = [];
  for (const sTable of schema.tables) {
    for (const field of sTable.fields) {
      if (field.relation?.resolved) {
        relations.push(`- \`${sTable.slug}.${field.field_name}\` → \`${field.relation.target_table_slug}\``);
      } else if (field.relation && !field.relation.resolved) {
        relations.push(`- \`${sTable.slug}.${field.field_name}\` → (unresolved: ${field.relation.target_table_name || "unknown"})`);
      }
    }
  }
  if (relations.length > 0) {
    lines.push("## Relations", "");
    lines.push(...relations, "");
  }

  return lines.join("\n");
}

/** Simple slugify for auto-discovered table names. */
function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "table";
}

// CLI entry point — run standalone for a single project
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/sync-project.mjs")) {
  const slug = process.argv[2];
  if (!slug) {
    console.error("用法: node scripts/sync-project.mjs <project-slug>");
    process.exit(1);
  }

  const env = process.env;
  const buildId = generateBuildId("local");

  Promise.resolve()
    .then(async () => {
      const hubConfig = await loadHubConfig();
      const credentialProfiles = await loadCredentialProfiles();
      const result = await syncProject(slug, hubConfig, credentialProfiles, env, buildId);
      console.log(`\n项目 ${slug} 同步完成：${result.manifest.tables.length} 张表`);
    })
    .catch(e => {
      console.error(`同步失败：${e.message}`);
      process.exitCode = 1;
    });
}

// syncProject is exported via the `export async function` declaration above.
