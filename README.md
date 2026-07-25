# Feishu Learning English Public Export

This repository exports explicitly approved Feishu Bitable views and fields
to static JSON on GitHub Pages, enabling AI tools to read the data model,
records, and inter-table relationships without Feishu access.

## Public entry points

| File | Purpose |
|---|---|
| `/` (index.html) | Human-readable overview with links to all tables |
| `/data/manifest.json` | Machine-readable table list with checksums |
| `/data/schema.json` | Full data model: field types, options, relations |

## Current public tables

| Table | Slug | Fields | Records |
|---|---|---|---|
| 文本库 | `text-library` | 18 | 30 |
| 轻量学习记录 | `vocabulary` | 22 | 6000 |
| 学习日志 | `learning-log` | 9 | 92 |
| 每日计划 | `daily-plan` | 8 | 9 |

## How to add a new public table

1. **Create a view in Feishu**: Open the target table in the Feishu Base, add a new Grid View named exactly `AI 公开导出`.
2. **Add a config entry** in `config/export.json` under `tables`:
   ```json
   {
     "table_name": "表名",
     "table_slug": "english-slug",
     "view_name": "AI 公开导出",
     "enabled": true,
     "fields": ["字段1", "字段2"]
   }
   ```
3. **Fill the field allowlist**: List every field name that is safe to export. Never use `*` (wildcard). Never include `app_secret`, `tenant_access_token`, `authorization`, `client_secret`, or any credential field name.
4. **Push to GitHub**: The workflow runs automatically on the next cron tick (hourly at minute 17), or trigger it manually via `workflow_dispatch`.

## How to create the "AI 公开导出" view in Feishu

1. Open the Feishu Base ("Learning English").
2. Navigate to the target data table.
3. Click the `+` button next to the last view tab.
4. Select "Grid View" (表格视图).
5. Name it exactly `AI 公开导出` (with the space).
6. The view inherits all fields by default — field-level filtering is controlled by the `fields` allowlist in `config/export.json`.

## Output JSON structure

```
site/
├── index.html              # Human-readable overview
└── data/
    ├── manifest.json       # v2: table list with checksums
    ├── schema.json         # Field types, options, relations
    ├── text-library/
    │   ├── fields.json     # Field metadata
    │   └── records-0001.json
    ├── vocabulary/
    │   ├── fields.json
    │   ├── records-0001.json
    │   └── records-0002.json  # ...up to 12 chunks
    ├── learning-log/
    │   ├── fields.json
    │   └── records-0001.json
    └── daily-plan/
        ├── fields.json
        └── records-0001.json
```

Each record file contains:
```json
{
  "schema_version": 1,
  "table_name": "文本库",
  "view_name": "AI 公开导出",
  "chunk": 1,
  "records": [
    {
      "record_id": "recXXXXXX",
      "fields": { "字段名": "值" }
    }
  ]
}
```

## Consuming manifest and schema

**manifest.json** — Start here to discover available tables:
```json
{
  "schema_version": 2,
  "generated_at": "2026-07-25T...",
  "base": { "name": "Learning English" },
  "tables": [
    {
      "name": "文本库",
      "slug": "text-library",
      "view_name": "AI 公开导出",
      "field_count": 18,
      "record_count": 30,
      "fields_file": "data/text-library/fields.json",
      "fields_bytes": 1234,
      "fields_sha256": "...",
      "record_files": [
        { "path": "data/text-library/records-0001.json", "record_count": 30, "bytes": 5678, "sha256": "..." }
      ]
    }
  ]
}
```

**schema.json** — Understand field types and relations:
```json
{
  "schema_version": 1,
  "tables": [
    {
      "slug": "vocabulary",
      "primary_field": "单词",
      "fields": [
        { "field_name": "单词", "field_type": "Text", "multi_value": false },
        { "field_name": "关联文本", "field_type": "DuplexLink", "multi_value": true,
          "relation": { "target_table_slug": "text-library", "resolved": true } }
      ]
    }
  ]
}
```

## Local execution

```bash
# Set environment variables
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_TOKEN="xxxx"

# Syntax check
npm run check

# Sync (writes to site/)
npm run sync

# Validate (checks integrity, checksums, secrets)
npm run validate
```

## Avoiding sensitive information

Two layers of protection:

1. **View-level**: Only the `AI 公开导出` view is exported. Tables without this view are skipped entirely.
2. **Field-level**: The `fields` allowlist in `config/export.json` explicitly lists every exported field. No wildcard mode.

Additional safeguards:
- `assertNoSecrets()` in sync.mjs scans every output file for credential values and patterns before writing.
- `validate.mjs` re-scans all output files for `app_secret`, `tenant_access_token`, `authorization`, `bearer` tokens, `client_secret`, `github_token`, internal `table_id` values, and the `app_token`.
- `.env` files and API response caches are listed in `.gitignore` and explicitly forbidden in the validator.
- No `table_id`, `app_token`, or Feishu internal identifiers appear in `index.html`.

## GitHub Actions

- **Schedule**: hourly at minute 17 (`cron: "17 * * * *"`)
- **Manual trigger**: `workflow_dispatch`
- **Permissions**: `contents: read`, `pages: write`, `id-token: write`
- **All actions pinned** to full commit SHAs
- **Pipeline**: checkout → syntax check → sync → validate → configure pages → upload artifact → deploy
- **Failure stops deployment**: if sync or validate fails, the build job exits non-zero and the deploy job does not run.
