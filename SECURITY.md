# Security Policy

## Public-data boundary

Everything generated under `site/` is public internet data.
Only tables, views, records, and fields explicitly approved in
`config/export.json` may be exported.

## Credentials

Never commit or print:

- FEISHU_APP_SECRET
- tenant_access_token
- Authorization headers

Credentials must be stored only in GitHub Actions Secrets.

## Incident response

If a secret or private field is exposed:

1. Disable the workflow.
2. Unpublish GitHub Pages.
3. Rotate the Feishu App Secret.
4. Remove the affected Pages deployment/artifact.
5. Review Git history, Actions logs, caches, and public mirrors.
6. Re-enable only after the allowlist and output validation pass.
