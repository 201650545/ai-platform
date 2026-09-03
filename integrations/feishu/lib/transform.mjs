// lib/transform.mjs — Data transformation utilities.
// Converts Feishu field types and record values to public-safe JSON.

/** Feishu field type code → human-readable label. */
const FIELD_TYPE_MAP = {
  1: "Text", 2: "Number", 3: "SingleSelect", 4: "MultiSelect", 5: "DateTime",
  7: "Checkbox", 11: "Person", 13: "Phone", 15: "URL", 17: "Attachment",
  18: "SingleLink", 19: "Lookup", 20: "Formula", 21: "DuplexLink",
  22: "Location", 23: "GroupChat", 1001: "CreatedTime", 1002: "ModifiedTime",
  1003: "CreatedBy", 1004: "ModifiedBy", 1005: "AutoNumber"
};

/** Get human-readable field type label. */
export function getFieldTypeLabel(type) {
  return FIELD_TYPE_MAP[type] || `Unknown(${type})`;
}

/** Determine if a field type supports multiple values. */
export function isMultiValue(type) {
  return type === 4 || type === 21;
}

/** Extract select/multi-select options from field metadata. */
export function extractOptions(field) {
  if (!field.property?.options) return undefined;
  return field.property.options.map(o => o.name);
}

/**
 * Transform a raw Feishu field value to public-safe JSON.
 * Handles text arrays, relation fields, select fields, etc.
 */
export function transformFieldValue(value, fieldType) {
  if (value === null || value === undefined) return null;

  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    // Text array (rich text)
    if (value.every(v => typeof v === "object" && v !== null && "text" in v)) {
      const texts = value.map(v => v.text).filter(t => t !== "");
      if (texts.length === 0) return null;
      return texts.length === 1 ? texts[0] : texts;
    }
    // String array
    if (value.every(v => typeof v === "string")) {
      return value.length === 1 ? value[0] : value;
    }
    // Object array (persons, attachments, etc.)
    return value.map(v => typeof v === "object" && v !== null ? (v.text ?? v.name ?? String(v)) : v);
  }

  if (typeof value === "object" && value !== null) {
    // Relation fields (DuplexLink / SingleLink)
    if (fieldType === 21 || fieldType === 18) {
      const result = {};
      if (value.text) result.text = value.text;
      if (Array.isArray(value.text_arr)) result.text_arr = value.text_arr;
      if (Array.isArray(value.record_ids)) result.record_ids = value.record_ids;
      return Object.keys(result).length > 0 ? result : null;
    }
    // Generic object — extract text or name
    if (value.text !== undefined) return value.text;
    if (value.name !== undefined) return value.name;
    return String(value);
  }

  return value;
}

/**
 * Select and transform a single record, keeping only allowlisted fields.
 * @param {object} record - Raw Feishu record.
 * @param {string[]} allowedFields - Field names to include.
 * @param {object} fieldMeta - Map of field name → { type, ui_type }.
 * @param {object} options - { include_record_id, include_timestamps }.
 */
export function selectRecord(record, allowedFields, fieldMeta, options = {}) {
  const inputFields = record?.fields && typeof record.fields === "object" ? record.fields : {};
  const fields = {};
  for (const name of allowedFields) {
    const rawValue = Object.hasOwn(inputFields, name) ? inputFields[name] : null;
    const meta = fieldMeta?.[name];
    const fieldType = meta?.type;
    fields[name] = transformFieldValue(rawValue, fieldType);
  }
  const output = { fields };
  if (options.include_record_id === true && record.record_id) {
    output.record_id = record.record_id;
  }
  if (options.include_timestamps === true) {
    if (record.created_time !== undefined) output.created_time = record.created_time;
    if (record.last_modified_time !== undefined) output.last_modified_time = record.last_modified_time;
  }
  return output;
}

/**
 * Build a schema entry for a table.
 * Includes field types, options, and relation resolution.
 */
export function buildSchemaEntry(tableConfig, selectedFieldsMeta, tableIdToSlug, generatedAt) {
  const fields = selectedFieldsMeta.map(f => {
    const entry = {
      field_name: f.field_name,
      field_type: getFieldTypeLabel(f.type),
      ui_type: f.ui_type || null,
      multi_value: isMultiValue(f.type),
      required: false
    };
    const options = extractOptions(f);
    if (options) entry.options = options;

    // Resolve relation targets
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
    primary_field: tableConfig.fields?.[0] || null,
    source_view: tableConfig.view_name,
    field_count: selectedFieldsMeta.length,
    fields,
    updated_at: generatedAt
  };
}

/** Escape HTML special characters. */
export function escapeHtml(v) {
  return String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
