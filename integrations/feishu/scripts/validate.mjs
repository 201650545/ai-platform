import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const ROOT = path.resolve("site");

async function walk(directory) {
  const output = [];
  const entries = await fs.readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      output.push(...await walk(fullPath));
    } else if (entry.isFile()) {
      output.push(fullPath);
    }
  }
  return output;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

const FORBIDDEN_PATTERNS = [
  /"app_secret"\s*:\s*"[^"]{10,}"/i,
  /"tenant_access_token"\s*:\s*"[^"]{10,}"/i,
  /"user_access_token"\s*:\s*"[^"]{10,}"/i,
  /"authorization"\s*:\s*"[^"]{10,}"/i,
  /"client_secret"\s*:\s*"[^"]{10,}"/i,
  /\bbearer\s+[a-z0-9_-]{20,}\b/i,
  /"github_token"\s*:\s*"[^"]{10,}"/i
];

const FORBIDDEN_FILES = [".env", ".env.local", ".env.production", "debug-response.json", "api-cache.json", "raw-response.json"];

async function main() {
  // 1. manifest.json must exist and be parseable
  const manifestPath = path.join(ROOT, "data", "manifest.json");
  const manifestText = await fs.readFile(manifestPath, "utf8");
  const manifest = JSON.parse(manifestText);

  // 2. schema_version check
  assert(manifest.schema_version === 2, `manifest schema_version 必须为 2，当前为 ${manifest.schema_version}`);
  assert(Array.isArray(manifest.tables), "manifest.tables 必须为数组");
  assert(manifest.tables.length > 0, "manifest 没有数据表");
  assert(manifest.base?.name, "manifest 缺少 base.name");

  // 3. Check slugs unique
  const slugSet = new Set();
  for (const table of manifest.tables) {
    assert(table.slug, `${table.name} 缺少 slug`);
    assert(!slugSet.has(table.slug), `slug 重复：${table.slug}`);
    slugSet.add(table.slug);
  }

  // Build slug set for relation resolution check
  const knownSlugs = new Set(manifest.tables.map(t => t.slug));

  // 4. Validate each table
  for (const table of manifest.tables) {
    assert(table.name, "表缺少 name");
    assert(table.view_name, `${table.name} 缺少 view_name`);
    assert(typeof table.field_count === "number", `${table.name} field_count 必须为数字`);
    assert(typeof table.record_count === "number", `${table.name} record_count 必须为数字`);
    assert(table.fields_file, `${table.name} 缺少 fields_file`);
    assert(Array.isArray(table.record_files) && table.record_files.length > 0, `${table.name} 缺少 record_files`);

    // 4a. fields.json exists and checksums match
    const fieldsPath = path.join(ROOT, table.fields_file);
    const fieldsText = await fs.readFile(fieldsPath, "utf8");
    const fieldsData = JSON.parse(fieldsText);

    assert(Buffer.byteLength(fieldsText) === table.fields_bytes, `${table.name} fields.json 字节数不一致`);
    assert(sha256(fieldsText) === table.fields_sha256, `${table.name} fields.json SHA-256 不一致`);
    assert(Array.isArray(fieldsData.fields), `${table.name} fields.json 缺少 fields 数组`);
    assert(fieldsData.fields.length === table.field_count, `${table.name} 字段数不一致：manifest=${table.field_count}, 实际=${fieldsData.fields.length}`);

    // 4b. Validate record files
    let totalRecords = 0;
    const recordIds = new Set();

    for (const rf of table.record_files) {
      const relativePath = rf.path.replace(/^data\//, "");
      const localPath = path.join(ROOT, "data", relativePath);
      const text = await fs.readFile(localPath, "utf8");
      const payload = JSON.parse(text);

      assert(Array.isArray(payload.records), `${rf.path} records 不是数组`);
      assert(Buffer.byteLength(text) === rf.bytes, `${rf.path} 字节数不一致`);
      assert(sha256(text) === rf.sha256, `${rf.path} SHA-256 不一致`);
      assert(payload.records.length === rf.record_count, `${rf.path} 记录数不一致`);

      for (const record of payload.records) {
        if (record.record_id) {
          assert(!recordIds.has(record.record_id), `${table.name} 存在重复 record_id：${record.record_id}`);
          recordIds.add(record.record_id);
        }
      }
      totalRecords += payload.records.length;
    }

    assert(totalRecords === table.record_count, `${table.name} 记录总数不一致：manifest=${table.record_count}, 实际=${totalRecords}`);
  }

  // 5. schema.json exists and is valid
  const schemaPath = path.join(ROOT, "data", "schema.json");
  const schemaText = await fs.readFile(schemaPath, "utf8");
  const schema = JSON.parse(schemaText);

  assert(schema.schema_version === 1, `schema.json schema_version 必须为 1`);
  assert(Array.isArray(schema.tables), "schema.tables 必须为数组");
  assert(schema.tables.length === manifest.tables.length, `schema 表数(${schema.tables.length})与 manifest(${manifest.tables.length})不一致`);

  // 6. Check relation target slugs
  for (const sTable of schema.tables) {
    assert(sTable.slug, `schema 表缺少 slug`);
    assert(knownSlugs.has(sTable.slug), `schema 中的 slug "${sTable.slug}" 不在 manifest 中`);

    for (const field of sTable.fields) {
      if (field.relation) {
        if (field.relation.resolved === true) {
          assert(field.relation.target_table_slug, `${sTable.slug}.${field.field_name} resolved=true 但缺少 target_table_slug`);
          assert(knownSlugs.has(field.relation.target_table_slug),
            `${sTable.slug}.${field.field_name} 关联目标 slug "${field.relation.target_table_slug}" 不在公开表中`);
        } else {
          assert(field.relation.target_table_slug === null,
            `${sTable.slug}.${field.field_name} unresolved 但 target_table_slug 不为 null`);
        }
      }
    }
  }

  // 7. index.html exists
  const indexPath = path.join(ROOT, "index.html");
  const indexText = await fs.readFile(indexPath, "utf8");
  assert(indexText.includes("manifest.json"), "index.html 缺少 manifest.json 链接");
  assert(indexText.includes("schema.json"), "index.html 缺少 schema.json 链接");

  // 8. Scan ALL files for sensitive information
  const files = await walk(ROOT);
  for (const file of files) {
    const text = await fs.readFile(file, "utf8");
    for (const pattern of FORBIDDEN_PATTERNS) {
      if (pattern.test(text)) {
        throw new Error(`公开输出疑似包含敏感信息：${path.relative(ROOT, file)} (匹配: ${pattern.source})`);
      }
    }
  }

  // 9. Check for forbidden files
  for (const file of files) {
    const basename = path.basename(file);
    if (FORBIDDEN_FILES.includes(basename)) {
      throw new Error(`公开目录中存在禁止文件：${path.relative(ROOT, file)}`);
    }
  }

  // 10. Check no table_id, app_token, or BASE_TOKEN in output
  for (const file of files) {
    const text = await fs.readFile(file, "utf8");
    assert(!text.includes("tblIeOhkaE") && !text.includes("tblKrJM8") && !text.includes("tblWoRH8") && !text.includes("tblAgZiB"),
      `公开输出疑似包含内部 table_id：${path.relative(ROOT, file)}`);
    assert(!text.includes("K15hbHNwtaY3BWs1STLcG092n4g"),
      `公开输出疑似包含 app_token：${path.relative(ROOT, file)}`);
  }

  console.log(`验证通过：${manifest.tables.length} 张表，${files.length} 个文件。`);
  for (const table of manifest.tables) {
    console.log(`  ${table.name} (${table.slug}): ${table.field_count} 字段, ${table.record_count} 记录, ${table.record_files.length} 分片`);
  }
}

main().catch((error) => {
  console.error(`验证失败：${error.message}`);
  process.exitCode = 1;
});
