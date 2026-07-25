# Security Policy

## Public-data boundary

Everything generated under `site/` is public internet data.
Only tables, views, records, and fields explicitly approved in
`config/export.json` may be exported.

## Two layers of protection

1. **View-level**: Each table must have a dedicated view named `AI 公开导出`. Tables without this view are never exported. No other view name is accepted as a substitute.
2. **Field-level**: The `fields` array in `config/export.json` is an explicit allowlist. Wildcard (`*`) is forbidden. Empty arrays are forbidden. Sensitive field names (`app_secret`, `tenant_access_token`, `user_access_token`, `authorization`, `client_secret`) are blocked at config validation time.

## Required GitHub Secrets

| Secret | Purpose |
|---|---|
| `FEISHU_APP_ID` | Feishu app identity |
| `FEISHU_APP_SECRET` | Feishu app credential (never logged, never written to output) |
| `FEISHU_BASE_TOKEN` | Bitable app token (the Base to read from) |

## What must never enter logs, code, or output

- `FEISHU_APP_SECRET` value
- `tenant_access_token` value
- `user_access_token` value
- `authorization` header values
- `client_secret` values
- GitHub tokens
- Feishu `app_token` / `BASE_TOKEN` value
- Internal `table_id` values

## Runtime safeguards

- `assertNoSecrets()` in `sync.mjs` checks every serialized JSON string against credential values and suspicious patterns before writing to disk.
- `validate.mjs` re-scans all output files for:
  - `app_secret`, `tenant_access_token`, `user_access_token`, `authorization`, `client_secret`, `github_token` patterns
  - `bearer` token patterns
  - Hardcoded `table_id` prefixes
  - The `app_token` value
- Forbidden files (`.env`, `debug-response.json`, `api-cache.json`, `raw-response.json`) are rejected if found in `site/`.

## Read-only snapshot guarantee

Even though the Feishu source tables are editable by their owners,
the GitHub Pages export is always a **read-only snapshot**:

- The sync script only reads from Feishu APIs (GET / list operations).
- No write operations are performed on the Feishu Base.
- The GitHub Pages site is static — no backend, no database, no user input.
- The snapshot is refreshed hourly by GitHub Actions, but each deployment is immutable until the next run.

## Incident response

If a secret or private field is exposed:

1. Disable the workflow immediately.
2. Unpublish GitHub Pages.
3. Rotate the Feishu App Secret.
4. Remove the affected Pages deployment and artifact.
5. Review Git history, Actions logs, caches, and any public mirrors.
6. Re-enable only after the allowlist and output validation pass.
