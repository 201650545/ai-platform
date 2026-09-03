// lib/semantic.mjs — Semantic configuration loading, validation, and semantic.json generation.
// Reads human-maintained YAML configs from config/semantics/<slug>.yaml and generates
// machine-readable semantic.json for AI consumption.

import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";

const REPO_ROOT = path.resolve(".");
const SEMANTICS_DIR = path.join(REPO_ROOT, "config", "semantics");

/**
 * Controlled vocabulary for semantic_type.
 * Only these values are allowed in field mappings.
 * Do not add types without actual usage.
 */
export const SEMANTIC_TYPES = new Set([
  "entity_identity_title",
  "project_id",
  "task_id",
  "task_title",
  "task_status",
  "task_priority",
  "planned_date",
  "due_date",
  "event_date",
  "created_at",
  "updated_at",
  "duration_minutes",
  "outcome",
  "score",
  "accuracy",
  "attempt_count",
  "error_type",
  "knowledge_topic",
  "content_text",
  "source_reference",
  "relation",
  "status",
  "confidence",
  "difficulty",
  "review_due_at",
  "mastery_level",
]);

/**
 * Valid table roles.
 */
export const TABLE_ROLES = new Set([
  "plan",
  "event_log",
  "knowledge",
  "metric",
  "content",
  "error_log",
  "reference",
  "analysis",
]);

/**
 * Valid entity types for tables.
 */
export const ENTITY_TYPES = new Set([
  "task",
  "task_collection",
  "learning_event",
  "knowledge",
  "metric",
  "content",
  "reference",
]);

/**
 * Load a semantic configuration YAML file for a project.
 * @param {string} slug - Project slug.
 * @returns {Promise<object|null>} - Parsed semantic config, or null if not found.
 */
export async function loadSemanticConfig(slug) {
  const filePath = path.join(SEMANTICS_DIR, `${slug}.yaml`);
  try {
    const text = await fs.readFile(filePath, "utf8");
    return yaml.load(text);
  } catch (err) {
    if (err.code === "ENOENT") return null;
    throw err;
  }
}

/**
 * Load the query routing configuration.
 * @returns {Promise<object|null>} - Parsed routing config, or null if not found.
 */
export async function loadRoutingConfig() {
  const filePath = path.join(REPO_ROOT, "config", "query-routing.yaml");
  try {
    const text = await fs.readFile(filePath, "utf8");
    return yaml.load(text);
  } catch (err) {
    if (err.code === "ENOENT") return null;
    throw err;
  }
}

/**
 * Validate a semantic configuration against schema and controlled vocabulary.
 * @param {object} semanticConfig - Parsed semantic YAML.
 * @param {object} schema - The project's schema.json content.
 * @param {object} projectConfig - The project's YAML config.
 * @returns {{ errors: string[], warnings: string[] }}
 */
export function validateSemanticConfig(semanticConfig, schema, projectConfig) {
  const errors = [];
  const warnings = [];

  if (!semanticConfig) {
    errors.push("语义配置文件不存在");
    return { errors, warnings };
  }

  if (semanticConfig.semantic_version !== 1) {
    errors.push(`semantic_version 必须为 1，当前为 ${semanticConfig.semantic_version}`);
  }

  const proj = semanticConfig.project;
  if (!proj) {
    errors.push("缺少 project 配置");
    return { errors, warnings };
  }

  if (proj.slug !== projectConfig.project.slug) {
    errors.push(`semantic project.slug (${proj.slug}) 与项目配置 (${projectConfig.project.slug}) 不一致`);
  }

  // Validate domains, capabilities, entity_types are non-empty arrays
  for (const field of ["domains", "entity_types", "capabilities"]) {
    if (!Array.isArray(proj[field]) || proj[field].length === 0) {
      errors.push(`project.${field} 必须为非空数组`);
    }
  }

  // Build schema table lookup
  const schemaTables = new Map();
  for (const t of schema.tables || []) {
    schemaTables.set(t.slug, t);
  }

  // Validate tables
  const semTables = semanticConfig.tables || {};
  for (const [tableSlug, tableSem] of Object.entries(semTables)) {
    if (!schemaTables.has(tableSlug)) {
      errors.push(`语义配置中的表 "${tableSlug}" 不在 schema 中`);
      continue;
    }

    const schemaTable = schemaTables.get(tableSlug);

    // Validate role
    if (tableSem.role && !TABLE_ROLES.has(tableSem.role)) {
      errors.push(`${tableSlug}: 无效的 role "${tableSem.role}"`);
    }

    // Validate entity_type
    if (tableSem.entity_type && !ENTITY_TYPES.has(tableSem.entity_type)) {
      errors.push(`${tableSlug}: 无效的 entity_type "${tableSem.entity_type}"`);
    }

    // Validate primary_display_field exists in schema
    if (tableSem.primary_display_field) {
      const fieldExists = schemaTable.fields?.some(f => f.field_name === tableSem.primary_display_field);
      if (!fieldExists) {
        errors.push(`${tableSlug}: primary_display_field "${tableSem.primary_display_field}" 不在 schema 字段中`);
      }
    }

    // Validate date_field exists in schema (if not null)
    if (tableSem.date_field) {
      const fieldExists = schemaTable.fields?.some(f => f.field_name === tableSem.date_field);
      if (!fieldExists) {
        errors.push(`${tableSlug}: date_field "${tableSem.date_field}" 不在 schema 字段中`);
      }
    }

    // Validate status_field exists in schema (if not null)
    if (tableSem.status_field) {
      const fieldExists = schemaTable.fields?.some(f => f.field_name === tableSem.status_field);
      if (!fieldExists) {
        errors.push(`${tableSlug}: status_field "${tableSem.status_field}" 不在 schema 字段中`);
      }
    }
  }

  // Validate field mappings
  const semFields = semanticConfig.fields || {};
  for (const [tableSlug, fieldMap] of Object.entries(semFields)) {
    if (!schemaTables.has(tableSlug)) {
      errors.push(`字段映射中的表 "${tableSlug}" 不在 schema 中`);
      continue;
    }

    const schemaTable = schemaTables.get(tableSlug);
    const schemaFieldNames = new Set(schemaTable.fields?.map(f => f.field_name) || []);

    for (const [fieldName, fieldSem] of Object.entries(fieldMap)) {
      // Check field exists in schema
      if (!schemaFieldNames.has(fieldName)) {
        errors.push(`${tableSlug}: 字段 "${fieldName}" 不在 schema 中`);
        continue;
      }

      // Check semantic_type is in controlled vocabulary
      if (fieldSem.semantic_type && !SEMANTIC_TYPES.has(fieldSem.semantic_type)) {
        errors.push(`${tableSlug}.${fieldName}: 无效的 semantic_type "${fieldSem.semantic_type}"`);
      }
    }
  }

  // Check for unmapped schema fields (warning only)
  for (const [tableSlug, schemaTable] of schemaTables) {
    const mappedFields = semFields[tableSlug] || {};
    for (const f of schemaTable.fields || []) {
      if (!mappedFields[f.field_name]) {
        warnings.push(`${tableSlug}: 字段 "${f.field_name}" 未映射 semantic_type`);
      }
    }
  }

  return { errors, warnings };
}

/**
 * Build the public semantic.json from the semantic config and schema.
 * @param {object} semanticConfig - Parsed semantic YAML.
 * @param {string} buildId - Current build_id.
 * @param {string} generatedAt - ISO timestamp.
 * @returns {object} - semantic.json content.
 */
export function buildSemanticJson(semanticConfig, buildId, generatedAt) {
  const proj = semanticConfig.project;

  // Build tables object with all semantic metadata
  const tables = {};
  for (const [slug, t] of Object.entries(semanticConfig.tables || {})) {
    tables[slug] = {
      role: t.role || null,
      entity_type: t.entity_type || null,
      preferred_for: t.preferred_for || [],
      primary_display_field: t.primary_display_field || null,
      date_field: t.date_field || null,
      status_field: t.status_field || null,
    };
  }

  return {
    semantic_version: semanticConfig.semantic_version || 1,
    project_slug: proj.slug,
    domains: proj.domains || [],
    entity_types: proj.entity_types || [],
    capabilities: proj.capabilities || [],
    supported_queries: proj.supported_queries || [],
    tables,
    field_mappings: semanticConfig.fields || {},
    generated_at: generatedAt,
    build_id: buildId,
  };
}

/**
 * Build the public routing.json from the routing config and catalog.
 * @param {object} routingConfig - Parsed routing YAML.
 * @param {object} catalog - The built catalog.json content.
 * @returns {object} - routing.json content.
 */
export function buildRoutingJson(routingConfig, catalog) {
  // Build capability → projects index from catalog
  const capabilityIndex = {};
  const domainIndex = {};

  for (const proj of catalog.projects) {
    // Collect capabilities
    for (const cap of proj.capabilities || []) {
      if (!capabilityIndex[cap]) capabilityIndex[cap] = [];
      capabilityIndex[cap].push(proj.slug);
    }
    // Collect domains
    for (const dom of proj.domains || []) {
      if (!domainIndex[dom]) domainIndex[dom] = [];
      domainIndex[dom].push(proj.slug);
    }
  }

  // Sort indices for stable output
  for (const k of Object.keys(capabilityIndex)) capabilityIndex[k].sort();
  for (const k of Object.keys(domainIndex)) domainIndex[k].sort();

  // Build intent entries
  const intents = {};
  for (const [intentName, intentDef] of Object.entries(routingConfig.intents || {})) {
    // Resolve candidate projects
    let candidateProjects = [];

    if (intentDef.projects && intentDef.projects.length > 0) {
      // Explicit project list
      candidateProjects = intentDef.projects;
    } else if (intentDef.capabilities) {
      // Select all projects matching any of the capabilities
      const matching = new Set();
      for (const cap of intentDef.capabilities) {
        for (const slug of capabilityIndex[cap] || []) {
          matching.add(slug);
        }
      }
      candidateProjects = [...matching].sort();
    }

    intents[intentName] = {
      description: intentDef.description || "",
      matching_domains: intentDef.projects
        ? (catalog.projects.filter(p => intentDef.projects.includes(p.slug)).flatMap(p => p.domains || []))
        : Object.keys(domainIndex),
      matching_capabilities: intentDef.capabilities || [],
      candidate_projects: candidateProjects,
      recommended_first_files: intentDef.recommended_first_files || [],
      recommended_tables: intentDef.recommended_tables || [],
      record_data_required: intentDef.record_data_required ?? false,
    };
  }

  return {
    routing_version: routingConfig.routing_version || 1,
    generated_at: catalog.generated_at,
    build_id: catalog.build_id,
    status_vocab: routingConfig.status_vocab || [],
    intents,
    reading_depth: routingConfig.reading_depth || {},
    capability_index: capabilityIndex,
    domain_index: domainIndex,
  };
}
