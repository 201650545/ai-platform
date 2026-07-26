# Semantic Layer Baseline

> 本文档记录 AI 语义层升级前的系统基线状态，用于变更追踪和回滚参考。

## 记录时间

2026-07-26

## 当前分支

- main: `717ec7d` (feat: add civil-service-exam project)
- 工作分支: `feature/ai-semantic-routing`

## 当前 build_id

`20260726T063553Z-717ec7d`

## 项目列表

| Slug | Title | Group | Tables | Records |
|------|-------|-------|--------|---------|
| civil-service-exam | 公考备考系统 | exam | 9 | 523 |
| learning-english | 英语学习系统 | learning | 9 | 7,647 |

总计: 2 项目, 18 表, 8,170 条记录

## 当前 catalog.json 字段

每个项目条目包含:
- slug, title, description, group, tags, status
- sync_status, is_stale, last_success_at
- manifest, schema, summary, homepage
- table_count, total_records

顶层包含:
- catalog_version: 1
- build_id, generated_at
- hub: { title, description }
- projects: []

**缺失**: domains, capabilities, entity_types, supported_queries, semantic, agent_guide, freshness, access_mode
**缺失**: 顶层 capabilities 索引, 顶层 domains 索引

## summary.md 状态

两个项目的 summary.md 由 sync-project.mjs 自动生成，内容为表清单和字段列表的机械汇总。
- 无项目用途说明
- 无核心目标
- 无表关系说明
- 无常见分析问题
- 无推荐读取顺序
- 无数据时效性说明
- 无已知限制
- 无不应做出的推断

## schema.json 状态

每个项目的 schema.json 包含:
- schema_version: 1
- project_slug, build_id, generated_at
- base: { name }
- tables: [{ table_name, slug, primary_field, source_view, field_count, fields, updated_at }]

fields 包含: field_name, field_type, ui_type, multi_value, required, options, relation
**缺失**: semantic_type, role, entity_type 等语义信息

## status.json 状态

当前字段:
- project_slug, build_id, sync_status, is_stale
- last_attempt_at, last_success_at
- source_record_count, published_record_count, warnings

**缺失**: expected_update_interval, table_count

## 首页状态

- 根目录 index.html 由 sync-hub.mjs 的 buildHubHomepage 生成
- 显示项目名称、描述、slug、group、status、sync_status
- 提供到 manifest.json, schema.json, summary.md, project index 的链接
- **缺失**: domains, capabilities, agent_guide, semantic 链接
- **缺失**: 筛选功能

## 旧 URL 兼容

- learning-english 项目通过 mirror_to_legacy_root 将数据镜像到 /data/ 路径
- /data/manifest.json, /data/schema.json, /data/<table-slug>/* 均可访问
- civil-service-exam 不镜像到旧路径 (mirror_to_legacy_root: false)

## 测试体系

当前验证脚本:
- `validate-config.mjs`: 验证 hub.yaml, credential-profiles.yaml, 项目 YAML 结构
- `validate-output.mjs`: 验证 catalog, manifest, schema, status, summary, checksums, record counts
- `security-scan.mjs`: 扫描敏感信息、Token、PII、高熵字符串、内部标识符

**缺失**: 语义配置验证, 路由测试, AI 文档验证, catalog 兼容性测试

## 安全扫描

覆盖范围:
- SECRET_PATTERNS: app_secret, tenant_access_token, user_access_token, authorization, client_secret, github_token, Bearer, PEM 私钥
- Token 前缀: cli_, Bearer, ghp_, gho_, ghs_, ghr_ (严格), t-, u- (歧义，需含数字)
- 内部标识符: table_id (tbl...), app_token (JSON 键值)
- PII: 手机号, 身份证, 邮箱, 银行卡号
- 高熵字符串: Shannon 熵 > 4.0
- 禁止文件: .env*, debug-response.json, api-cache.json, raw-response.json, .npmrc, .netrc

## 构建产物来源

所有公开产物均由代码生成:
- catalog.json ← sync-hub.mjs buildCatalog()
- 项目 manifest/schema/status/summary/index ← sync-project.mjs
- 首页 index.html ← sync-hub.mjs buildHubHomepage()
- 旧路径镜像 ← sync-project.mjs mirrorToLegacyPaths()
- 无手工维护的公开文件
