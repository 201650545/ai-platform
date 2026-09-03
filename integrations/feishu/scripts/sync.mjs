import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const API_ROOT = "https://open.feishu.cn/open-apis";
const OUTPUT_DIR = path.resolve("site");
const CONFIG_PATH = path.resolve("config/export.json");

const APP_ID = process.env.FEISHU_APP_ID;
const APP_SECRET = process.env.FEISHU_APP_SECRET;
const BASE_TOKEN = process.env.FEISHU_BASE_TOKEN;

for (const [name, value] of Object.entries({ FEISHU_APP_ID: APP_ID, FEISHU_APP_SECRET: APP_SECRET, FEISHU_BASE_TOKEN: BASE_TOKEN })) {
  if (!value || !String(value).trim()) throw new Error(`缺少必需环境变量：${name}`);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function encodeSegment(v) { return encodeURIComponent(String(v)); }
function sha256(text) { return crypto.createHash("sha256").update(text).digest("hex"); }
function escapeHtml(v) {
  return String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function assertSafeSlug(slug) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error(`slug 非法：${slug}`);
}

async function loadConfig() {
  const config = JSON.parse(await fs.readFile(CONFIG_PATH, "utf8"));
  if (config.schema_version !== 2) throw new Error("config/export.json 的 schema_version 必须为 2");
  if (!Number.isInteger(config.chunk_size) || config.chunk_size < 1 || config.chunk_size > 500) throw new Error("chunk_size 必须是 1～500 的整数");
  if (!Number.isInteger(config.max_table_bytes) || config.max_table_bytes < 1024) throw new Error("max_table_bytes 必须是大于 1024 的整数");
  if (!Array.isArray(config.tables) || config.tables.length === 0) throw new Error("至少需要配置一张表");

  const seenSlugs = new Set();
  const forbiddenFieldNames = new Set(["app_secret","tenant_access_token","user_access_token","authorization","client_secret"]);

  for (const item of config.tables) {
    if (!item.table_name || !item.table_slug || !item.view_name) {
      throw new Error("每个 tables 项都必须包含 table_name、table_slug、view_name");
    }
    assertSafeSlug(item.table_slug);
    if (seenSlugs.has(item.table_slug)) throw new Error(`slug 重复：${item.table_slug}`);
    seenSlugs.add(item.table_slug);

    if (!Array.isArray(item.fields) || item.fields.length === 0) throw new Error(`${item.table_name} 的 fields 不能为空`);
    if (item.fields.includes("*")) throw new Error(`${item.table_name} 禁止使用通配字段 *`);
    for (const fn of item.fields) {
      if (forbiddenFieldNames.has(String(fn).trim().toLowerCase())) throw new Error(`${item.table_name} 禁止公开敏感字段名：${fn}`);
    }
    if (new Set(item.fields).size !== item.fields.length) throw new Error(`${item.table_name} 的 fields 存在重复项`);
  }
  return config;
}

function retryDelay(attempt, retryAfterHeader) {
  const ra = Number(retryAfterHeader);
  if (Number.isFinite(ra) && ra > 0) return Math.min(ra * 1000, 60000);
  return Math.min(1000 * 2 ** attempt, 30000) + Math.floor(Math.random() * 500);
}

async function apiRequest(endpoint, { method = "GET", token, query = {}, body, maxAttempts = 5 } = {}) {
  const url = new URL(`${API_ROOT}${endpoint}`);
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    let response;
    try {
      response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json; charset=utf-8", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(30000)
      });
    } catch (e) {
      if (attempt === maxAttempts - 1) throw new Error(`网络请求失败：${e.message}`);
      await sleep(retryDelay(attempt)); continue;
    }
    const text = await response.text();
    let payload;
    try { payload = JSON.parse(text); } catch { throw new Error(`飞书返回非 JSON 内容，HTTP ${response.status}`); }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxAttempts - 1) throw new Error(`飞书服务暂时不可用，HTTP ${response.status}`);
      await sleep(retryDelay(attempt, response.headers.get("retry-after"))); continue;
    }
    if (!response.ok) throw new Error(`飞书 HTTP 错误：${response.status}`);
    if (payload.code !== 0) {
      const rid = response.headers.get("x-request-id") || "unknown";
      throw new Error(`飞书 API 错误：code=${payload.code}, msg=${payload.msg || "unknown"}, request_id=${rid}`);
    }
    return payload;
  }
  throw new Error("请求重试次数耗尽");
}

async function getTenantAccessToken() {
  const p = await apiRequest("/auth/v3/tenant_access_token/internal", { method: "POST", body: { app_id: APP_ID, app_secret: APP_SECRET } });
  if (!p.tenant_access_token) throw new Error("飞书响应中缺少 tenant_access_token");
  return p.tenant_access_token;
}

async function paginate(endpoint, token, query = {}, pageSize = 100) {
  const all = [];
  const seen = new Set();
  let pageToken = "";
  for (let i = 0; i < 10000; i++) {
    const p = await apiRequest(endpoint, { token, query: { ...query, page_size: pageSize, ...(pageToken ? { page_token: pageToken } : {}) } });
    const d = p.data || {};
    all.push(...(Array.isArray(d.items) ? d.items : []));
    if (!d.has_more) return all;
    const next = d.page_token;
    if (!next || seen.has(next)) throw new Error("飞书分页 token 缺失或发生循环");
    seen.add(next); pageToken = next;
  }
  throw new Error("分页超过安全上限 10000 页");
}

async function listTables(token) {
  return paginate(`/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables`, token);
}
async function listViews(token, tableId) {
  return paginate(`/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/views`, token);
}
async function listFields(token, tableId) {
  return paginate(`/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/fields`, token);
}
async function listRecords(token, tableId, viewId, fieldNames) {
  return paginate(`/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/records`, token, {
    view_id: viewId, field_names: JSON.stringify(fieldNames), text_field_as_array: "true"
  }, 500);
}

function exactOne(items, prop, expected, ctx) {
  const matches = items.filter(i => i?.[prop] === expected);
  if (matches.length === 0) throw new Error(`${ctx}不存在：${expected}`);
  if (matches.length > 1) throw new Error(`${ctx}存在重名：${expected}`);
  return matches[0];
}

const FIELD_TYPE_MAP = {
  1: "Text", 2: "Number", 3: "SingleSelect", 4: "MultiSelect", 5: "DateTime",
  7: "Checkbox", 11: "Person", 13: "Phone", 15: "URL", 17: "Attachment",
  18: "SingleLink", 19: "Lookup", 20: "Formula", 21: "DuplexLink",
  22: "Location", 23: "GroupChat", 1001: "CreatedTime", 1002: "ModifiedTime",
  1003: "CreatedBy", 1004: "ModifiedBy", 1005: "AutoNumber"
};

function getFieldTypeLabel(type) { return FIELD_TYPE_MAP[type] || `Unknown(${type})`; }

function isMultiValue(type) { return type === 4 || type === 21; }

function extractOptions(field) {
  if (!field.property?.options) return undefined;
  return field.property.options.map(o => o.name);
}

function transformFieldValue(value, fieldType) {
  if (value === null || value === undefined) return null;

  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    if (value.every(v => typeof v === "object" && v !== null && "text" in v)) {
      const texts = value.map(v => v.text).filter(t => t !== "");
      if (texts.length === 0) return null;
      return texts.length === 1 ? texts[0] : texts;
    }
    if (value.every(v => typeof v === "string")) {
      return value.length === 1 ? value[0] : value;
    }
    return value.map(v => typeof v === "object" && v !== null ? (v.text ?? v.name ?? String(v)) : v);
  }

  if (typeof value === "object" && value !== null) {
    if (fieldType === 21 || fieldType === 18) {
      const result = {};
      if (value.text) result.text = value.text;
      if (Array.isArray(value.text_arr)) result.text_arr = value.text_arr;
      if (Array.isArray(value.record_ids)) result.record_ids = value.record_ids;
      return Object.keys(result).length > 0 ? result : null;
    }
    if (value.text !== undefined) return value.text;
    if (value.name !== undefined) return value.name;
    return String(value);
  }

  return value;
}

function selectRecord(record, allowedFields, config) {
  const inputFields = record?.fields && typeof record.fields === "object" ? record.fields : {};
  const fields = {};
  for (const name of allowedFields) {
    const rawValue = Object.hasOwn(inputFields, name) ? inputFields[name] : null;
    const fieldMeta = allowedFields._meta?.[name];
    const fieldType = fieldMeta?.type;
    fields[name] = transformFieldValue(rawValue, fieldType);
  }
  const output = { fields };
  if (config.include_record_id === true && record.record_id) output.record_id = record.record_id;
  if (config.include_timestamps === true) {
    if (record.created_time !== undefined) output.created_time = record.created_time;
    if (record.last_modified_time !== undefined) output.last_modified_time = record.last_modified_time;
  }
  return output;
}

function assertNoSecrets(serialized, tenantToken) {
  const forbiddenValues = [APP_SECRET, tenantToken].filter(Boolean);
  for (const v of forbiddenValues) {
    if (serialized.includes(v)) throw new Error("检测到实际凭证值即将进入公开输出，已中止部署");
  }
  const patterns = [
    /"app_secret"\s*:\s*"[^"]{10,}"/i,
    /"tenant_access_token"\s*:\s*"[^"]{10,}"/i,
    /"user_access_token"\s*:\s*"[^"]{10,}"/i,
    /"authorization"\s*:\s*"[^"]{10,}"/i,
    /"client_secret"\s*:\s*"[^"]{10,}"/i,
    /\bbearer\s+[a-z0-9_-]{20,}\b/i
  ];
  for (const p of patterns) {
    if (p.test(serialized)) throw new Error(`检测到疑似敏感信息模式：${p.source}`);
  }
}

async function writeJson(relativePath, value, tenantToken) {
  const serialized = `${JSON.stringify(value, null, 2)}\n`;
  assertNoSecrets(serialized, tenantToken);
  const abs = path.join(OUTPUT_DIR, relativePath);
  await fs.mkdir(path.dirname(abs), { recursive: true });
  await fs.writeFile(abs, serialized, "utf8");
  return { bytes: Buffer.byteLength(serialized), sha256: sha256(serialized) };
}

function buildSchemaEntry(tableConfig, selectedFields, tableIdToSlug, generatedAt) {
  const fields = selectedFields.map(f => {
    const entry = {
      field_name: f.field_name,
      field_type: getFieldTypeLabel(f.type),
      ui_type: f.ui_type || null,
      multi_value: isMultiValue(f.type),
      required: false
    };
    const options = extractOptions(f);
    if (options) entry.options = options;
    if (f.type === 21 || f.type === 18) {
      const targetSlug = f.property?.table_id ? tableIdToSlug.get(f.property.table_id) : null;
      const targetName = f.property?.table_id ? tableIdToSlug.get(f.property.table_id + ":name") : null;
      entry.relation = {
        target_table_slug: targetSlug || null,
        target_table_name: targetName || null,
        resolved: !!targetSlug
      };
    }
    return entry;
  });

  return {
    table_name: tableConfig.table_name,
    slug: tableConfig.table_slug,
    primary_field: tableConfig.fields[0] || null,
    source_view: tableConfig.view_name,
    field_count: selectedFields.length,
    fields,
    updated_at: generatedAt
  };
}

function buildIndexHtml(manifest, schema, generatedAt) {
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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Learning English — Public Data Export</title>
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
</style>
</head>
<body>
<h1>Learning English — Public Data Export</h1>
<p class="meta">Last synced: ${escapeHtml(generatedAt)} | Tables: ${manifest.tables.length}</p>
<ul>
  <li><a href="data/manifest.json">manifest.json</a></li>
  <li><a href="data/schema.json">schema.json</a></li>
</ul>
${tablesHtml}
</body>
</html>
`;
}

async function main() {
  const config = await loadConfig();
  await fs.rm(OUTPUT_DIR, { recursive: true, force: true });
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  const generatedAt = new Date().toISOString();
  console.log("开始获取飞书访问凭证……");
  const tenantToken = await getTenantAccessToken();

  console.log("开始读取数据表清单……");
  const allTables = await listTables(tenantToken);

  // Build table_id → slug mapping for relation resolution
  const tableIdToSlug = new Map();
  for (const tc of config.tables) {
    const table = allTables.find(t => t.name === tc.table_name);
    if (table?.table_id) {
      tableIdToSlug.set(table.table_id, tc.table_slug);
      tableIdToSlug.set(table.table_id + ":name", tc.table_name);
    }
  }

  const manifest = {
    schema_version: 2,
    generated_at: generatedAt,
    base: { name: "Learning English" },
    tables: []
  };
  const schemaTables = [];
  const skippedTables = [];

  for (const tc of config.tables) {
    if (tc.enabled === false) {
      console.log(`跳过已禁用的表：${tc.table_name}`);
      skippedTables.push({ name: tc.table_name, reason: "配置中 enabled=false" });
      continue;
    }

    console.log(`同步数据表：${tc.table_name}`);
    const table = exactOne(allTables, "name", tc.table_name, "数据表");
    const tableId = table.table_id;
    if (!tableId) throw new Error(`数据表缺少 table_id：${tc.table_name}`);

    const [views, fields] = await Promise.all([listViews(tenantToken, tableId), listFields(tenantToken, tableId)]);

    const view = exactOne(views, "view_name", tc.view_name, `${tc.table_name} 的视图`);
    const viewId = view.view_id;
    if (!viewId) throw new Error(`视图缺少 view_id：${tc.view_name}`);

    const fieldByName = new Map();
    for (const f of fields) {
      if (!f.field_name) continue;
      if (fieldByName.has(f.field_name)) throw new Error(`${tc.table_name} 存在重名字段：${f.field_name}`);
      fieldByName.set(f.field_name, f);
    }
    for (const fn of tc.fields) {
      if (!fieldByName.has(fn)) throw new Error(`${tc.table_name} 缺少配置字段：${fn}`);
    }

    const selectedFieldsMeta = tc.fields.map(name => {
      const f = fieldByName.get(name);
      return { field_name: name, field_id: f.field_id, type: f.type, ui_type: f.ui_type, property: f.property };
    });

    // Build field metadata map for record transformation
    const fieldsWithMeta = tc.fields;
    fieldsWithMeta._meta = {};
    for (const name of tc.fields) {
      const f = fieldByName.get(name);
      fieldsWithMeta._meta[name] = { type: f.type, ui_type: f.ui_type };
    }

    const rawRecords = await listRecords(tenantToken, tableId, viewId, tc.fields);
    const records = rawRecords.map(r => selectRecord(r, fieldsWithMeta, config));
    records.sort((a, b) => {
      const aid = a.record_id || "";
      const bid = b.record_id || "";
      return aid.localeCompare(bid);
    });

    const basePath = `data/${tc.table_slug}`;
    const fieldsWrite = await writeJson(`${basePath}/fields.json`, {
      schema_version: 1,
      table_name: tc.table_name,
      view_name: tc.view_name,
      fields: selectedFieldsMeta.map(f => ({
        field_name: f.field_name,
        field_id: f.field_id,
        type: f.type,
        ui_type: f.ui_type
      }))
    }, tenantToken);

    const recordFiles = [];
    let totalBytes = fieldsWrite.bytes;

    for (let offset = 0; offset < records.length; offset += config.chunk_size) {
      const chunkNum = Math.floor(offset / config.chunk_size) + 1;
      const filename = `records-${String(chunkNum).padStart(4, "0")}.json`;
      const chunkRecords = records.slice(offset, offset + config.chunk_size);
      const relPath = `${basePath}/${filename}`;
      const result = await writeJson(relPath, {
        schema_version: 1,
        table_name: tc.table_name,
        view_name: tc.view_name,
        chunk: chunkNum,
        records: chunkRecords
      }, tenantToken);
      totalBytes += result.bytes;
      recordFiles.push({ path: relPath, record_count: chunkRecords.length, bytes: result.bytes, sha256: result.sha256 });
    }

    if (records.length === 0) {
      const relPath = `${basePath}/records-0001.json`;
      const result = await writeJson(relPath, {
        schema_version: 1, table_name: tc.table_name, view_name: tc.view_name, chunk: 1, records: []
      }, tenantToken);
      totalBytes += result.bytes;
      recordFiles.push({ path: relPath, record_count: 0, bytes: result.bytes, sha256: result.sha256 });
    }

    if (totalBytes > config.max_table_bytes) {
      throw new Error(`${tc.table_name} 输出 ${totalBytes} 字节超过上限 ${config.max_table_bytes}`);
    }

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
    console.log(`  完成：${records.length} 条记录，${recordFiles.length} 个分片`);
  }

  // Sort manifest tables by slug for stable diff
  manifest.tables.sort((a, b) => a.slug.localeCompare(b.slug));

  const manifestWrite = await writeJson("data/manifest.json", manifest, tenantToken);
  console.log(`manifest.json: ${manifestWrite.bytes} bytes`);

  const schema = {
    schema_version: 1,
    generated_at: generatedAt,
    base: { name: "Learning English" },
    tables: schemaTables.sort((a, b) => a.slug.localeCompare(b.slug))
  };
  const schemaWrite = await writeJson("data/schema.json", schema, tenantToken);
  console.log(`schema.json: ${schemaWrite.bytes} bytes`);

  const indexHtml = buildIndexHtml(manifest, schema, generatedAt);
  const indexPath = path.join(OUTPUT_DIR, "index.html");
  assertNoSecrets(indexHtml, tenantToken);
  await fs.writeFile(indexPath, indexHtml, "utf8");
  console.log(`index.html written`);

  if (skippedTables.length > 0) {
    console.log("\n跳过的表：");
    for (const t of skippedTables) console.log(`  - ${t.name}: ${t.reason}`);
  }

  console.log(`\n同步完成：${manifest.tables.length} 张表已公开导出。`);
}

main().catch(e => { console.error(`同步失败：${e.message}`); process.exitCode = 1; });
