# 公开数据桥 exporter

飞书 Bitable → GitHub Pages 公开 JSON。供高级 AI 连接器（ChatGPT 官网 / Anthropic claude.ai）实读仓库、持续优化架构（方案书 §6.7、§7「GitHub 静态 JSON 快照 MVP」）。

**只公开能力+实例两表**，凭证池 / 账号资产 / 自动化任务日志 / 工具资产明细表整表不导出。

## 公开产物（`public/`）

| 文件 | 说明 |
|---|---|
| `index.json` | 入口：元数据 + `build_id`（内容哈希）+ 表计数 + `freshness` |
| `capabilities.json` | 资源能力规格表（白名单 10 字段） |
| `instances.json` | 资源实例表（白名单 7 字段 + 计算字段 `额度状态`） |
| `schema.json` | 各表白名单字段 + 主键说明 |

## 安全设计（方案书 §6.7）

1. **白名单 DTO 从零构造**：`config.json` 里每张表只列 `whitelist`，不在白名单的字段一律不输出（不是删除，是构造时就不带）。
2. **额度区间模糊化**：`剩余额度快照`/`额度总量`/`安全余量` → 计算 `额度状态` 区间（耗尽/接近安全余量/偏低/中等/充足/未知），**原始数值丢弃**，不公开精确额度。
3. **字段级剔除**：`需人工登录URL`、`缺失环境变量`、`验证指纹`、`凭证ID`、`任务列表` 等一律不输出。
4. **敏感扫描**：产物写完后逐条 regex 扫描，命中即退出码非 0、中止部署。配置在 `config.json` 的 `scan.patterns`。命中值不写日志，只输出文件/detector/offset/长度/sha256。
5. **语义校验**（`validate.py`）：count>0、主键唯一、引用完整、字段集⊆白名单、枚举合法、值形状（email/手机号/Bearer/密钥前缀）拒绝、与上一版记录数下降>30% 阻断。
6. **classification 声明**（`config.json` 每表 `classifications`）：PUBLIC（原值公开）/ PUBLIC_COARSE（必须 transform 后公开）/ INTERNAL（不出桥）/ SECRET（出现即 fatal）。**新字段必须声明 classification 才能导出**——未声明的白名单字段会被 validator 拒绝（默认拒绝，防安全策略随表数量退化）。
7. **build_id 变更才部署**（`check_changed.py`）：build_id=内容哈希（不含时间戳），与线上一致时跳过部署；`--force` 手动触发强制。
8. **Secret job / Pages job 隔离**：飞书 Secret 只在 export job（只读权限），发布权限只给 deploy job；失败通知只发 run_id/stage/error_code。

## 本地运行

```bash
# 真实同步（需要环境变量）
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_TOKEN="StmDbTXQWaujshs9NpIc3UFpnAc"
python exporter/export.py

# 本地验证链路（无需凭据，用 fixture 数据）
python exporter/export.py --mock
python exporter/validate.py                                  # 语义校验
python exporter/validate.py --baseline <线上index_url>       # 数量突变检测
python exporter/check_changed.py                             # build_id 变更判定
```

- CI 里走仓库 Secret（`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_BASE_TOKEN`），见 `.github/workflows/export-public.yml`。
- 表名与字段名必须与飞书一致（真源 `feishu/build_v03.py`）；字段变更时同步更新 `config.json`。
- **新增字段流程**：① 在飞书建字段 → ② 若需公开，加入对应表 `whitelist` + 在 `classifications.PUBLIC`（或 PUBLIC_COARSE，此时须配 transform）声明 → ③ `--mock` + `validate.py` 本地验证 → ④ push 触发 CI。

## 本地运行

```bash
# 真实同步（需要环境变量）
export FEISHU_APP_ID="cli_xxxx"
export FEISHU_APP_SECRET="xxxx"
export FEISHU_BASE_TOKEN="StmDbTXQWaujshs9NpIc3UFpnAc"
python exporter/export.py

# 本地验证链路（无需凭据，用 fixture 数据）
python exporter/export.py --mock
```

- CI 里走仓库 Secret（`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_BASE_TOKEN`），见 `.github/workflows/export-public.yml`。
- 表名与字段名必须与飞书一致（真源 `feishu/build_v03.py`）；字段变更时同步更新 `config.json`。

## 前置条件（一次性）

1. 飞书「AI 自助资源库」Base 中，能力表与实例表已建 **`AI 公开导出`** 视图。
2. 统一飞书应用（`FEISHU_APP_ID`）被添加为该 Base 的**只读协作者**。
3. 仓库 Settings → Secrets → Actions 里配置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_BASE_TOKEN`。
4. Settings → Pages → Source 选 **GitHub Actions**。
