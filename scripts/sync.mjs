import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const API_ROOT = "https://open.feishu.cn/open-apis";
const OUTPUT_DIR = path.resolve("site");
const CONFIG_PATH = path.resolve("config/export.json");

const APP_ID = process.env.FEISHU_APP_ID;
const APP_SECRET = process.env.FEISHU_APP_SECRET;
const BASE_TOKEN = process.env.FEISHU_BASE_TOKEN;

const REQUIRED_ENV = {
  FEISHU_APP_ID: APP_ID,
  FEISHU_APP_SECRET: APP_SECRET,
  FEISHU_BASE_TOKEN: BASE_TOKEN
};

for (const [name, value] of Object.entries(REQUIRED_ENV)) {
  if (!value || !String(value).trim()) {
    throw new Error(`缺少必需环境变量：${name}`);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function encodeSegment(value) {
  return encodeURIComponent(String(value));
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function assertSafeSlug(slug) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
    throw new Error(`slug 非法：${slug}。仅允许小写字母、数字和单连字符分隔。`);
  }
}

async function loadConfig() {
  const raw = await fs.readFile(CONFIG_PATH, "utf8");
  const config = JSON.parse(raw);

  if (config.schema_version !== 1) {
    throw new Error("config/export.json 的 schema_version 必须为 1");
  }

  if (!Number.isInteger(config.chunk_size) || config.chunk_size < 1 || config.chunk_size > 500) {
    throw new Error("chunk_size 必须是 1～500 的整数");
  }

  if (!Number.isInteger(config.max_table_bytes) || config.max_table_bytes < 1024) {
    throw new Error("max_table_bytes 必须是大于 1024 的整数");
  }

  if (!Array.isArray(config.tables) || config.tables.length === 0) {
    throw new Error("config/export.json 至少需要配置一张表");
  }

  const seenSlugs = new Set();
  for (const item of config.tables) {
    if (!item.table_name || !item.view_name || !item.slug) {
      throw new Error("每个 tables 项都必须包含 table_name、view_name、slug");
    }
    assertSafeSlug(item.slug);
    if (seenSlugs.has(item.slug)) {
      throw new Error(`slug 重复：${item.slug}`);
    }
    seenSlugs.add(item.slug);

    if (!Array.isArray(item.fields) || item.fields.length === 0) {
      throw new Error(`${item.table_name} 的 fields 不能为空`);
    }
    if (item.fields.includes("*")) {
      throw new Error(`${item.table_name} 禁止使用通配字段 *`);
    }
    const forbiddenFieldNames = new Set([
      "app_secret",
      "tenant_access_token",
      "authorization"
    ]);
    for (const fieldName of item.fields) {
      if (forbiddenFieldNames.has(String(fieldName).trim().toLowerCase())) {
        throw new Error(`${item.table_name} 禁止公开敏感字段名：${fieldName}`);
      }
    }
    if (new Set(item.fields).size !== item.fields.length) {
      throw new Error(`${item.table_name} 的 fields 存在重复项`);
    }
  }

  return config;
}

function retryDelay(attempt, retryAfterHeader) {
  const retryAfter = Number(retryAfterHeader);
  if (Number.isFinite(retryAfter) && retryAfter > 0) {
    return Math.min(retryAfter * 1000, 60000);
  }
  const base = Math.min(1000 * 2 ** attempt, 30000);
  return base + Math.floor(Math.random() * 500);
}

async function apiRequest(endpoint, {
  method = "GET",
  token,
  query = {},
  body,
  maxAttempts = 5
} = {}) {
  const url = new URL(`${API_ROOT}${endpoint}`);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let response;
    try {
      response = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(30000)
      });
    } catch (error) {
      if (attempt === maxAttempts - 1) {
        throw new Error(`网络请求失败：${error.message}`);
      }
      await sleep(retryDelay(attempt));
      continue;
    }

    const text = await response.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error(`飞书返回非 JSON 内容，HTTP ${response.status}`);
    }

    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxAttempts - 1) {
        throw new Error(`飞书服务暂时不可用，HTTP ${response.status}`);
      }
      await sleep(retryDelay(attempt, response.headers.get("retry-after")));
      continue;
    }

    if (!response.ok) {
      throw new Error(`飞书 HTTP 错误：${response.status}`);
    }

    if (payload.code !== 0) {
      const requestId = response.headers.get("x-request-id") || "unknown";
      throw new Error(
        `飞书 API 错误：code=${payload.code}, msg=${payload.msg || "unknown"}, request_id=${requestId}`
      );
    }

    return payload;
  }

  throw new Error("请求重试次数耗尽");
}

async function getTenantAccessToken() {
  const payload = await apiRequest("/auth/v3/tenant_access_token/internal", {
    method: "POST",
    body: {
      app_id: APP_ID,
      app_secret: APP_SECRET
    }
  });

  if (!payload.tenant_access_token) {
    throw new Error("飞书响应中缺少 tenant_access_token");
  }

  return payload.tenant_access_token;
}

async function paginate({ endpoint, token, query = {}, pageSize }) {
  const all = [];
  const seenTokens = new Set();
  let pageToken = "";

  for (let page = 0; page < 10000; page += 1) {
    const payload = await apiRequest(endpoint, {
      token,
      query: {
        ...query,
        page_size: pageSize,
        ...(pageToken ? { page_token: pageToken } : {})
      }
    });

    const data = payload.data || {};
    all.push(...(Array.isArray(data.items) ? data.items : []));

    if (!data.has_more) {
      return all;
    }

    const nextToken = data.page_token;
    if (!nextToken || seenTokens.has(nextToken)) {
      throw new Error("飞书分页 token 缺失或发生循环");
    }
    seenTokens.add(nextToken);
    pageToken = nextToken;
  }

  throw new Error("分页超过安全上限 10000 页");
}

async function listTables(token) {
  return paginate({
    endpoint: `/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables`,
    token,
    pageSize: 100
  });
}

async function listViews(token, tableId) {
  return paginate({
    endpoint: `/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/views`,
    token,
    pageSize: 100
  });
}

async function listFields(token, tableId) {
  return paginate({
    endpoint: `/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/fields`,
    token,
    pageSize: 100
  });
}

async function listRecords(token, tableId, viewId, fieldNames) {
  return paginate({
    endpoint: `/bitable/v1/apps/${encodeSegment(BASE_TOKEN)}/tables/${encodeSegment(tableId)}/records`,
    token,
    pageSize: 500,
    query: {
      view_id: viewId,
      field_names: JSON.stringify(fieldNames),
      text_field_as_array: "true"
    }
  });
}

function exactOne(items, property, expected, context) {
  const matches = items.filter((item) => item?.[property] === expected);
  if (matches.length === 0) {
    throw new Error(`${context}不存在：${expected}`);
  }
  if (matches.length > 1) {
    throw new Error(`${context}存在重名，无法安全选择：${expected}`);
  }
  return matches[0];
}

function selectRecord(record, allowedFields, config) {
  const inputFields = record?.fields && typeof record.fields === "object"
    ? record.fields
    : {};

  const fields = {};
  for (const name of allowedFields) {
    fields[name] = Object.hasOwn(inputFields, name) ? inputFields[name] : null;
  }

  const output = { fields };

  if (config.include_record_id === true && record.record_id) {
    output.record_id = record.record_id;
  }

  if (config.include_timestamps === true) {
    if (record.created_time !== undefined) output.created_time = record.created_time;
    if (record.last_modified_time !== undefined) {
      output.last_modified_time = record.last_modified_time;
    }
  }

  return output;
}

function assertNoSecrets(serialized, tenantToken) {
  const forbiddenValues = [APP_SECRET, tenantToken].filter(Boolean);
  for (const value of forbiddenValues) {
    if (serialized.includes(value)) {
      throw new Error("检测到实际凭证值即将进入公开输出，已中止部署");
    }
  }
}

async function writeJson(relativePath, value, tenantToken) {
  const serialized = `${JSON.stringify(value, null, 2)}\n`;
  assertNoSecrets(serialized, tenantToken);
  const absolutePath = path.join(OUTPUT_DIR, relativePath);
  await fs.mkdir(path.dirname(absolutePath), { recursive: true });
  await fs.writeFile(absolutePath, serialized, "utf8");
  return {
    bytes: Buffer.byteLength(serialized),
    sha256: sha256(serialized)
  };
}

async function main() {
  const config = await loadConfig();
  await fs.rm(OUTPUT_DIR, { recursive: true, force: true });
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  console.log("开始获取飞书访问凭证……");
  const tenantToken = await getTenantAccessToken();

  console.log("开始读取数据表清单……");
  const allTables = await listTables(tenantToken);

  const manifest = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    source: "Feishu Bitable",
    tables: []
  };

  for (const tableConfig of config.tables) {
    console.log(`同步数据表：${tableConfig.table_name}`);

    const table = exactOne(
      allTables,
      "name",
      tableConfig.table_name,
      "数据表"
    );

    const tableId = table.table_id;
    if (!tableId) {
      throw new Error(`数据表缺少 table_id：${tableConfig.table_name}`);
    }

    const [views, fields] = await Promise.all([
      listViews(tenantToken, tableId),
      listFields(tenantToken, tableId)
    ]);

    const view = exactOne(
      views,
      "view_name",
      tableConfig.view_name,
      `${tableConfig.table_name} 的视图`
    );

    const viewId = view.view_id;
    if (!viewId) {
      throw new Error(`视图缺少 view_id：${tableConfig.view_name}`);
    }

    const fieldByName = new Map();
    for (const field of fields) {
      const name = field.field_name;
      if (!name) continue;
      if (fieldByName.has(name)) {
        throw new Error(`${tableConfig.table_name} 存在重名字段：${name}`);
      }
      fieldByName.set(name, field);
    }

    for (const fieldName of tableConfig.fields) {
      if (!fieldByName.has(fieldName)) {
        throw new Error(`${tableConfig.table_name} 缺少配置字段：${fieldName}`);
      }
    }

    const selectedFieldMetadata = tableConfig.fields.map((name) => {
      const field = fieldByName.get(name);
      return {
        field_name: name,
        field_id: field.field_id,
        type: field.type,
        ui_type: field.ui_type
      };
    });

    const rawRecords = await listRecords(
      tenantToken,
      tableId,
      viewId,
      tableConfig.fields
    );

    const records = rawRecords.map((record) =>
      selectRecord(record, tableConfig.fields, config)
    );

    const basePath = `data/${tableConfig.slug}`;
    const fieldsWrite = await writeJson(
      `${basePath}/fields.json`,
      {
        schema_version: 1,
        table_name: tableConfig.table_name,
        view_name: tableConfig.view_name,
        fields: selectedFieldMetadata
      },
      tenantToken
    );

    const chunks = [];
    let totalBytes = fieldsWrite.bytes;

    for (let offset = 0; offset < records.length; offset += config.chunk_size) {
      const chunkNumber = Math.floor(offset / config.chunk_size) + 1;
      const filename = `records-${String(chunkNumber).padStart(4, "0")}.json`;
      const chunkRecords = records.slice(offset, offset + config.chunk_size);
      const relativePath = `${basePath}/${filename}`;

      const result = await writeJson(
        relativePath,
        {
          schema_version: 1,
          table_name: tableConfig.table_name,
          view_name: tableConfig.view_name,
          chunk: chunkNumber,
          records: chunkRecords
        },
        tenantToken
      );

      totalBytes += result.bytes;
      chunks.push({
        path: `./${tableConfig.slug}/${filename}`,
        file: filename,
        record_count: chunkRecords.length,
        bytes: result.bytes,
        sha256: result.sha256
      });
    }

    if (records.length === 0) {
      const relativePath = `${basePath}/records-0001.json`;
      const result = await writeJson(
        relativePath,
        {
          schema_version: 1,
          table_name: tableConfig.table_name,
          view_name: tableConfig.view_name,
          chunk: 1,
          records: []
        },
        tenantToken
      );
      totalBytes += result.bytes;
      chunks.push({
        path: `./${tableConfig.slug}/records-0001.json`,
        file: "records-0001.json",
        record_count: 0,
        bytes: result.bytes,
        sha256: result.sha256
      });
    }

    if (totalBytes > config.max_table_bytes) {
      throw new Error(
        `${tableConfig.table_name} 输出 ${totalBytes} 字节，超过 max_table_bytes=${config.max_table_bytes}`
      );
    }

    manifest.tables.push({
      name: tableConfig.table_name,
      view: tableConfig.view_name,
      slug: tableConfig.slug,
      field_count: selectedFieldMetadata.length,
      record_count: records.length,
      fields_path: `./${tableConfig.slug}/fields.json`,
      chunks
    });
  }

  await writeJson("data/manifest.json", manifest, tenantToken);

  const rows = manifest.tables.map((table) => `
    <tr>
      <td>${escapeHtml(table.name)}</td>
      <td>${escapeHtml(table.view)}</td>
      <td>${table.field_count}</td>
      <td>${table.record_count}</td>
      <td><a href="./data/${escapeHtml(table.slug)}/fields.json">字段</a></td>
      <td><a href="./data/${escapeHtml(table.slug)}/${escapeHtml(table.chunks[0].file)}">首个数据分片</a></td>
    </tr>`).join("");

  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Feishu Base Public Export</title>
</head>
<body>
  <main>
    <h1>Feishu Base Public Export</h1>
    <p>Generated at: ${escapeHtml(manifest.generated_at)}</p>
    <p><a href="./data/manifest.json">Open manifest.json</a></p>
    <table border="1" cellpadding="8" cellspacing="0">
      <thead>
        <tr>
          <th>数据表</th><th>视图</th><th>字段数</th><th>记录数</th><th>字段</th><th>数据</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </main>
</body>
</html>\n`;

  assertNoSecrets(html, tenantToken);
  await fs.writeFile(path.join(OUTPUT_DIR, "index.html"), html, "utf8");
  await fs.writeFile(path.join(OUTPUT_DIR, ".nojekyll"), "", "utf8");
  await fs.writeFile(
    path.join(OUTPUT_DIR, "robots.txt"),
    "User-agent: *\nDisallow: /\n",
    "utf8"
  );

  console.log(`同步完成：${manifest.tables.length} 张表。`);
}

main().catch((error) => {
  console.error(`同步失败：${error.message}`);
  process.exitCode = 1;
});
