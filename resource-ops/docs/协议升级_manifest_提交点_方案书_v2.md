# 公开数据桥协议升级：manifest.json 提交点（v2 定稿）

> 状态：**v2 定稿**（已并入 GPT-5.6 Extended + Claude Sonnet 5 双评审结论 + 运营者拍板）
> 评审依据：`docs/ai-advice/协议升级评审综合_GPT_Claude_2026-08-11.md`
> v1 → v2 变更：见文末「v2 变更」。

## 1. 问题

跨 build 混搭：GitHub Pages 经 CDN 分发，门户对三文件独立 GET，各文件 CDN 缓存刷新时机不同 → 可能拉到「新 capabilities + 旧 index」。双读 index 只能证明 index 自身在两次读取间未变，**无法证明 caps/insts 与 index 同 build**。

## 2. 方案（定稿）

新增 `public/manifest.json`，作为「提交点」：

```json
{
  "build_id": "<sha256[:16]，与 index.json.build_id 一致>",
  "generated_at": "…",
  "bridge_version": 1,
  "files": {
    "index.json":        { "sha256": "…" },
    "capabilities.json": { "sha256": "…" },
    "instances.json":    { "sha256": "…" },
    "schema.json":       { "sha256": "…" }
  }
}
```

**安全本质**（评审共识）：真正提供安全性的是「manifest 绑定每个对象的不可伪造内容摘要 + 消费端 fail-closed」。发布顺序只能缩短失败窗口，不能消灭 CDN 可见性乱序。`public/` 整包作为单个 Pages artifact 原子上传，发布端无混搭，混搭只来自消费端 CDN 时序，manifest 在消费端裁决。

### 2.1 数据桥侧（ai-resource-hub）

1. `exporter/export.py` `write_outputs()`：写完 4 个数据文件后，逐个 `Path.read_bytes()` 读回算 sha256（哈希实际写盘字节），**最后写** `public/manifest.json`。
2. `public/manifest.json` 随 `public/` 整包走现有 `export-public.yml` 上传（workflow 不改）。
3. `exporter/check_changed.py`：逻辑不变；**上线首次手动 `--force` 强制部署一次**，确保 manifest 落线。
4. `exporter/validate.py`：加「manifest.files 与磁盘文件哈希一致」自检，不一致即中止。

### 2.2 门户侧（ai-hub · `00_中央平台/resources_bridge.py`）

1. `_fetch_remote()`：并发拉 `manifest.json + index/capabilities/instances/schema` 四文件（同锁）；**用 `r.content` 原始字节算 sha256**（解析用 `r.json()`，先算 hash 后 parse），逐项比对 `manifest.files`；**全匹配 且 `manifest.build_id == index.build_id` 才接受**，任一失败/缺失/结构非法 → 返回全 None fail-closed 回退本地。
2. **降级策略（运营者拍板：硬切换 fail-closed）**：remote 强制要求 manifest，**无 manifest 即回退本地，不保留「无 manifest → remote 双读」分支**。桥侧先发 manifest，过渡窗口 <24h。
3. `_load_local()`：支持本地 manifest 校验；本地无 manifest 时过渡期信任 build_id（三个月后删除该宽容分支）。
4. 缓存/TTL/single-flight 不变；命中缓存仍按当前时刻重算 fresh；命中聚合结果带 manifest 一起缓存。
5. 现有 `_validate_files` 结构校验保留在哈希通过之后做第二道。
6. 补 4 场景测试：全匹配接受 / 单文件哈希不匹配回退 / 无 manifest fail-closed / manifest 结构非法回退。

### 2.3 schema.json 纳入校验

manifest 声明 4 文件，门户**连 schema 一并拉取哈希**（承诺与执行一致，杜绝 schema 混搭漏检）。

## 3. 兼容性矩阵（定稿）

| 数据桥 | 门户 | 行为 |
|---|---|---|
| 有 manifest | 新版 | 严格 sha256 逐文件校验 + build_id 断言 |
| 有 manifest | 旧版 | 忽略 manifest，双读 index（现状，无危害） |
| 无 manifest | 新版 | **fail-closed 回退本地**（不裸奔） |
| 无 manifest | 旧版 | 现状 |

## 4. 落地顺序（评审共识）

1. 数据桥：`export.py` 写文件→读回字节→写 manifest；`validate.py` 加自检。
2. 手动发布一次（`workflow_dispatch --force`）确认线上 manifest 出现。**桥侧先于门户落地**。
3. 门户：`_fetch_remote` 改 manifest + 字节哈希 + fail-closed；`_load_local` 同理。
4. 四场景单测。
5. 故障演练（线上改 capabilities 一字节 → 门户应回退本地）。
6. 门户上线（切 fail-closed）。

## 5. 风险表（评审）

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| 1 | 门户误用 `r.json()` 而非 `r.content`，字节比对恒失败 | 高 | 中 | 代码评审重点盯此口径；单测 fixtures 用真实字节 |
| 2 | 过渡期（manifest 上线前）门户 fail-closed 短暂无 remote | 中 | 低 | 桥侧先发 manifest；回退本地仍可用；<24h 窗口 |
| 3 | 编码漂移误伤（BOM/CRLF 被某环节改写） | 低 | 低 | exporter 与门户同吃原始字节；CI 用 Linux 保证 \n |
| 4 | schema 混搭漏检 | 中 | 低 | 门户补齐拉取 schema 并哈希 |
| 5 | 新 build 数据未变时 check_changed 判「无需部署」，manifest 不刷新 | 低 | 低 | 首次 `--force` 强制部署；语义版本纳入指纹为长期项 |

## v2 变更（相对 v1）

- 降级策略由「无 manifest 降级双读 index」改为「**硬切换 fail-closed 回退本地**」（运营者拍板 + 双评审建议）。
- 门户哈希口径明确为 **`r.content` 原始字节**（非 `r.json()`）。
- schema.json 纳入门户校验（manifest 声明 4 文件、门户全校验 4 文件）。
- 新增 `manifest.build_id == index.build_id` 纵深断言。
- `validate.py` 加 manifest 自检；首次部署 `--force`。
- 补 v1 缺失的「发布端原子性」认知（单 artifact 上传，混搭只来自 CDN 消费端）。
