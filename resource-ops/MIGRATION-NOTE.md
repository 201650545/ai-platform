# MIGRATION-NOTE · ai-resource-hub → ai-platform/resource-ops

- **来源仓**：`ai-resource-hub`（本地 `D:\ai-resource-hub`，远程 `github.com/201650545/ai-resource-hub`）
- **来源 head SHA**：`df6a2f68c9f6128e3c085bafce211c8936791335`（`sync(三端): 本地→GitHub 自动同步 20260902-1701`）
- **迁入日期**：2026-09-03
- **目标**：`github.com/201650545/ai-platform` 的 `migration/resource-ops` 分支，`resource-ops/` 子目录
- **目标基线**：main @ `71c81f2`（bootstrap）
- **迁入方式**：把源仓克隆到临时目录 → `git mv` 全部内容至 `resource-ops/`（生成 rename 提交，历史完整保留）→ 以 `--allow-unrelated-histories` 并入目标仓。源仓保持只读，未修改未删除。
- **迁入文件数**：164 个已提交文件（源仓顶层的 `runtime/` 为 `.gitignore` 忽略的未跟踪目录，不含在 git 历史中，未随迁移）。

## 引用修正清单（本目录内旧仓名自引用 → 新位置自解释）

| 文件 | 改动 |
|------|------|
| `README.md` | 标题改为 resource-ops；新增"本目录为 ai-platform 单仓 resource-ops 子目录（原 ai-resource-hub 迁入）"说明；公开数据桥 URL `…/ai-resource-hub/` → `…/ai-platform/resource-ops/` |
| `方案书.md` | 附：本仓库 `github.com/201650545/ai-resource-hub` → `…/ai-platform/tree/main/resource-ops` |
| `.github/workflows/export-public.yml` | 校验基线 `…/ai-resource-hub/index.json` → `…/ai-platform/resource-ops/index.json` |
| `exporter/check_changed.py` | `ONLINE_INDEX` → `…/ai-platform/resource-ops/index.json` |
| `exporter/export.py` | 导出 JSON `repo` 字段 → `…/ai-platform/tree/main/resource-ops` |
| `scheduler/sync.py` | `REMOTE_BASE` → `…/ai-platform/resource-ops` |
| `feishu/backfill_ei_new_resources.py` | 本地路径 `D:/ai-resource-hub/docs/资源调研` → `D:/AI平台-B/resource-ops/docs/资源调研` |
| `tests/test_control_plane_stage5.py` | `sys.path` `D:\ai-resource-hub` → `D:\AI平台-B\resource-ops` |
| `scheduler/_test_cfg.json` | `db_path`/`credentials_path` `D:\项目\ai-resource-hub\…` → `D:\AI平台-B\resource-ops\…` |
| `sync/README.md` | `--repo ai-resource-hub` → `--repo ai-platform` |
| `sync/sync_config.json` | repos 条目 `ai-resource-hub`→`ai-platform`（path `D:\ai-resource-hub`→`D:\AI平台-B`）；feishu 导出 name/cwd → `ai-platform resource-ops` / `D:\AI平台-B\resource-ops` |
| `docs/Claude调度大脑_接入规范_2026-08-30.md` | 仓库名与运行路径（`cd /d/ai-resource-hub/sync` → `/d/AI平台-B/resource-ops/sync`）及"已配置仓库"列表改为 ai-platform |

## 保留未改（历史归档）

`docs/ai-advice/*`（问诊/审查记录）、`docs/资源调研/*`、`docs/分派指令包`、`docs/免费资源*`、`docs/协议升级*`、`docs/会话交接包/项目交接总结`、`reports/stage5_wire_evidence_20260829.md`、`sync/sync_log.md` 均为**带日期的历史文献/运行日志**，其中的旧仓名属记录性内容，保留原貌以保证归档真实性。如后续需要，可批量替换（github.com/201650545/ai-resource-hub → …/ai-platform）。

> 备注：`resource-ops/.github/workflows/` 下的 Actions 工作流随子目录移动后不会被 GitHub 在根级自动发现，其迁移后是否继续托管 CI 需由仓库所有者确认。