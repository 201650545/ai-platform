# 公开数据桥协议升级：manifest.json 提交点（跨 build 混搭根治）

> 状态：**草案 v1 · 待高级 AI 问诊评审**
> 关联：门户雏形 `ai-hub` 的 `/api/resources`（`00_中央平台/resources_bridge.py`）
> 日期：2026-08-11

## 1. 问题

现网链路：飞书表 → `exporter/export.py` → `public/` 四 JSON → GitHub Pages（CDN）→ 门户 `resources_bridge` 分三文件拉取（`index.json` / `capabilities.json` / `instances.json`）。

- `build_id` = **内容哈希**（`sha256(canonical JSON)[:16]`，不含 `generated_at`）——数据未变化时保持稳定，供 CI `check_changed.py` 判「是否需要部署」。
- **跨 build 混搭风险**：GitHub Pages 经 CDN 分发，门户对三文件独立 GET，各文件 CDN 缓存刷新时机不同 → 可能拉到「新 capabilities + 旧 index」的组合。
- **现状防护**：门户双读 index（index A → caps/insts → index B），只能证明「index 自身在两次读取间未变」，**无法证明 caps/insts 与 index 同属一个 build**。CDN 下 caps 命中旧缓存而 index 是新版时，双读 index 全程通过，混搭仍然生效。

## 2. 目标与约束

- **从协议层根治**：门户拿到一个文件集合，能自证「三者同属一个 build」。
- **向后兼容**：旧版门户（无 manifest 认知）不受影响；新版门户对旧产物降级，绝不裸奔。
- **雏形从简**：不加数据库/鉴权/复杂重试；数据文件（`capabilities/instances/index/schema`）结构尽量不动。
- **安全边界沿用**：凭证值不入库、额度模糊化不变（方案书 §6）。

## 3. 方案选型

### 方案 A（推荐）：`manifest.json` 提交点

新增 `public/manifest.json`：

```json
{
  "build_id": "<sha256[:16]，与 index.json.build_id 一致>",
  "generated_at": "2026-08-11T23:18:45+08:00",
  "bridge_version": 1,
  "files": {
    "index.json":        { "sha256": "…" },
    "capabilities.json": { "sha256": "…" },
    "instances.json":    { "sha256": "…" },
    "schema.json":       { "sha256": "…" }
  }
}
```

- **发布顺序（关键）**：先写 4 个数据文件，**最后写 `manifest.json`**。manifest 是「提交点」——它出现即声明「全部文件已就位」。
- **门户校验**：读 manifest → 读三文件 → 对**文件原始字节**算 `sha256` → 与 `manifest.files` 逐项比对 → 全匹配接受 / 任一不匹配回退本地（fail-closed）。
- **安全性**：任意时刻，读到「旧 manifest + 新文件」或「新 manifest + 旧文件」→ 哈希不匹配 → 拒绝。**不存在「被接受但混搭」的状态**。
- **兼容**：旧门户不读 manifest，一切照旧；新门户遇旧产物（无 manifest）→ 降级走现有双读 index。
- **数据文件结构零改动**（`capabilities.json` / `instances.json` 仍是纯数组）。

### 方案 B：逐文件内嵌 `build_id`

`capabilities.json` / `instances.json` 由数组改为 `{"build_id":…, "items":[…]}`。

- 门户可直接校验每文件 build_id 一致。
- **破坏向后兼容**：旧门户 `.map()` 直接炸；所有消费方需同步升级。当前唯一消费方是门户，但协议变更面大（CI/校验/文档/所有读取方），收益不高于方案 A。
- **判定：拒绝**。

### 方案 C：URL 版本化子目录（每 build 一个目录永久共存）

`/builds/<build_id>/index.json` + `/latest/` 指向。

- 完整可回溯、支持多版本回滚。
- 但要求发布端维护 build 目录栈、Pages 生成多快照，体积与复杂度上升。
- 雏形阶段无回滚需求，收益低。
- **判定：暂不做，列为未来演进项**（若后续需要「多 build 可回溯」再启用）。

## 4. 推荐方案 A 落地清单

### 4.1 数据桥侧（ai-resource-hub）

1. `exporter/export.py` `write_outputs()`：
   - 写完三数据文件 + schema 后，**逐个读回磁盘文件字节**算 `sha256`（与门户同口径，避免序列化漂移）。
   - 写 `public/manifest.json`（含 `files` 哈希表）——顺序保证：数据文件在前、manifest 最后。
2. `exporter/check_changed.py`：不变（仍比 index.build_id；manifest 随 `public/` 整包走部署判定）。
3. `.github/workflows/export-public.yml`：不变（`public/` 整包上传已含 manifest）。
4. `exporter/validate.py`：可选加一条「manifest.files 与磁盘文件哈希一致」自检。

### 4.2 门户侧（ai-hub · `00_中央平台/resources_bridge.py`）

1. `_fetch_remote()`：改为「读 manifest → 读三文件 → sha256 逐项比对 → 通过则接受」。
   - 读不到 manifest（旧产物/传输中）→ **降级现有双读 index**。
   - manifest 结构非法 → 视同不可用（走回退），不裸奔。
2. `_load_local()`：同样支持本地 manifest 校验（本地 `public/` 为 CI 产物，可能含 manifest）。
3. 缓存 / TTL / 回退策略不变。
4. 测试补 4 场景：manifest 全匹配接受 / 单文件哈希不匹配回退 / 无 manifest 降级双读 / manifest 结构非法回退。

### 4.3 产物

- 新增 `public/manifest.json`（CI 生成、`public/` 已在 `.gitignore`、随 Pages 部署）。
- 其余四文件结构不变。

## 5. 兼容性矩阵

| 数据桥 | 门户 | 行为 |
|---|---|---|
| 有 manifest | 新版 | 严格 sha256 逐文件校验 |
| 有 manifest | 旧版 | 忽略 manifest，双读 index（现状） |
| 无 manifest | 新版 | 降级双读 index（过渡期安全） |
| 无 manifest | 旧版 | 现状 |

## 6. 验证方案

1. **数据桥**：本地 `python exporter/export.py --mock` 跑通 → 断言 `public/manifest.json` 出现，`files` 哈希与磁盘文件一致。
2. **门户**：单测（patch manifest + 文件哈希）覆盖第 4.2 节 4 场景。
3. **集成**：真实发布一次 → 门户 `curl /api/resources` 显示 `source=remote`，日志/断言确认走 manifest 校验。
4. **故障演练**：手工改线上 `capabilities.json` 一个字节（模拟 CDN 混搭）→ 门户应回退本地 / 报 503；恢复后自动正常。

## 7. 风险

- manifest 本身也会被 CDN 缓存新旧交错 → 但任何不一致都导致哈希不匹配 → **拒绝方向永远安全（fail-closed）**，最坏是短暂回退本地。
- sha256 口径：门户读原始字节算，exporter 写完读回字节算 → 同口径，无 JSON 序列化漂移。
- 若未来要「多 build 可回滚」→ 演进方案 C。
