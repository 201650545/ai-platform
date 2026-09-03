结论

可以继续上线，但我会把当前版本判为“可用的 MVP 防线，不应作为长期稳定安全边界”。 核心方向是对的：白名单 DTO 从零构造优于黑名单删除；精确额度字段没有进入 DTO；敏感扫描在部署之前；Pages 只有扫描通过后才上传，因此扫描失败时旧 Pages 会继续作为 last-known-good，而不是被坏产物覆盖。当前公开索引显示桥版本 1，capabilities=21、instances=21。
201650545.github.io
+3
GitHub
+3
GitHub
+3

最大短板不是“regex 不够多”，而是 Public DTO 仍然太接近执行平面。 当前白名单同时公开 认证方案、允许主机、endpoint、请求体模板、健康探测、免费额度描述，实例又公开平台、实际模型、重置规则/日期、验证时间、状态、备注和所属能力；设计文档明确说明这些字段原本就是为了让 AI “读一行就知道怎么调用”。这套字段用于本地可信调度器没问题，用于互联网 Public Read Model 则暴露过量。
GitHub
+2
GitHub
+2

额度区间本身不能唯一反推出精确剩余量，但组合后能反推出量级/数值区间。 尤其当前 免费额度描述 被直接列入公开白名单，而设计文档给出的字段示例本身就是“2000万 token / 180天”；如果某实例关联到这个能力，再公开“充足 >50%”，外部即可得到“剩余 >1000万 token”这种数量级结论。每日快照再持续观察，会形成时间序列侧信道。
GitHub
+3
GitHub
+3
GitHub
+3

当前最需要立即修的两个实现问题： 第一，正式 CI 并没有 fail-closed 校验公开视图——找不到 AI 公开导出 时，代码会无条件改成拉整张表；第二，scanner 命中敏感值以后会把命中位置前后文本作为 snippet 打进 Actions 日志，相当于“成功阻止部署，却可能把凭证写进日志”。
GitHub
+2
GitHub
+2

另外，workflow 中 force 声称用于“跳过 build_id 变更检测”，但仓库当前根本不存在 build_id 对比逻辑；产物校验也只检查文件是否存在。今天仓库实际已经出现过一次 workflow #4 exit code 1 失败，而 YAML 中没有显式的失败通知路径。
GitHub
+2
GitHub
+2

问题清单
致命

Scanner 命中后会把疑似 Secret 本身写入 CI 日志——触发场景：有人把真实 key 粘进 备注/请求体模板/免费额度描述，regex 成功拦住 Pages，却由 snippet 把命中值及前后 18 字符打印出来；对不属于 GitHub 已登记 Secret 的第三方凭证，不能指望 GitHub 自动 mask。
GitHub
+2
GitHub Docs
+2

高危

公开视图丢失时正式任务 fail-open 到全表——触发场景：飞书视图被重命名/误删，view_id=None 后仍调用 /records，虽然字段白名单还在，但所有原本不应公开的记录都会参与导出。
GitHub
+1

“不公开精确额度”的政策被 免费额度描述 绕过——触发场景：能力写着“2000万 token / 180天”，实例公开额度单位、重置规则、重置日和额度区间，关联后直接得到有意义的数字上下界。
GitHub
+2
GitHub
+2

跨表可拼成近似可执行接口规格——触发场景：capabilities 提供 auth scheme + allowed host + endpoint + payload template，instances 提供平台、实际模型和 capability 关联，攻击者基本只缺凭证。
GitHub
+1

Regex 是“字段名 + 明文格式检测”，不是 Secret 检测器——触发场景：Base64/URL 编码、零宽字符、拆成两个字段、password/session/cookie/private_key/webhook/accessKey 等近义字段、供应商特有 key 前缀或高熵随机串均可漏过当前五条表达式。
GitHub

自由文本是最大的绕过通道——触发场景：备注、免费额度描述、请求体模板 内有人复制完整错误响应、登录链接、账号、Cookie、临时 token，而值没有符合现有 regex。
GitHub
+1

错误路径可能把飞书 Base Token 所在 URL 写进日志——触发场景：Bitable API 返回 HTTPError，代码异常字符串直接包含完整 url，而 URL 路径由 FEISHU_BASE_TOKEN 构造；GitHub Secret masking 应当只作为最后兜底，不能作为代码设计边界。
GitHub
+2
GitHub
+2

中

只检查文件存在，无法阻止“成功发布空数据”——触发场景：上游异常最终得到 [] 或关系字段全部异常，但四个 JSON 文件仍存在，workflow 就继续部署。
GitHub

没有主键唯一性、引用完整性和 enum 校验——触发场景：两个 instance_id 重复、实例指向不存在的 capability、状态出现自由文本，都可以通过当前导出链路。
GitHub
+1

无 HTTP retry/backoff——触发场景：飞书单次 429/5xx/短暂网络错误直接导致整次 daily export 失败，而不是短暂重试。
GitHub
+1

没有 freshness fail-safe——触发场景：连续多日导出失败时旧 Pages 会继续正常返回 200，调用方如果不检查 generated_at 就可能长期把陈旧数据当现状。当前索引虽有时间戳，但没有 expires_at/stale_after。
201650545.github.io

公开精确的重置日、到期日、上次/下次验证会暴露运营节奏——触发场景：外部长期采集 snapshots，可以知道何时恢复额度、何时进行验证、哪些资源处于耗尽/冷却窗口。
GitHub
+1

Public repo 的 schedule 存在“长期静默停摆”边界——GitHub 官方规定公开仓库连续 60 天没有仓库活动时会自动禁用 scheduled workflows；cron 在高负载时还可能延迟甚至丢弃，因此不能把 cron 成功本身当 freshness 保证。你选 :23 避开整点高峰是正确方向。
GitHub Docs
+2
GitHub Docs
+2

飞书 Secret 与 Pages 发布权限处在同一个 job/environment——触发场景：未来 job 增加第三方 action 或 workflow 被误改后，读取数据的凭证域与互联网发布权限域没有做到最小权限隔离。当前官方 Pages 方案本身支持独立 deploy job。
GitHub
+3
GitHub
+3
GitHub
+3

低

force 是死配置——触发场景：人工以为 force=false 会跳过未变化发布，实际上每天仍完整上传部署。
GitHub
+1

cache-dir 不是 setup-python 的有效 input——实际 workflow 已产生 warning；不会直接破坏安全，但会制造噪声，让真正警告更难发现。
GitHub
+1

Exporter 对两张表硬编码过重——index.json 和最终日志显式写死 capabilities/instances；以后再加工具/账号/权益/网关，即使 exporter 写出了 JSON，索引层也不会自然扩展。
GitHub

优化方案
1. 先把 Public DTO 从“可执行规格”降成“架构审查规格”

exporter/config.json 建议第一轮直接改：

Diff
 "资源能力规格表": {
   "whitelist": [
     "capability_id", "资源名称", "类别", "逻辑模型", "质量等级", "调用方式",
-    "adapter_id", "协议版本", "认证方案", "允许主机", "模型族", "endpoint",
-    "请求体模板", "健康探测", "免费额度描述", "请求模板版本", "状态"
+    "adapter_id", "协议版本", "模型族", "请求模板版本"
   ]
 },

 "资源实例表": {
   "whitelist": [
-    "instance_id", "平台", "实际模型名", "额度单位", "重置规则", "额度重置日",
-    "额度到期日", "限速", "配置版本", "验证策略", "上次验证",
-    "下次验证", "状态", "备注", "所属能力"
+    "instance_id", "平台", "实际模型名",
+    "额度单位", "重置规则", "配置版本", "所属能力"
   ]
 }

然后派生而不是直接公开：额度状态 保留；重置规则 最好再降成 daily/weekly/monthly/one_time/none/unknown；上次验证/下次验证 改成 freshness_band = <=7d / 8-30d / >30d / unknown；状态 改成 availability = available/degraded/unavailable/unknown。这样高级 AI 仍能审查资源覆盖、生命周期和架构，却拿不到实际调用靶面。当前设计文件明确区分了本地可信 adapter 与公开桥，做这层拆分与原架构并不冲突。
GitHub
+2
GitHub
+2

尤其建议立即删除 免费额度描述 的 identity export，因为设计方案示例本身就含精确数量。
GitHub

2. 公开视图必须 fail-closed

把 export.py 的 fetch_real 改成：

Diff
-def fetch_real(cfg):
+def fetch_real(cfg, allow_missing_view=False):
 ...
     view_id = resolve_view_id(token, base_cfg, table_id, base_cfg["export_view"])
+    if not view_id and not allow_missing_view:
+        raise RuntimeError(
+            f"缺少公开导出视图: table={table_name!r} "
+            f"view={base_cfg['export_view']!r}"
+        )
     params = {}
     if view_id:
         params["view_id"] = view_id

主流程同步改：

Diff
-raw_tables = fetch_mock(cfg) if args.mock else fetch_real(cfg)
+raw_tables = (
+    fetch_mock(cfg)
+    if args.mock
+    else fetch_real(cfg, allow_missing_view=args.no_view)
+)

这样 --no-view 才真正只存在于人工测试路径，CI 默认 fail-closed。
GitHub
+1

3. Scanner 绝不能打印原始命中值

当前 183–185 行建议直接废掉 snippet：

Diff
- start = max(0, m.start() - 18)
- snippet = text[start:m.end() + 18].replace("\n", " ")
- issues.append(f"{path.name}: /{pat}/ → …{snippet}…")
+ digest = hashlib.sha256(m.group(0).encode("utf-8")).hexdigest()[:12]
+ issues.append(
+     f"{path.name}: detector={pattern_id} "
+     f"offset={m.start()} value_sha256={digest}"
+ )

日志永远只出现 detector、文件、字段/offset、长度、hash，不出现 value。 GitHub 官方本身也建议敏感信息必须 mask，但这里应做到即使 masking 失效，程序也没把值写出来。
GitHub
+1

4. Scanner 升级为“结构检测 + 规范化 + 值检测”

不要继续单纯堆 regex。建议新增：

Python
Run
def canonicalize(s):
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return urllib.parse.unquote(s)

FORBIDDEN_KEYS = {
    "password", "passwd", "cookie", "session",
    "authorization", "private_key", "client_secret",
    "credential_id", "access_key",
    "密码", "密钥", "令牌", "凭证", "cookie"
}

然后做四层：

字段名 deny detector：规范化后出现 secret/credential/password/cookie/session 等即拒绝；

值 detector：JWT、PEM、常见 provider key prefix、Bearer、URL query credential；

高熵 detector：自由文本中 ≥24/32 字符的高熵 token 报警；

编码 detector：对疑似 Base64/percent-encoded 片段做一次安全解码后重新扫描。

这仍只是第二防线；真正解决 Base64/拼接/近义词问题的办法，是尽量不向公网输出自由文本和模板。当前 scanner 的五个 pattern 无法承担这个安全目标。
GitHub

5. 增加语义级产物 validator

建议新增 exporter/validate.py，在上传前至少检查：

count > 0
primary_key 非空且唯一
instances.所属能力 ∈ capabilities.capability_id
所有 record.keys() ⊆ schema 允许字段
status / enum 只能取预声明集合
禁止出现 URL query / email / phone / Secret-like value
与上一成功版本相比记录数下降 >30% → 阻断

force=true 只允许跳过“数据没变化”和“合理的数量突变确认”，绝不能跳过 Secret scanner、schema validation、0 条保护和引用完整性。

当前 21/21 可以作为第一次 baseline，但以后应读取上一成功发布的 index，而不是把 21 写死。
201650545.github.io

6. 实现真正的 build_id

export.py 增加：

Python
Run
import hashlib

canonical = json.dumps(
    table_records,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
build_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

写进 index.json：

Diff
 "bridge_version": meta["bridge_version"],
+"build_id": meta["build_id"],
 "generated_at": meta["generated_at"],

build_id 不包含 generated_at，否则每天都会变化，永远无法跳过部署。

同时增加：

JSON
"freshness": {
  "stale_after_hours": 48
}

消费者规则定为：now-generated_at > 48h 时只允许用于架构参考，不允许认为其代表最新资源状态。

7. 工作流拆成“Secret job”和“Pages job”

现在三个飞书 Secret 与 pages:write/id-token:write 同处一个 job。建议改成：

YAML
jobs:
  export:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: data-export
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@...
      - uses: actions/setup-python@...
        with:
          python-version: '3.12'

      - name: Export
        env:
          FEISHU_APP_ID: ${{ secrets.FEISHU_APP_ID }}
          FEISHU_APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
          FEISHU_BASE_TOKEN: ${{ secrets.FEISHU_BASE_TOKEN }}
        run: python exporter/export.py

      - name: Validate
        run: python exporter/validate.py

      - name: Compare build_id
        id: changed
        run: python exporter/check_changed.py

      - name: Upload Pages artifact
        if: steps.changed.outputs.changed == 'true'
        uses: actions/upload-pages-artifact@...
        with:
          path: public

  deploy:
    needs: export
    if: needs.export.outputs.changed == 'true'
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    permissions:
      pages: write
      id-token: write
    steps:
      - id: deployment
        uses: actions/deploy-pages@...

这是 GitHub Pages 官方推荐的 build/deploy 分 job 方向；Pages 权限只给 deploy job。
GitHub Docs
+1

另外删掉：

Diff
- cache-dir: ''

并升级 Node 24 兼容的 Actions major；当前 repo 的运行记录已经在提示旧 action 的 Node 20 和无效 cache-dir。当前 setup-python 已有 v6 系列、deploy-pages 已有 v5 Node 24 版本。生产环境最好进一步把第三方/官方 Actions pin 到完整 commit SHA，再用 Dependabot 升级。
GitHub
+2
GitHub
+2

8. HTTP 增加有限重试，同时清洗错误日志

http_json() 至少针对 429/500/502/503/504 和短暂网络异常做 3–4 次指数退避，并尊重 Retry-After；401/403 等配置错误不要重试。

同时：

Diff
-raise RuntimeError(f"HTTP {e.code} {url}\n{raw[:2000]}") from e
+raise RuntimeError(
+    f"HTTP {e.code} host={urllib.parse.urlsplit(url).hostname}"
+) from e

错误 body 如果确需诊断，也只能输出经过 redactor 后的短摘要。当前实现直接携带完整 URL 和前 2000 字符响应。
GitHub

9. 失败恢复定义成两个级别

扫描/拉取失败： 不 deploy，旧 Pages 自动继续服务，这一点当前流程已经成立；修复飞书源数据或 Secret 后人工 rerun 即可。
GitHub

错误数据已经成功部署： 当前缺显式 rollback。建议成功扫描后额外保存一个短期 safe-public-${build_id} artifact，保留 7–14 天；一旦发现 scanner 漏检，可重新部署上一 safe artifact，而不是重新从当下飞书生成。

通知方面，YAML 至少增加一个 notify job：

YAML
notify:
  needs: [export, deploy]
  if: ${{ always() &&
    (needs.export.result == 'failure' || needs.deploy.result == 'failure') }}
  runs-on: ubuntu-latest
  environment: bridge-alert
  steps:
    - run: python .github/scripts/notify_failure.py
      env:
        ALERT_WEBHOOK: ${{ secrets.BRIDGE_ALERT_WEBHOOK }}

通知文本只能发 run_id / failed_stage / error_code，不要发原始异常 body。GitHub 自身也支持 workflow run 通知，但我会把它当备份而不是唯一告警。
GitHub Docs

10. 为未来 4 张表改成通用 exporter

当前的 write_outputs() 和最终统计显式认识 capabilities/instances，应改成完全 config-driven。
GitHub

建议未来配置结构改成：

JSON
{
  "tables": {
    "资源实例表": {
      "slug": "instances",
      "primary_key": "instance_id",
      "view_required": true,
      "guards": {
        "min_count": 1,
        "max_drop_ratio": 0.30
      },
      "fields": {
        "instance_id": {
          "out": "instance_id",
          "classification": "PUBLIC",
          "transform": "identity"
        },
        "剩余额度快照": {
          "classification": "INTERNAL",
          "transform": "quota_band",
          "out": "quota_band"
        },
        "额度重置日": {
          "classification": "INTERNAL",
          "transform": "reset_cadence",
          "out": "reset_cadence"
        },
        "备注": {
          "classification": "INTERNAL",
          "publish": false
        }
      }
    }
  }
}

固定四类即可：

PUBLIC → 原值允许公开；PUBLIC_COARSE → 必须 transform 后公开；INTERNAL → 不出桥；SECRET → 若输入层发现即 fatal。

这样以后加工具、账号、权益、网关，不再复制一份 whitelist/fuzz/drop/scan 特例，而是新增字段必须先声明 classification + transform。没有 classification 的新字段默认拒绝导出，才能真正防止安全策略随着表数量增加而退化。

更省方案
方案	改动量	收益	安全评价
保留每日拉取，只在 build_id 变化时 deploy	小	少 Pages artifact / deployment、日志更干净	最推荐
每日拉取 → 每 2～3 天一次	极小	飞书读取次数下降约 50–67%	牺牲 freshness
Feishu 变更事件触发 GitHub	中～大	几乎无空跑	多一个公网 webhook/鉴权面，不值得当前 42 条规模
去掉 Pages，把 JSON commit 到 GitHub branch	小～中	少一个 Pages deploy job	不推荐，直接恶化 Git 历史不可逆风险
raw GitHub 文件作为读取源	小	HTTP 层更简单	前提仍是把产物 commit 进 Git；与核心安全立场冲突

当前标准 GitHub-hosted runner 在公开仓库的 Actions 使用本身是免费的，所以“每天跑一次”目前主要消耗的是 API 请求、artifact/deployment 次数和运维复杂度，而不是显著的 GitHub compute 费用。
GitHub Docs

因此我不会为了“省”而删除 Pages。你这个安全模型下，Pages artifact 恰恰比把 JSON 写进 Git branch 更合适：扫描漏掉一次错误时，Pages 可以被后续 deployment 覆盖；Git commit 则直接进入不可逆历史。

最优解是：

**Feishu 每日拉一次 → DTO/val
GitHub
+1
GitHub
+1
GitHub Docs
GitHub Docs
GitHub
201650545.github.io
