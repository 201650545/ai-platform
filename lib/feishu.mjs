// lib/feishu.mjs — Feishu API client shared across all projects.
// Handles authentication, pagination, retries, and all Bitable read operations.

const API_ROOT = "https://open.feishu.cn/open-apis";

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function encodeSegment(v) { return encodeURIComponent(String(v)); }

function retryDelay(attempt, retryAfterHeader) {
  const ra = Number(retryAfterHeader);
  if (Number.isFinite(ra) && ra > 0) return Math.min(ra * 1000, 60000);
  return Math.min(1000 * 2 ** attempt, 30000) + Math.floor(Math.random() * 500);
}

/**
 * Low-level API request with retry logic.
 * Never logs token, secret, or authorization values.
 */
export async function apiRequest(endpoint, { method = "GET", token, query = {}, body, maxAttempts = 5 } = {}) {
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

/**
 * Obtain tenant_access_token using app credentials.
 * The token is returned but must never be logged or written to output.
 */
export async function getTenantAccessToken(appId, appSecret) {
  if (!appId || !appSecret) throw new Error("缺少飞书应用凭据 (app_id / app_secret)");
  const p = await apiRequest("/auth/v3/tenant_access_token/internal", {
    method: "POST",
    body: { app_id: appId, app_secret: appSecret }
  });
  if (!p.tenant_access_token) throw new Error("飞书响应中缺少 tenant_access_token");
  return p.tenant_access_token;
}

/**
 * Paginated fetch helper — follows page_token until has_more is false.
 * Safety limit of 10000 pages prevents infinite loops.
 */
export async function paginate(endpoint, token, query = {}, pageSize = 100) {
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

/** List all tables in a Base (app_token). */
export async function listTables(token, appToken) {
  return paginate(`/bitable/v1/apps/${encodeSegment(appToken)}/tables`, token);
}

/** List all views in a table. */
export async function listViews(token, appToken, tableId) {
  return paginate(`/bitable/v1/apps/${encodeSegment(appToken)}/tables/${encodeSegment(tableId)}/views`, token);
}

/** List all fields in a table. */
export async function listFields(token, appToken, tableId) {
  return paginate(`/bitable/v1/apps/${encodeSegment(appToken)}/tables/${encodeSegment(tableId)}/fields`, token);
}

/** List all records in a table view, filtered to specific field names. */
export async function listRecords(token, appToken, tableId, viewId, fieldNames) {
  return paginate(`/bitable/v1/apps/${encodeSegment(appToken)}/tables/${encodeSegment(tableId)}/records`, token, {
    view_id: viewId,
    field_names: JSON.stringify(fieldNames),
    text_field_as_array: "true"
  }, 500);
}

/** Find exactly one item matching a property value, or throw. */
export function exactOne(items, prop, expected, ctx) {
  const matches = items.filter(i => i?.[prop] === expected);
  if (matches.length === 0) throw new Error(`${ctx}不存在：${expected}`);
  if (matches.length > 1) throw new Error(`${ctx}存在重名：${expected}`);
  return matches[0];
}
