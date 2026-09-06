# ============================================================
# inspect_gateways.ps1 — 网关运行态只读探测器
# 用途：读 config/gateways.json（声明式真源），探测实际进程/端口/健康，
#       生成 gateway_runtime.json + gateway_drift.json（禁止手改，整体覆盖写入）。
# 原则：本脚本绝不启动、停止、修复任何服务；只报告与声明态的偏差。
# 用法：powershell -ExecutionPolicy Bypass -File inspect_gateways.ps1
#       （可加 -Config <path> 指定 gateways.json，-OutDir <dir> 指定输出目录）
# ============================================================
param(
    [string]$Config = "$PSScriptRoot\gateways.json",
    [string]$OutDir  = (Join-Path (Split-Path $PSScriptRoot -Parent) 'search_gateway\data')
)

function Normalize-PathString {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    return $Path.Trim().Trim('"').Replace('/', '\').TrimEnd('\').ToLowerInvariant()
}

$script:__svcproc = @()
function Get-ServiceProcesses {
    param([string]$CanonicalPath, [string]$Entrypoint, [string[]]$CommandMatch)
    $script:__svcproc = @()
    $canonical = Normalize-PathString $CanonicalPath
    $entryFull = Normalize-PathString (Join-Path $CanonicalPath $Entrypoint)
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($proc in $all) {
        if ([string]::IsNullOrWhiteSpace($proc.CommandLine)) { continue }
        $cmd = Normalize-PathString $proc.CommandLine
        if (-not $cmd.Contains($entryFull)) { continue }
        $allMatch = $true
        foreach ($token in $CommandMatch) {
            if (-not $cmd.Contains((Normalize-PathString $token))) { $allMatch = $false; break }
        }
        if ($allMatch) { $script:__svcproc += $proc }
    }
}

function Get-PortListener {
    param([int]$Port)
    if ($null -eq $Port -or $Port -eq 0) { return $null }
    $listeners = @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    ) | Where-Object { $null -ne $_ }
    if ($listeners.Count -eq 0) { return @() }
    return @($listeners | ForEach-Object {
        [ordered]@{ local_address = $_.LocalAddress; local_port = $_.LocalPort; pid = $_.OwningProcess }
    })
}

function Test-HttpHealth {
    param([string]$Url, [int]$TimeoutSec = 2)
    if ([string]::IsNullOrWhiteSpace($Url)) { return $null }
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        return [ordered]@{ status = 'healthy'; http_status = [int]$response.StatusCode; error = $null }
    }
    catch {
        return [ordered]@{ status = 'unhealthy'; http_status = $null; error = $_.Exception.Message }
    }
}

function Get-ProcessAgeSeconds {
    param($Process)
    try {
        if ($null -eq $Process.CreationDate) { return $null }
        $created = [Management.ManagementDateTimeConverter]::ToDateTime($Process.CreationDate)
        return [int]((Get-Date) - $created).TotalSeconds
    } catch { return $null }
}

# ------------------------------------------------------------ 主流程
if (-not (Test-Path $Config)) { Write-Error "找不到配置: $Config"; exit 1 }
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

$services = $cfg.gateways

$now = Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'
$runtime = @{
    schema_version = 1
    generated_at   = $now
    services       = @{}
}
$driftItems = @()

foreach ($key in ($services.PSObject.Properties.Name | Sort-Object)) {
    $svc = $services.$key
    $entry = [ordered]@{
        id               = $key
        kind             = $svc.kind
        lifecycle        = $svc.lifecycle
        desired_state    = $svc.desired_state
        canonical_path   = $svc.canonical_path
    }

    # 1. 进程存活
    $procs = @()
    if ($svc.process -and $svc.process.entrypoint) {
        $c = $svc.canonical_path; $e = $svc.process.entrypoint
        Get-ServiceProcesses -CanonicalPath $c -Entrypoint $e -CommandMatch @($svc.process.command_match)
        $procs = @($script:__svcproc)
    }
    $alive = ($procs.Count -gt 0)
    $entry.alive = $alive
    $entry.process_count = $procs.Count
    $pidMatch = $false
    $port = $null
    $listeners = $null
    $listenerPid = $null

    if ($alive) {
        $first = $procs[0]
        $entry.pid = [int]$first.ProcessId
        $entry.command_line = $first.CommandLine
        $entry.process_age_sec = Get-ProcessAgeSeconds $first
        $cmdPathPresent = (Normalize-PathString $first.CommandLine).Contains((Normalize-PathString (Join-Path $svc.canonical_path $svc.process.entrypoint)))
        $entry.canonical_path_match = $cmdPathPresent
        $entry.command_match = $true
    } else {
        $entry.pids = @()
        $entry.canonical_path_match = $false
    }

    # 2. 端口监听
    if ($svc.network) {
        $port = [int]$svc.network.port
        $entry.port = $port
        $listeners = @(Get-PortListener -Port $port)
        $entry.port_listening = ($listeners.Count -gt 0)
        if ($entry.port_listening) {
            $listenerPid = $listeners[0].pid
            $entry.listener_pid = $listenerPid
            if ($alive) { $pidMatch = ([int]$listenerPid -eq [int]$entry.pid) }
            $entry.port_owner_match = $pidMatch
        } else {
            $entry.port_owner_match = $false
        }
    }

    # 3. startup grace + 健康
    $graceSec = 0
    if ($svc.healthcheck) { $graceSec = [int]$svc.healthcheck.startup_grace_sec }
    $age = if ($entry.PSObject.Properties.Name -contains 'process_age_sec') { $entry.process_age_sec } else { $null }

    if (-not $alive) {
        $entry.health = 'not_applicable'
        $healthHttp = $null
    } elseif ($age -ne $null -and $age -lt $graceSec) {
        $entry.health = 'starting'
        $healthHttp = $null
    } else {
        if ($svc.healthcheck) {
            $h = Test-HttpHealth -Url $svc.healthcheck.url -TimeoutSec ([int]$svc.healthcheck.timeout_sec)
            $entry.health = if ($h) { $h.status } else { 'not_applicable' }
            if ($h) { $entry.http_status = $h.http_status; $entry.health_error = $h.error }
        } else {
            # orchestrator 无 healthcheck：以存活为准，标注 running
            $entry.health = if ($alive) { 'running' } else { 'not_applicable' }
        }
    }

    # 4. drift 判定
    $reasons = @()
    $ds = $svc.desired_state
    $prt = if ($port) { $entry.port_listening } else { $false }
    switch ("$ds`|$alive`|$prt") {
        'stopped|True|_' { $reasons += 'unexpected_alive' }
        'stopped|False|True' { $reasons += 'orphan_listener' }
        'started|False|_' { $reasons += 'not_running' }
        'started|True|False' {
            if ($entry.health -ne 'starting') { $reasons += 'port_not_listening' }
        }
        'started|True|True' {
            if (-not $pidMatch) { $reasons += 'port_owned_by_other_process' }
            elseif ($entry.health -eq 'unhealthy') { $reasons += 'healthcheck_failed' }
        }
    }
    if ($alive -and $procs.Count -gt 1) { $reasons += 'duplicate_instances' }

    $entry.drift = ($reasons.Count -gt 0)
    $entry.drift_reasons = @($reasons)
    $entry.last_check = $now

    $runtime.services[$key] = $entry

    if ($reasons.Count -gt 0) {
        $driftItems += [ordered]@{
            id      = $key
            reasons = @($reasons)
        }
    }
}

# ------------------------------------------------------------ 写出
$rtFile = Join-Path $OutDir 'gateway_runtime.json'
$drFile = Join-Path $OutDir 'gateway_drift.json'
$runtime | ConvertTo-Json -Depth 10 | Set-Content -Path $rtFile -Encoding UTF8
$drift = @{
    schema_version = 1
    generated_at   = $now
    has_drift      = ($driftItems.Count -gt 0)
    items          = @($driftItems)
}
$drift | ConvertTo-Json -Depth 10 | Set-Content -Path $drFile -Encoding UTF8

Write-Host "已生成: $rtFile"
Write-Host "已生成: $drFile"
Write-Host ""
Write-Host "===== 运行态报告 ====="
foreach ($genEntry in @($runtime.services.GetEnumerator() | Sort-Object Key)) {
    $gen = $genEntry.Value
    $tag = if ($gen.drift) { 'DRIFT' } else { 'ok   ' }
    Write-Host ("[{0}] {1}  state={2,-7} alive={3,-5} port={4,-5} health={5,-13} drift={6}" -f `
        $tag, $gen.id, $gen.desired_state, $gen.alive, $gen.port, $gen.health, ($gen.drift_reasons -join ','))
    if ($gen.drift) { Write-Host ("       reasons: {0}" -f ($gen.drift_reasons -join ', ')) }
}
Write-Host ""
if ($drift.has_drift) { Write-Host "⚠ 存在 $($driftItems.Count) 个漂移项，见 gateway_drift.json" }
else { Write-Host "✓ 无漂移，声明态与运行态一致" }