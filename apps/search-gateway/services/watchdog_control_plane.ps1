﻿# watchdog_control_plane.ps1 — 控制面看门狗（阶段5，Claude 裁定 Q3/Q7 + 风险#1/#2）
# 单次检查（计划任务 WatchdogControlPlane 每 5 分钟调用）。探测内容：
#   1. lease.lock 心跳新鲜度（>150s → 3202）
#   2. control_plane_state.json updated_at 陈旧度（>20 分钟 → 3202）
#   3. 回滚趋势兜底（24h ≥6 次 → 3204；sync 自身已发，此处防其告警路径失效）
#   4. halted=true 提示（3205 已由 sync 发出，watchdog 只记录不重复告警）
#   5. 3203 流水线活性停滞：当前阶段【禁用告警、仅记录】——空代是合法稳定基线，
#      换代停滞≠故障（Claude 必改②/风险#1），真实候选放开后才考虑启用
# 不做裸进程存活检查（心跳新鲜度已覆盖"死了"和"活着没干活"两种情形）。
# 休眠保护（风险#2）：最近 5 分钟内系统唤醒 → 本轮跳过陈旧判定。
$ErrorActionPreference = 'SilentlyContinue'
$cpdir     = 'D:\项目\ai-hub\search_gateway\data\control_plane'
$stateFile = Join-Path $cpdir 'control_plane_state.json'
$leaseFile = Join-Path $cpdir 'lease.lock'
$alertLog  = Join-Path $cpdir 'watchdog_alerts.log'
$eventSrc  = 'API3100ControlPlane'
$dedupMin  = 30
$now = Get-Date

function Write-Alert([int]$id, [string]$kind, [string]$msg) {
  # 去抖：30 分钟内同 kind 不重复（读 alertLog 尾部）
  if (Test-Path $alertLog) {
    $tail = Get-Content $alertLog -Tail 30 -Encoding UTF8
    foreach ($l in $tail) {
      if ($l -match "^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*\[$kind/") {
        $t = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm', $null)
        if (($now - $t).TotalMinutes -lt $dedupMin) { return }
      }
    }
  }
  $line = "{0} [{1}/E{2}] {3}" -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $kind, $id, $msg
  $line | Out-File -Append -Encoding utf8 $alertLog
  try {
    if (-not [System.Diagnostics.EventLog]::SourceExists($eventSrc)) {
      [System.Diagnostics.EventLog]::CreateEventSource($eventSrc, 'Application')
    }
    Write-EventLog -LogName Application -Source $eventSrc -EventId $id -EntryType Error -Message $line
  } catch {}
}

# --- 0. 休眠保护 ---
$wake = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Power-Troubleshooter'; Id=1} -MaxEvents 1 |
        Select-Object -ExpandProperty TimeCreated -ErrorAction SilentlyContinue
if ($wake -and (($now - $wake).TotalMinutes -lt 5)) { exit 0 }

$state = $null
try { $state = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}

# --- 1. 心跳新鲜度（lease.lock）---
if (Test-Path $leaseFile) {
  try {
    $lease = Get-Content $leaseFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $hb = [datetime]::ParseExact($lease.heartbeat_at, 'yyyy-MM-ddTHH:mm:ss', $null)
    $age = ($now - $hb).TotalSeconds
    if ($age -gt 150) {
      Write-Alert 3202 'heartbeat_stale' ("lease 心跳陈旧 {0:N0}s（holder pid={1}）；状态 updated_at={2}" -f $age, $lease.pid, $state.updated_at)
    }
  } catch {
    Write-Alert 3202 'heartbeat_stale' ("lease.lock 解析失败：" + $_.Exception.Message)
  }
} else {
  # loop 以"登录触发的用户会话计划任务"运行（lark-cli UAT 绑定用户 DPAPI，
  # 无法跑 SYSTEM 服务）：仅在有人登录且任务未运行时告警；无人登录=预期停跑
  $loggedOn = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
  if ($loggedOn) {
    $t = Get-ScheduledTask 'ControlPlaneLoop' -ErrorAction SilentlyContinue
    if ($t -and $t.State -ne 'Running') {
      Write-Alert 3202 'heartbeat_stale' ("用户 {0} 已登录但 ControlPlaneLoop 任务未运行（State={1}）" -f $loggedOn, $t.State)
    } elseif (-not $t) {
      Write-Alert 3202 'heartbeat_stale' "用户已登录但 ControlPlaneLoop 任务不存在（被删除？）"
    }
  }
}

# --- 2. 状态文件陈旧度（loop 60s + 抖动，20 分钟未更新=严重滞后）---
if ($state -and $state.updated_at) {
  try {
    $up = [datetime]::ParseExact($state.updated_at, 'yyyy-MM-ddTHH:mm:ss', $null)
    $ageMin = ($now - $up).TotalMinutes
    if ($ageMin -gt 20) {
      Write-Alert 3202 'state_stale' ("状态文件 {0:N0} 分钟未更新（pid={1} last_run_result={2}）" -f $ageMin, $state.pid, $state.last_run_result)
    }
  } catch {}
}

# --- 3. 回滚趋势兜底 ---
if ($state -and $state.rollback_times) {
  $recent = 0
  foreach ($t in $state.rollback_times) {
    try {
      $rt = [datetime]::ParseExact($t, 'yyyy-MM-ddTHH:mm:ss', $null)
      if (($now - $rt).TotalHours -lt 24) { $recent++ }
    } catch {}
  }
  if ($recent -ge 6) {
    Write-Alert 3204 'rollback_trend' ("24h 内回滚 {0} 次（watchdog 兜底确认）" -f $recent)
  }
}

# --- 4. halted 提示（只记录）---
if ($state -and $state.halted) {
  ("{0} [INFO/halted] halted=true since={1} reason={2}（3205 已由控制面发出，仅 --clear-halt 解除）" -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $state.halted_since, $state.halted_reason) |
    Out-File -Append -Encoding utf8 $alertLog
}

# --- 5. 3203：禁用告警，仅记录（真实候选放开前不接警）---
if ($state -and $state.last_fetch_ok_at) {
  try {
    $fk = [datetime]::ParseExact($state.last_fetch_ok_at, 'yyyy-MM-ddTHH:mm:ss', $null)
    $ageH = ($now - $fk).TotalHours
    if ($ageH -gt 24) {
      ("{0} [LOG-ONLY/3203-disabled] last_fetch_ok_at 距今 {1:N1}h（真实候选放开后才考虑启用）" -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $ageH) |
        Out-File -Append -Encoding utf8 $alertLog
    }
  } catch {}
}
exit 0
