// lib/config.mjs — Configuration parsing and validation for the Data Hub.
// Reads hub.yaml, credential-profiles.yaml, and all project YAMLs.

import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";

const REPO_ROOT = path.resolve(".");
const CONFIG_DIR = path.join(REPO_ROOT, "config");
const PROJECTS_DIR = path.join(CONFIG_DIR, "projects");

/** Safe slug pattern: lowercase letters, digits, single hyphens between segments. */
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Field names that must never be exported. */
const FORBIDDEN_FIELD_NAMES = new Set([
  "app_secret", "tenant_access_token", "user_access_token",
  "authorization", "client_secret", "github_token", "cookie"
]);

/** Assert a value is a safe slug. */
export function assertSafeSlug(slug, ctx = "slug") {
  if (!SLUG_RE.test(slug)) throw new Error(`${ctx} 非法：${slug}（只允许小写字母、数字和连字符）`);
}

/** Read and parse a YAML file. */
async function readYaml(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return yaml.load(text);
}

/** Read and parse a JSON file. */
async function readJson(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return JSON.parse(text);
}

/**
 * Load hub-level configuration from config/hub.yaml.
 */
export async function loadHubConfig() {
  const hubPath = path.join(CONFIG_DIR, "hub.yaml");
  const hub = await readYaml(hubPath);
  if (!hub.hub_version) throw new Error("hub.yaml 缺少 hub_version");
  if (!hub.hub?.title) throw new Error("hub.yaml 缺少 hub.title");
  if (!hub.output?.root_dir) throw new Error("hub.yaml 缺少 output.root_dir");
  return hub;
}

/**
 * Load credential profiles from config/credential-profiles.yaml.
 */
export async function loadCredentialProfiles() {
  const credPath = path.join(CONFIG_DIR, "credential-profiles.yaml");
  const profiles = await readYaml(credPath);
  if (!profiles.profiles) throw new Error("credential-profiles.yaml 缺少 profiles");
  return profiles;
}

/**
 * Resolve credentials for a given profile from environment variables.
 * Tries primary secrets first, falls back to legacy secrets.
 * Returns { appId, appSecret, appToken } or null if not available.
 */
export function resolveCredentials(profileConfig, env, baseKey) {
  if (!profileConfig) return null;

  const appId = env[profileConfig.app_id_secret] || env[profileConfig.fallback_app_id_secret];
  const appSecret = env[profileConfig.app_secret_secret] || env[profileConfig.fallback_app_secret_secret];

  // Try registry first, then fallback to single token
  let appToken = null;
  const registryJson = env[profileConfig.base_registry_secret];
  if (registryJson) {
    try {
      const registry = JSON.parse(registryJson);
      appToken = registry[baseKey]?.app_token;
    } catch {
      // Registry parse failed — fall through to fallback
    }
  }
  if (!appToken) {
    appToken = env[profileConfig.fallback_base_token_secret];
  }

  if (!appId || !appSecret || !appToken) return null;
  return { appId, appSecret, appToken };
}

/**
 * Load a single project configuration from config/projects/<slug>.yaml.
 * Validates structure and field allowlists.
 */
export async function loadProjectConfig(slug) {
  assertSafeSlug(slug, "项目 slug");
  const projectPath = path.join(PROJECTS_DIR, `${slug}.yaml`);
  const config = await readYaml(projectPath);

  if (!config.config_version) throw new Error(`${slug}: 缺少 config_version`);
  if (!config.project?.slug) throw new Error(`${slug}: 缺少 project.slug`);
  if (config.project.slug !== slug) throw new Error(`${slug}: project.slug (${config.project.slug}) 与文件名不一致`);
  assertSafeSlug(config.project.slug, "项目 slug");
  if (!config.project.title) throw new Error(`${slug}: 缺少 project.title`);
  if (!config.project.enabled) throw new Error(`${slug}: project.enabled 必须为 true`);
  if (!config.source?.base_key) throw new Error(`${slug}: 缺少 source.base_key`);
  if (!config.source?.credential_profile) throw new Error(`${slug}: 缺少 source.credential_profile`);
  if (!config.source?.export_view_name) throw new Error(`${slug}: 缺少 source.export_view_name`);

  // Validate tables if explicitly listed
  if (Array.isArray(config.tables)) {
    const seenSlugs = new Set();
    for (const tc of config.tables) {
      if (!tc.table_name || !tc.table_slug || !tc.view_name) {
        throw new Error(`${slug}: 每个表必须包含 table_name、table_slug、view_name`);
      }
      assertSafeSlug(tc.table_slug, `${slug} 的表 slug`);
      if (seenSlugs.has(tc.table_slug)) throw new Error(`${slug}: 表 slug 重复：${tc.table_slug}`);
      seenSlugs.add(tc.table_slug);

      if (Array.isArray(tc.fields)) {
        if (tc.fields.length === 0) throw new Error(`${slug}/${tc.table_name}: fields 不能为空`);
        if (tc.fields.includes("*")) throw new Error(`${slug}/${tc.table_name}: 禁止使用通配字段 *`);
        for (const fn of tc.fields) {
          if (FORBIDDEN_FIELD_NAMES.has(String(fn).trim().toLowerCase())) {
            throw new Error(`${slug}/${tc.table_name}: 禁止公开敏感字段名：${fn}`);
          }
        }
        if (new Set(tc.fields).size !== tc.fields.length) {
          throw new Error(`${slug}/${tc.table_name}: fields 存在重复项`);
        }
      }
    }
  }

  return config;
}

/**
 * Discover all project YAMLs in config/projects/.
 * Returns array of slugs sorted alphabetically.
 */
export async function discoverProjects() {
  const entries = await fs.readdir(PROJECTS_DIR, { withFileTypes: true });
  const slugs = [];
  for (const entry of entries) {
    if (entry.isFile() && entry.name.endsWith(".yaml")) {
      const slug = entry.name.slice(0, -5);
      if (SLUG_RE.test(slug)) slugs.push(slug);
    }
  }
  return slugs.sort();
}

/**
 * Load all enabled projects, returning { slug, config } pairs.
 * Projects with enabled=false are skipped.
 */
export async function loadAllProjects() {
  const slugs = await discoverProjects();
  const projects = [];
  for (const slug of slugs) {
    const config = await loadProjectConfig(slug);
    if (config.project.enabled !== false) {
      projects.push({ slug, config });
    }
  }
  return projects;
}

/**
 * Load the legacy export.json for backward compatibility.
 * Used during migration to ensure old URLs keep working.
 */
export async function loadLegacyExportConfig() {
  const exportPath = path.join(CONFIG_DIR, "export.json");
  try {
    return await readJson(exportPath);
  } catch {
    return null;
  }
}

export { CONFIG_DIR, PROJECTS_DIR, REPO_ROOT, SLUG_RE, FORBIDDEN_FIELD_NAMES };
