---
id: search_gateway-02
type: spec
project: ai-platform
component: search_gateway
status: active
---

# 02 · search_gateway 配置与路由规范

> 本文件是 search_gateway「三拆配置」与「路由策略」的长期规格真源。
> 修改路由语义前必须先读 `ADR/ADR-002-配置三拆与显式备用链`。

## 1. 配置职责矩阵（规范核心）

| 文件 | 回答的问题 | 可以包含 | 禁止包含 |
|---|---|---|---|
| `model_catalog.json` | 对外"有哪些模型" | alias、展示名、产品信息、能力档位 | credential、实时 health、fallback 执行状态 |
| `model_routes.json` | "这个模型走哪里" | primary、backup、fallback、fallback_policy | 密钥、渠道实时 quota |
| `channel_registry.json` | "渠道现在是什么状态" | credential 引用、quota、health、enabled | 产品 alias、产品展示规则 |

## 2. 路由原则

### 正常路径

```text
model alias
→ catalog resolve
→ route resolve
→ primary
→ upstream
```

### 异常路径

```text
primary failure
→ 显式 backup
→ 显式 fallback（仅 fallback_policy.enabled=true 时）
```

禁止：

- 自动遍历所有可用渠道
- 未声明的隐式 fallback
- 根据渠道列表顺序偷偷改变产品语义

## 3. 配置修改规则

新增模型：

1. 先登记 `model_catalog.json`
2. 再登记 `model_routes.json`
3. 确保依赖渠道已存在于 `channel_registry.json`
4. 验证 alias → route → channel 完整闭环

新增渠道：

1. 登记 `channel_registry.json`
2. 不自动获得任何模型流量
3. 只有被 `model_routes.json` 显式引用后才能进入路由

## 4. Secret 规则

Obsidian 中禁止记录：

- API Key
- Access Token
- Secret
- Credential 明文

仅记录：

- credential 字段语义
- credential 的加载方式
- secret 存放位置类型
- 轮换流程

## 5. 代码入口

主要配置/路由模块：

- `catalog_routes.py`

修改路由语义前必读：

- `ADR/ADR-002-配置三拆与显式备用链`
- `ADR/ADR-003-统一模型名聚合同模多渠道成员池`