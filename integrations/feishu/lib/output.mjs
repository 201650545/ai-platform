// lib/output.mjs — Output file management and HTML generation.
// Handles writing JSON with checksums, building HTML pages, and path management.

import fs from "node:fs/promises";
import path from "node:path";
import { sha256, assertNoSecrets } from "./security.mjs";
import { escapeHtml } from "./transform.mjs";

/**
 * Write a JSON value to a file with security scanning.
 * Returns { bytes, sha256 } for manifest tracking.
 */
export async function writeJson(outputDir, relativePath, value, secretValues = []) {
  const serialized = `${JSON.stringify(value, null, 2)}\n`;
  assertNoSecrets(serialized, secretValues, relativePath);
  const abs = path.join(outputDir, relativePath);
  await fs.mkdir(path.dirname(abs), { recursive: true });
  await fs.writeFile(abs, serialized, "utf8");
  return { bytes: Buffer.byteLength(serialized), sha256: sha256(serialized) };
}

/**
 * Write a text file with security scanning.
 */
export async function writeText(outputDir, relativePath, text, secretValues = []) {
  assertNoSecrets(text, secretValues, relativePath);
  const abs = path.join(outputDir, relativePath);
  await fs.mkdir(path.dirname(abs), { recursive: true });
  await fs.writeFile(abs, text, "utf8");
  return { bytes: Buffer.byteLength(text), sha256: sha256(text) };
}

/**
 * Copy a file from source to destination (for legacy path mirroring).
 */
export async function copyFile(srcPath, destPath) {
  await fs.mkdir(path.dirname(destPath), { recursive: true });
  await fs.copyFile(srcPath, destPath);
}

/**
 * Recursively walk a directory and return all file paths.
 */
export async function walkDir(directory) {
  const output = [];
  const entries = await fs.readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      output.push(...await walkDir(fullPath));
    } else if (entry.isFile()) {
      output.push(fullPath);
    }
  }
  return output;
}

/**
 * Generate a build_id from timestamp and short git SHA.
 */
export function generateBuildId(gitSha = "local") {
  const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const shortSha = gitSha.slice(0, 8);
  return `${ts}-${shortSha}`;
}

/**
 * Build the project-level index.html page.
 */
export function buildProjectIndexHtml(projectConfig, manifest, schema, buildId) {
  const projectName = escapeHtml(projectConfig.project.title);
  const projectSlug = escapeHtml(projectConfig.project.slug);
  const generatedAt = manifest.generated_at || new Date().toISOString();

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
<title>${projectName} — Public Data Export</title>
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
<h1>${projectName}</h1>
<p class="meta">Slug: <code>${projectSlug}</code> | Build: <code>${escapeHtml(buildId)}</code> | Last synced: ${escapeHtml(generatedAt)} | Tables: ${manifest.tables.length}</p>
<div class="nav">
  <a href="../index.html">← Data Hub</a>
  <a href="manifest.json?v=${escapeHtml(buildId)}">manifest.json</a>
  <a href="schema.json?v=${escapeHtml(buildId)}">schema.json</a>
  <a href="semantic.json?v=${escapeHtml(buildId)}">semantic.json</a>
  <a href="summary.md">summary.md</a>
  <a href="agent-guide.md">agent-guide.md</a>
  <a href="status.json?v=${escapeHtml(buildId)}">status.json</a>
</div>
${tablesHtml}
</body>
</html>
`;
}

/**
 * Build the Data Hub homepage (catalog-level index.html).
 * Displays project info with semantic metadata, filtering support, and no-JS fallback.
 */
export function buildHubHomepage(catalog, buildId) {
  const projectsHtml = catalog.projects.map(p => {
    const statusClass = p.sync_status === "ok" ? "ok" : (p.is_stale ? "stale" : "fail");
    const domains = (p.domains || []).join(", ") || "—";
    const capabilities = (p.capabilities || []).join(", ") || "—";
    const tags = (p.tags || []).join(", ") || "—";
    const staleBadge = p.is_stale ? ' <span class="badge stale">stale</span>' : "";
    return `  <section class="project ${statusClass}" data-domain="${(p.domains || []).join(" ")}" data-capability="${(p.capabilities || []).join(" ")}" data-status="${p.sync_status}" data-tags="${(p.tags || []).join(" ")}">
    <h2><a href="${p.homepage}">${escapeHtml(p.title)}</a>${staleBadge}</h2>
    <p class="meta">Slug: <code>${escapeHtml(p.slug)}</code> | Group: ${escapeHtml(p.group || "—")} | Status: ${escapeHtml(p.sync_status)} ${p.is_stale ? "(stale)" : ""}</p>
    <p>${escapeHtml(p.description || "")}</p>
    <p class="meta">Domains: ${escapeHtml(domains)} | Capabilities: ${escapeHtml(capabilities)} | Tags: ${escapeHtml(tags)}</p>
    <p class="meta">Tables: ${p.table_count} | Records: ${p.total_records} | Last sync: ${escapeHtml(p.last_success_at || "—")}</p>
    <ul>
      <li><a href="${p.manifest}?v=${escapeHtml(buildId)}">manifest.json</a></li>
      <li><a href="${p.schema}?v=${escapeHtml(buildId)}">schema.json</a></li>
      <li><a href="${p.semantic || p.summary}?v=${escapeHtml(buildId)}">semantic.json</a></li>
      <li><a href="${p.summary}">summary.md</a></li>
      <li><a href="${p.agent_guide || p.summary}">agent-guide.md</a></li>
      <li><a href="${p.homepage}">project index</a></li>
    </ul>
  </section>`;
  }).join("\n");

  // Build capability index for top-level display
  const capIndex = catalog.capabilities || {};
  const capIndexHtml = Object.entries(capIndex).map(([cap, slugs]) =>
    `  <span class="cap-pill" data-capability="${cap}">${escapeHtml(cap)} (${slugs.length})</span>`
  ).join("\n");

  return `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feishu Data Hub</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#333}
h1{border-bottom:2px solid #e0e0e0;padding-bottom:.5rem}
h2{margin-top:2rem;color:#1a73e8}
code{background:#f5f5f5;padding:.1em .3em;border-radius:3px;font-size:.9em}
section{border:1px solid #e0e0e0;border-radius:8px;padding:1rem 1.5rem;margin:1rem 0}
section.ok{border-left:4px solid #4caf50}
section.stale{border-left:4px solid #ff9800}
section.fail{border-left:4px solid #f44336}
li{margin:.2rem 0}
a{color:#1a73e8;text-decoration:none}
a:hover{text-decoration:underline}
.meta{color:#666;font-size:.9rem}
.badge{display:inline-block;padding:.1em .5em;border-radius:3px;font-size:.8em;font-weight:bold}
.badge.stale{background:#ff9800;color:#fff}
.cap-index{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}
.cap-pill{display:inline-block;background:#e8f0fe;color:#1a73e8;padding:.2em .8em;border-radius:12px;font-size:.85rem;cursor:pointer}
.cap-pill:hover{background:#d0e0fc}
.filter-bar{margin:1rem 0;padding:.5rem;background:#f9f9f9;border-radius:4px}
.filter-bar input,.filter-bar select{padding:.3em .5em;margin-right:.5rem;border:1px solid #ddd;border-radius:3px}
.filter-bar button{padding:.3em .8em;background:#1a73e8;color:#fff;border:none;border-radius:3px;cursor:pointer}
.filter-bar button:hover{background:#1557b0}
noscript{display:block;padding:.5rem;background:#fff3cd;border-radius:4px;margin:.5rem 0}
</style>
</head>
<body>
<h1>Feishu Data Hub</h1>
<p class="meta">${escapeHtml(catalog.hub?.description || "统一公开导出的飞书多维表格数据中心")} | Build: <code>${escapeHtml(buildId)}</code> | Generated: ${escapeHtml(catalog.generated_at)} | Projects: ${catalog.projects.length}</p>
<ul>
  <li><a href="catalog.json?v=${escapeHtml(buildId)}">catalog.json</a></li>
  <li><a href="routing.json?v=${escapeHtml(buildId)}">routing.json</a></li>
  <li><a href="AI-README.md">AI-README.md</a></li>
  <li><a href="catalog-versioned/${escapeHtml(buildId)}.json">versioned catalog</a></li>
</ul>
<div class="cap-index">
${capIndexHtml}
</div>
<noscript>JavaScript 未启用 — 以下项目列表可直接点击访问。使用筛选功能需要启用 JavaScript。</noscript>
<div class="filter-bar">
  <input type="text" id="filter-keyword" placeholder="关键词筛选..." oninput="filterProjects()">
  <select id="filter-domain" onchange="filterProjects()">
    <option value="">所有领域</option>
    ${[...new Set(catalog.projects.flatMap(p => p.domains || []))].sort().map(d => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join("")}
  </select>
  <select id="filter-capability" onchange="filterProjects()">
    <option value="">所有能力</option>
    ${Object.keys(capIndex).sort().map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("")}
  </select>
  <select id="filter-status" onchange="filterProjects()">
    <option value="">所有状态</option>
    <option value="ok">正常</option>
    <option value="stale">过期</option>
    <option value="failed">失败</option>
  </select>
</div>
${projectsHtml}
<script>
function filterProjects() {
  const kw = document.getElementById('filter-keyword').value.toLowerCase();
  const domain = document.getElementById('filter-domain').value;
  const capability = document.getElementById('filter-capability').value;
  const status = document.getElementById('filter-status').value;
  const sections = document.querySelectorAll('section.project');
  sections.forEach(s => {
    const text = s.textContent.toLowerCase();
    const sDomain = s.dataset.domain || '';
    const sCap = s.dataset.capability || '';
    const sStatus = s.dataset.status || '';
    const sTags = s.dataset.tags || '';
    const matchKw = !kw || text.includes(kw);
    const matchDomain = !domain || sDomain.split(' ').includes(domain);
    const matchCap = !capability || sCap.split(' ').includes(capability);
    const matchStatus = !status || sStatus === status;
    s.style.display = (matchKw && matchDomain && matchCap && matchStatus) ? '' : 'none';
  });
}
</script>
</body>
</html>
`;
}
