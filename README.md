# Feishu Learning English Public Export

This repository exports explicitly approved Feishu Bitable views and fields
to static JSON on GitHub Pages.

## Public entry point

`/data/manifest.json`

## Security rule

Everything generated under `site/` is public. Export configuration must use:

- exact table name;
- exact dedicated public view name;
- explicit field allowlist.

Secrets are stored only in GitHub Actions Secrets.
