# 协议升级评审综合（GPT-5.6 Extended + Claude Sonnet 5）· manifest 提交点

> 日期：2026-08-11
> 关联方案书 v1：`docs/协议升级_manifest_提交点_方案书_v1.md`
> 两份独立评审，结论一致且互补。

---

## 一、GPT-5.6 Extended 核心判断（镜像站 vip-17，首条回复完整，正文被镜像站截断）

- **manifest + 内容哈希方向成立**。真正安全的是「manifest 绑定每个对象的不可伪造内容摘要，消费端 fail-closed」；「最后写 manifest」的发布顺序只能缩短失败窗口，不能消灭 CDN 可见性乱序。
- **修正点 ①**：兼容降级（manifest 404 走双读 index）会形成「降级回不安全协议」的窗口，严格说不算根治，只算过渡期容忍。
- **修正点 ②**：`build_id` 只哈希 `table_records`，`check_changed.py` 只按它判部署；协议/schema/index 元数据变化但业务数据没变时可能判「无需部署」。manifest 首次上线至少强制部署，长期把「发布语义版本」纳入指纹。
- 镜像站 3 次回复均截断在引用卡片处，7 条详答未取全 → 转 Claude Sonnet 5 完整评审。

## 二、Claude Sonnet 5 完整评审（7 条 + 落地清单）

### 结论摘要

方案成立，方向正确，可落地。核心正确性论证确认：**门户对「收到的原始字节」算 sha256 与 manifest 比对，任何跨 build 混搭（旧 manifest+新文件 / 新 manifest+旧文件）都会哈希不匹配 → fail-closed，不存在「被接受但混搭」的状态**。git 层面 `public/` 整包作为单个 Pages artifact 原子上传，发布端本身无混搭，混搭只可能来自消费端 CDN 缓存时序，manifest 恰好是消费端验证手段。

**需要修正/补强的点**：
1. 门户必须哈希 `r.content` 原始字节而非 `r.json()`（否则字节口径崩溃）——**当前代码唯一必须改的口径隐患**。
2. 无 manifest 不该永久降级双读 index，应 fail-closed 并靠下一轮部署强制推进。
3. manifest 含 4 文件哈希但门户只读 3 文件，schema 混搭会漏检。
4. 命中后应再断言 `manifest.build_id == index.build_id` 做纵深防御。

关键文件已核：`export.py` 用 `write_text(encoding="utf-8")`（无 BOM、Linux 换行）；`resources_bridge.py` 目前用 `r.json()` 而非原字节——这是唯一需要改口径的隐患点。

### 逐条结论

1. **成立**，无「被接受但混搭」漏网。漏检点：manifest 声明 4 文件、门户只校验 3（不读 schema）——建议门户连 schema 一并拉取哈希，或把 manifest files 收敛为门户实际校验集合；命中后加 `manifest.build_id == index.build_id` 断言。
2. **够**，且不会引入新窗口。`public/` 整包作为单个 artifact 原子上传，发布端无部分文件先到场景；真正不一致只来自消费端 CDN 缓存时序，manifest 在消费端裁决。manifest 单读足够（要么旧要么新，无自身混搭）。manifest fetch 失败必须 fail-closed 回退，不能静默当作「文件齐全」。
3. **可靠**，前提是门户哈希 `r.content` 原始字节而非 `r.json()`。编码无坑：`write_text(encoding="utf-8")` 无 BOM、CDN 字节直通无 CRLF/编码变换，`r.content` 字节 == 磁盘字节。`json.dumps(indent=2)` 字节在不同 Python 版本间变化**不影响安全**——manifest 哈希的是实际写盘字节，永远匹配真正上线的字节。
4. **GPT 判断正确**，双读 index 严格弱于 manifest。建议：**新门户对 remote 强制要求 manifest，无 manifest 即 fail-closed（回退本地），不保留「无 manifest → remote 双读」分支**。数据桥与门户同属一个运营者、桥每日调度部署，下一次导出就带 manifest，硬要求过渡窗口 <24h，且本地 `public/` 是同一 operator 控制的原子产物，语义安全。本地回退侧可宽松：本地有 manifest 则校验、无则信任 build_id（过渡期临时容忍，三个月后删除）。
5. **门户侧遗漏 4 处**：① 字节口径（新增 `r.content` 哈希步骤，`r.json()` 仅用于解析，先算 hash 后 parse）；② manifest fetch 与 single-flight/缓存同锁，命中聚合结果带 manifest 一起缓存，TTL 不变；③ manifest 缺失/结构非法/哈希失败三者统一 fail-closed 回退本地，不混入静默成功路径；④ 补 schema.json 拉取哈希 + `manifest.build_id == index.build_id` 断言。`_load_local()` 也要支持本地 manifest 校验。现有 `_validate_files` 结构校验保留在哈希通过后做第二道。
6. **替代方案评估**：
   - ETag/If-None-Match：**更差**。每文件粒度缓存协商，只能证明单文件未变，无法跨文件证明同 build。可留作 fetch 优化，但替代不了 manifest。
   - GitHub commit sha / raw 固定 sha 拉取：唯一真正「免 manifest」的正道——commit 本身是原子同快照绑定，门户解析最新 commit sha → 按 sha 拉 raw。但代价是依赖 GitHub API（未认证 60 次/小时限流）+ 走 raw.githubusercontent（非 CDN 缓存路径）+ 部署中 commit 在途竞态。对 dashboard 场景收益远低于复杂度，**否决**。
   - HTTP 自定义头带校验值：**不可行**。GitHub Pages/CDN 不允许逐文件自定义响应头，直接判死。
   - **结论**：没有比 manifest 更简单且同等安全的免 manifest 路径。manifest 本质是「在纯字节 GET 之上手工复刻 git commit 的原子绑定」。
7. **落地顺序 + 风险表**：
   - 顺序：① export.py 写文件→读回字节→写 manifest，validate.py 加自检 → ② 手动发布一次（`workflow_dispatch --force`）确认线上 manifest 出现 → ③ 门户 `_fetch_remote` 改 manifest+字节哈希+fail-closed，`_load_local` 同理 → ④ 四场景单测 → ⑤ 故障演练（线上改 capabilities 一字节 → 应回退本地）→ ⑥ 门户上线，桥侧双读分支删除。**桥侧先于门户落地 manifest**。
   - 风险表：

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| 1 | 门户误用 `r.json()` 而非 `r.content`，字节比对恒失败 | 高 | 中 | 代码评审重点盯此口径；单测 fixtures 用真实字节 |
| 2 | 过渡期（manifest 上线前）门户 fail-closed 短暂无 remote | 中 | 低 | 桥侧先发 manifest；回退本地仍可用；<24h 窗口 |
| 3 | 哈希比对通过但编码漂移误伤（BOM/CRLF 被某环节改写） | 低 | 低 | exporter 与门户同吃原始字节；CI 用 Linux 保证 \n |
| 4 | schema.json 混搭漏检（manifest 声明 4、门户校验 3） | 中 | 低 | 门户补齐拉取 schema 并哈希，或收敛 manifest 文件集 |
| 5 | 新 build 数据未变时 check_changed 判「无需部署」，manifest 不刷新 | 低 | 低 | manifest 首次上线走 `--force` 强制部署一次；语义版本纳入指纹为长期项 |

### 数据桥侧最小改动清单（ai-resource-hub）

1. `exporter/export.py` `write_outputs()`：写完全部数据文件 + schema 后，逐个 `Path.read_bytes()` 读回算 sha256，最后写 `public/manifest.json`（含 build_id/generated_at/bridge_version/files 哈希表）。文件写在前、manifest 最后。
2. `public/manifest.json` 随 `public/` 整包走现有 `export-public.yml` 上传（workflow 无需改动）。
3. `exporter/check_changed.py`：逻辑不变（仍比 index.build_id）；上线首次手动 `--force` 强制部署一次，确保 manifest 落线。
4. `exporter/validate.py`（可选但建议）：加「manifest.files 与磁盘文件哈希一致」自检，不一致即中止。

### 门户侧最小改动清单（00_中央平台/resources_bridge.py）

1. `_fetch_remote()`：新增拉取 `manifest.json`（与三文件同锁并发）；用 `r.content` 原始字节算 sha256（解析用 `r.json()`，两者都要），逐项比对 `manifest.files`；全匹配且 `manifest.build_id == index.build_id` 才接受，任一失败/缺失/结构非法 → 返回全 None 走 fail-closed 回退本地。
2. 补拉 `schema.json` 一并哈希（或要求数据桥收敛 manifest 文件集到门户实际消费集合）。
3. `_load_local()`：同样支持本地 manifest 校验；本地无 manifest 时过渡期信任 build_id（三个月后删除）。
4. 缓存/TTL/single-flight 不变；命中缓存仍按当前时刻重算 fresh。
5. 补 4 场景测试：全匹配接受 / 单文件哈希不匹配回退 / 无 manifest fail-closed / manifest 结构非法回退。

---

## 三、两份评审共识（拍板依据）

- manifest 方向成立，manifest 是纯字节 GET 下最简的「同 build 自证」手段。
- 门户必须哈希**原始字节**（`r.content`），不是 `r.json()`。
- **无 manifest 的降级策略是唯一需要运营者拍板的分叉**（见方案书 v2 决策点）。
- 桥侧先落地 manifest 并强制部署一次，门户再切 fail-closed。
