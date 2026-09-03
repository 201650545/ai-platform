# 迁移映射表（path-map）

> 2026-09-03 启动整合：9 仓 → 6 仓。本表回答「这个东西原来从哪来、迁到哪去了」。

## 迁入

| 旧仓 | 旧 head（迁移时） | 新位置 | 迁移分支 | 方式 |
|---|---|---|---|---|
| ai-hub | f97d372 | （根目录原样） | migration/core | merge --allow-unrelated-histories，完整历史保留 |
| ai-resource-hub | （见其 MIGRATION-NOTE） | resource-ops/ | migration/resource-ops | 同上（Agent B 执行） |
| feishu-data-hub | （见其 MIGRATION-NOTE） | integrations/feishu/ | migration/feishu | 同上（Agent C 执行） |
| ai-hub-memory（协议文档） | 323e21c | agent/memory/ | migration/core | 文档快照复制（运行数据与工具链留原仓） |

## 不迁移

| 仓 | 处置 |
|---|---|
| ai-hub-memory | 运行仓保留独立（Agent 记忆唯一真源），协议快照见 agent/memory/ |
| nitian-theme / handbook / workspace-index | 游戏域三仓，不在本次整合范围 |
| english-teaching-production | 生活域，保持独立 |
| financial-security-plan | 私有仓，永不公开，保持独立 |

## 旧 README 存档

- ai-hub 原 README 与项目简述：`docs/migration/legacy-ai-hub-README.md`、`legacy-ai-hub-项目简述.md`

## 收尾清单（集成时逐项勾）

- [x] merge migration/resource-ops、migration/feishu
- [x] 根 README / project.yaml 终稿（迁移状态改为完成）
- [x] 全局扫描旧仓名引用：功能性 URL（clone/链接/badge）修正；历史任务卡与问诊记录中的旧仓 URL 属史实描述不改写（旧仓 Archive 后仍可访问，最终删除前再评估）
- [x] feishu Pages 迁移：按 integrations/feishu/MIGRATION-NOTE 重新配置 Pages 源，验证新 URL 可访问
- [x] .github/workflows 路径适配（若旧仓带 CI）
- [ ] workspace-index 注册表切换唯一入口
- [ ] 新仓 AI 可读性验收：陌生 Agent 只读本仓能答「平台有哪些能力/记忆协议在哪/飞书导出在哪」
- [ ] 旧三仓 Archive（冷却 30-60 天后经人工确认再删）
