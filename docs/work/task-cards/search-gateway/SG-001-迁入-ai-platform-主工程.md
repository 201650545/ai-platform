---
id: SG-001
project: ai-platform
component: search_gateway
status: done        # done 仅表示历史实施工作已完成，不代表正式验收通过
implementation_status: completed
acceptance_status: pending   # 未执行正式验收，待复核
record_type: retrospective
date: 2026-09-05
---

# SG-001 · 迁入 ai-platform 主工程（回溯任务卡）

> ⚠️ 本卡为**回溯补记**：实施工作确已完成，但当时未定义验收标准、未执行正式验收。验收状态 = **待复核**。

## 目标
将 search_gateway（API 转发网关）从旧目录整体迁入 ai-platform 工程，作为仓内子项目。

## 实施内容（已完成）
- services/ 代码 + data/ 配置数据整体迁入 `D:\项目\ai-hub\search_gateway`
- 修改全部相关路径配置：
  - `services\channels.py`、`capabilities.py`、`resource_config.py`、`quota.py`、`history.py`、`rate_limit.py` 的 DATA_DIR / base / CAP_FILE 路径
  - 启动脚本 `start_search_gateway_3000.ps1`、看门狗 `watchdog_3100_alert.ps1` / `watchdog_control_plane.ps1` / `watchdog_gateway.bat`
  - 全局启动 `start_all.ps1`、清理/重启脚本 `purge_3000.ps1` / `restart_sg_dsh.ps1`
- 重新注册计划任务（Arguments / WorkingDirectory 指向新路径）

## 验收标准（回溯补记，待复核）
- [ ] :3000 / :3100 迁移后可正常监听与启动
- [ ] 遗传功能（模型调用、健康检查）在新路径下不受影响
- [ ] 无旧路径残留引用
- [ ] 计划任务 / 看门狗可正常拉起服务

## 产物
- ADR：`ADR/ADR-001-迁入-ai-platform-作为子项目`
- 建设记录：`03-search_gateway-建设与演进记录`（迁入里程碑）

## 决策依据
仅引用 ADR-001，不在此重复设计理由。