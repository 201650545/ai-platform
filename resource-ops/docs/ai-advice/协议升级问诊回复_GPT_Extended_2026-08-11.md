# 协议升级问诊回复 GPT-5.6 Extended（manifest 提交点评审）

> 日期：2026-08-11
> 模型：GPT-5.6 Extended（镜像站 vip-17.67673.live）
> 会话：`https://vip-17.67673.live/c/6a7bd884-2788-83ea-be23-03019de1a4ec`
> 状态：**⚠️ 首次回复被镜像站截断在「结论」标题**，追问补全中（见文末）。

---

## GPT 首次回复（截断，已收到的完整部分）

GPT 工作了 **2m58s**，期间做工具调用（Searching raw.githubusercontent.com / Assessed deployment fingerprints / Strengthened manifest rollout / Searched 1 website）。

### 开场

我会按「协议正确性 → CDN/缓存语义 → 哈希口径 → 过渡兼容 → 门户实现 → 替代方案 → 落地顺序」逐层核对代码和方案书。重点会把**真正可能出现的跨 build 竞态**列成时序，而不是只看 happy path。

### 中间判断

**manifest + 内容哈希这个方向是成立的**，但「最后写 manifest」不是 GitHub Pages/CDN 上真正提供原子性的原因。**真正让它安全的是「manifest 绑定每个对象的不可伪造内容摘要，消费端 fail-closed」**；发布顺序只能缩短失败窗口，不能消灭 CDN 可见性乱序。

### 两个比方案书更值得优先修的点

1. **兼容降级会形成「降级回不安全协议」的窗口**：manifest 404/不可见时走双读 index，严格说就不再是「根治」，只能算过渡期容忍。
2. **当前 `build_id` 只哈希 `table_records`**，而 `check_changed.py` 只按它决定是否部署；因此**协议/schema/index 元数据改变但业务数据没变时，可能被判「无需部署」**。manifest 首次上线至少要强制部署，长期最好把「发布语义版本」纳入发布指纹。

### 结论（标题，正文被截断）

方案方向 ……（被镜像站截断，追问中）

---

## 待补全内容（追问已发出）

1. 第 1-4 条要点结论（成立性/漏掉的竞态/发布顺序/哈希口径编码坑/降级够不够稳）
2. 第 5 条：门户侧改造点遗漏检查
3. 第 6 条：替代方案评估（ETag/If-None-Match、GitHub API commit sha、HTTP 头校验）
4. 第 7 条：落地顺序 + 风险表
