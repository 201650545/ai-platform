# feishu-data-hub → ai-platform 迁移说明

> 本文件由 feishu 迁移线（分支 `migration/feishu`）生成。
> 适用范围：**仅 `integrations/feishu/` 目录**。根目录文件、`.github/`、根 `docs/` 由负责根目录集成的维护者（A）统一处理，本线未改动。

---

## 一、来源与基线

| 项 | 值 |
|---|---|
| 来源仓 | <https://github.com/201650545/feishu-data-hub> |
| **来源 head SHA** | `e1482d1fe1ec258f0442f73bf9a5ce2ab12589b0` |
| 来源 head 提交标题 | `fix(ci): Hourly Sync 无 hourly 项目时安全跳过，避免空输出部署覆盖 Pages` |
| 来源 head 提交时间 | 2026-08-13T08:52:08-07:00 |
| 来源默认分支 | `main` |
| 来源附带 tag | `pre-data-hub-migration`（已一并 fetch） |
| 迁入文件数 | **74**（受版本控制文件，全部） |
| 目标仓 | <https://github.com/201650545/ai-platform> |
| 目标基线 | `71c81f25b0a43c4f94fc054185e21ba8ee28df77`（bootstrap） |
| **迁移日期** | **2026-09-03** |
| 迁移分支 | `migration/feishu` |

### 迁移动作

- 采用 `git merge src/main --allow-unrelated-histories --no-commit`（**未使用 `--squash`**），随后 `git mv` 将全部文件移入 `integrations/feishu/`。
- 合并提交为**双亲提交**（`71c81f2` + `e1482d1`），原仓完整提交历史可通过 `git log` 追溯。
- 内容保真校验：74/74 文件逐一比对 blob SHA，与 `src/main` **零差异**。

### 冲突处理

`README.md` 与 `.gitignore` 发生 add/add 冲突。按红线「只准动 `integrations/feishu/`、绝不碰根文件」：

- 根目录 `README.md` / `.gitignore` **一律以新仓（71c81f2）版本为准**（`--ours`），零改动。
- 源仓同名文件的内容另存于 `integrations/feishu/README.md` / `integrations/feishu/.gitignore`。

根 `README.md`、`project.yaml`、`.gitignore`、根 `docs/migration/` 均未被本线修改（已用 `git diff HEAD --` 验证为空）。

---

## 二、改动清单（本线实际提交的内容）

### 2.1 结构性改动

| # | 改动 | 说明 |
|---|---|---|
| 1 | 74 文件迁入 `integrations/feishu/` | blob SHA 逐一校验一致，无遗漏、无多余 |
| 2 | 清理 `git mv` 残留的空目录 | `.github/`、`config/`、`content/`、`examples/`、`lib/`、`scripts/`、`templates/`（根目录下已无文件，属移动后的空壳，非新仓原有文件） |

### 2.2 自我引用修正

| 文件 | 改动 |
|---|---|
| `README.md` | 顶部加迁移状态块；站点地址标注「原 `…/feishu-data-hub/` 已失效、迁移后待定」；Actions 表格补 `name:` 与「当前不生效」警告；本地执行段补 `cd integrations/feishu`；文档表新增本文件条目 |
| `package.json` | `name`: `feishu-data-hub` → `feishu-integration` |
| `package-lock.json` | 对应两处 `name` 同步改为 `feishu-integration`（保持 `npm ci` 可用） |
| `.github/workflows/sync-daily.yml` | `name` → `Feishu: Daily Sync`；加迁移说明头注；job 级 `defaults.run.working-directory: integrations/feishu`；`cache-dependency-path: integrations/feishu/package-lock.json`；`upload-pages-artifact.path` → `integrations/feishu/public` |
| `.github/workflows/sync-hourly.yml` | 同上 → `Feishu: Hourly Sync` |
| `.github/workflows/sync-manual.yml` | 同上 → `Feishu: Manual Sync` |
| `.github/workflows/validate.yml` | 同上 → `Feishu: Validate`；另将 `paths` 过滤由 `config/**`、`scripts/**`、`lib/**`、`.github/workflows/validate.yml` 全部加 `integrations/feishu/` 前缀 |
| `scripts/analyze_memory_phase3.py` | 硬编码旧 Pages URL → `PAGES_BASE`，默认 `https://201650545.github.io/ai-platform/`，可用环境变量 `FEISHU_PAGES_BASE_URL` 覆盖 |
| `scripts/generate_daily_review.mjs` | 同上（同一环境变量） |
| `scripts/add-project.mjs` | 帮助文本中的旧 Pages URL → 动态读取 `FEISHU_PAGES_BASE_URL`，默认同上 |
| `docs/ARCHITECTURE.md` | 加迁移说明头注；目录树根 `feishu-data-hub/` → `integrations/feishu/`；站点 URL → 新仓 Pages 根；流程图中 artifact 路径 → `integrations/feishu/public` |
| `docs/ONBOARDING.md` | 加迁移说明头注；5 处旧 Pages URL → 新仓 Pages 根 |
| `docs/OPERATIONS.md` | 加迁移说明头注；5 处旧 Pages URL → 新仓 Pages 根 |
| `docs/英语学习系统_记忆策略待完善.md` | 加迁移说明头注；仓库 URL → 新仓 `tree/main/integrations/feishu`；Pages URL → 新仓 Pages 根 |
| `docs/MIGRATION_BASELINE.md` | **仅加「历史存档」头注**，正文原样保留（记录的是迁入库之前的状态） |
| `docs/MIGRATION_REPORT.md` | 同上 |
| `docs/记忆策略问诊_交接指令包_2026-08-11.md` | 同上 |
| `MIGRATION-NOTE.md` | 新增（本文件） |

### 2.3 校验

- 4 个工作流 + `dependabot.yml` YAML 解析通过；`name` 与 `working-directory` 均已生效。
- 18 个 `.mjs`（`scripts/` + `lib/`）`node --check` 全部通过。
- `scripts/analyze_memory_phase3.py` 编译检查通过。

---

## 三、Pages 管线盘点

### 3.1 旧仓实测配置（`gh api repos/201650545/feishu-data-hub/pages`）

| 字段 | 值 |
|---|---|
| `build_type` | **`workflow`**（由 GitHub Actions 部署，非分支 Jekyll 构建） |
| `source.branch` | `main` |
| `source.path` | `/` |
| `html_url` | `https://201650545.github.io/feishu-data-hub/` |
| `cname` | `null`（无自定义域名） |
| `public` | `true` |
| `https_enforced` | `true` |
| `custom_404` | `false` |
| `pages/builds` | `[]`（API 无构建记录，说明发布完全走 Actions） |

### 3.2 新仓现状

- `gh api repos/201650545/ai-platform/pages` → **HTTP 404**，即**新仓 Pages 尚未启用**。

### 3.3 工作流清单（现位于 `integrations/feishu/.github/workflows/`，**当前不生效**）

| 文件 | `name:`（迁入后） | 触发器 | 产物路径 | 部署 |
|---|---|---|---|---|
| `sync-hourly.yml` | `Feishu: Hourly Sync` | `cron: 17 * * * *` + `workflow_dispatch` | `integrations/feishu/public` | ✅ configure/upload/deploy-pages |
| `sync-daily.yml` | `Feishu: Daily Sync` | `cron: 17 3 * * *` + `workflow_dispatch` | `integrations/feishu/public` | ✅ |
| `sync-manual.yml` | `Feishu: Manual Sync` | `workflow_dispatch` | `integrations/feishu/public` | ✅ |
| `validate.yml` | `Feishu: Validate` | PR / push（限 `integrations/feishu/**`）+ `workflow_dispatch` | — | ❌ 不部署 |

公共配置：

- `concurrency.group: feishu-pages`，`cancel-in-progress: false`
- Actions 全部 pin 到完整 SHA：`actions/checkout@d23441a…`、`setup-node@49933ea…`、`configure-pages@983d773…`、`upload-pages-artifact@7b1f4a7…`、`deploy-pages@d6db901…`
- 运行时读取的 Secrets：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_TOKEN`、`FEISHU_BASE_REGISTRY_JSON`、`FDH_PREV_HASH_URL`（内容哈希防噪音）、`FDH_NAME_BLACKLIST`（姓名黑名单，安全扫描用）
- 防噪音机制：`public/.deploy-skip` 存在则跳过部署（daily/hourly）

### 3.4 旧仓 Secrets 清单（仅名称，未取值）

`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_TOKEN`、`FEISHU_BASE_REGISTRY_JSON`、`FDH_PREV_HASH_URL`、`FDH_NAME_BLACKLIST`（共 6 个）。

> ⚠️ 配置与实际的偏差：`config/credential-profiles.yaml` 以 `FEISHU_PUBLIC_APP_ID` / `FEISHU_PUBLIC_APP_SECRET` 为**主**密钥、`FEISHU_APP_ID` / `FEISHU_APP_SECRET` 为**回退**；但旧仓并未配置 `FEISHU_PUBLIC_*` 两个 Secret，即实际一直走回退路径。集成时建议确认是否补齐，或简化为单一组。

---

## 四、Pages 迁移注意事项（集成阶段必读）

### 4.1 旧 URL 将失效

`https://201650545.github.io/feishu-data-hub/` 由旧仓 Pages 提供。旧仓一旦归档/关闭 Pages，该域名即 **404**。所有外部引用方（AI 工具、脚本、书签）需切换到新地址。

本线已将代码中的硬编码 URL 改为可覆盖常量：

- 默认值：`https://201650545.github.io/ai-platform/`
- 覆盖方式：环境变量 `FEISHU_PAGES_BASE_URL`
- 影响文件：`scripts/analyze_memory_phase3.py`、`scripts/generate_daily_review.mjs`、`scripts/add-project.mjs`

若集成后 Pages 源不是站点根（见 4.3），**必须**同步改这三处的默认值。

### 4.2 必须在新仓重新配置 Pages 源

1. `ai-platform` → Settings → Pages → **Source 选 `GitHub Actions`**（与旧仓 `build_type: workflow` 一致）。
   选「Deploy from a branch」会导致 `deploy-pages` 无法发布。
2. 仓库必须保留 `pages: write` + `id-token: write` 权限（工作流内已声明）。
3. 旧仓的 `cname` 为 `null`、`https_enforced: true`，新仓无需迁移域名配置。

### 4.3 ⚠️ 关键冲突：一个仓库只有一个 Pages 站点

旧仓是「一个仓库 = 一个 Pages 站点 = 站点根」。合并到 `ai-platform` 后，**四条业务线共享同一个 Pages 站点**。若 `ai-hub` / `ai-resource-hub` 也需要各自的 Pages 站点，不能共存于站点根——后部署者会整站覆盖先部署者（本线的 `upload-pages-artifact` 上传即整包替换）。

两个可选方案（**需由集成负责人拍板**）：

| 方案 | 做法 | 对本线的影响 |
|---|---|---|
| A. 单一聚合站点（推荐） | 建一个统一构建 job，把各线输出聚合到 `public/<line>/` 后一次性上传 | 本线三个 workflow 的部署段需并入统一 job；artifact 路径改为 `public/feishu/`；脚本默认 URL 改为 `https://201650545.github.io/ai-platform/feishu/` |
| B. 各线独立发布 | 本线继续单独部署到整站根，其他线改用外部托管或独立 Pages 仓 | 本线无需改动，但其他线不能再用本仓 Pages |

缓存清除依赖 `build_id`（`catalog-versioned/<build_id>.json` + `?v=<build_id>`），换域名后首次部署即生成新 `build_id`，无需额外处理。

### 4.4 工作流需迁移到根目录（A 负责）

GitHub **只识别仓库根目录**的 `.github/workflows/`。本线按红线未碰根目录，因此四个工作流文件当前**不会触发任何运行**。集成时请：

1. 将 `integrations/feishu/.github/workflows/*.yml` 移到根 `.github/workflows/`。
2. 文件内**已预置**好以下适配，迁到根目录后可直接使用，**无需再改命令**：
   - job 级 `defaults.run.working-directory: integrations/feishu`
   - `cache-dependency-path: integrations/feishu/package-lock.json`
   - `upload-pages-artifact.path: integrations/feishu/public`
   - `validate.yml` 的 `paths` 过滤已加 `integrations/feishu/` 前缀
3. `name` 已统一加 `Feishu: ` 前缀，避免与其他业务线重名；若仍有冲突请再确认。
4. `concurrency.group: feishu-pages` —— 若其他业务线也部署 Pages，需确认不冲突（见 4.3）。
5. **`dependabot.yml` 同样只识别根目录**：`integrations/feishu/.github/dependabot.yml` 需合并进根 `.github/dependabot.yml`，否则 Actions SHA pin 不再自动更新。

---

## 五、敏感信息扫描结论

扫描范围：`integrations/feishu/` 全部 74 个文件（提交前执行）。

| 检查项 | 结果 |
|---|---|
| 已知真实凭据（本地记忆中的飞书 App ID/Secret、open_id、Base token） | ✅ 未命中 |
| `app_secret` / `sk-` / `ghp_` / `github_pat_` / 私钥头 | ✅ 无实值（仅 Secret **名称**与文档措辞） |
| 飞书 token（`bascn`/`bastkn`/`wikcn`/`doxcn`/`shtcn`）、`ou_` open_id | ✅ 未命中 |
| 手机号、邮箱 | ✅ 未命中 |
| 个人姓名 / 学校 / 地区等 PII | ✅ 未命中 |
| `package-lock.json` 内 registry 凭据 | ✅ 无 |
| 高熵长串（≥32 位） | ✅ 全部为 `actions/*@<commit-sha>` 的 pin，非密钥 |

**结论：未发现真实密钥、飞书凭证或个人数据，符合红线。**

### 建议复核项（非阻断）

`docs/英语学习系统_记忆策略待完善.md` 含飞书 Base 链接
`https://my.feishu.cn/base/K15hbHNwtaY3BWs1STLcG092n4g`（learning-english 数据源）。
该链接在旧仓（同为公开仓）中已公开，且本就是「公开导出」项目的数据源，**不是密钥**；但公开仓暴露 Base ID 意味着他人可凭此 ID 尝试申请权限。建议集成时确认是否符合预期，必要时移除或改写为「见 `config/projects/learning-english.yaml`」。

---

## 六、集成后待办清单

- [ ] 新仓启用 Pages，Source 选 **GitHub Actions**
- [ ] 确定 Pages 归属方案（4.3 的方案 A 或 B），并据此调整本线 artifact 路径与脚本默认 URL
- [ ] 4 个 workflow 迁移到根 `.github/workflows/`（4.4）
- [ ] `dependabot.yml` 合并进根 `.github/dependabot.yml`
- [ ] 6 个 Secrets 迁移到新仓，并确认 `FEISHU_PUBLIC_*` 是否补齐
- [ ] 旧仓归档前通知引用方切换 URL；归档后旧站点即失效
- [ ] 复核第五节的飞书 Base 链接披露问题
- [ ] 更新根 `README.md` 迁移状态表中 `feishu-data-hub` 一行的状态
