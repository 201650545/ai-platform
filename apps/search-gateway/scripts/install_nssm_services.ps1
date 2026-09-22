# install_nssm_services.ps1 — 网关(:3100)+web2api(:3102) NSSM 化（2026-09-22）
# 自提权运行；NSSM = D:\Tools\nssm\nssm.exe
$ErrorActionPreference = 'Stop'
Start-Transcript -Path 'D:\项目\ai-hub\search_gateway\scripts\_nssm_install.log' -Force

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
      ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $PSCommandPath)
    exit
}

$nssm = 'D:\Tools\nssm\nssm.exe'
$py   = 'C:\Users\郭永涛\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe'
$svc  = 'D:\项目\ai-hub\search_gateway\services'
$log  = 'D:\项目\ai-hub\search_gateway\services\_nssm_logs'
New-Item -ItemType Directory -Force $log | Out-Null

# 清掉先前误弹的 nssm GUI（提权态可杀）
Get-Process nssm -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 停掉手动拉起的旧进程（服务接管前）
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'api_gateway\.py|web2api\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

function Install-Svc($name, $script) {
    if (Get-Service $name -ErrorAction SilentlyContinue) {
        & $nssm stop $name | Out-Null
        & $nssm remove $name confirm | Out-Null
    }
    & $nssm install $name $py $script | Out-Null
    & $nssm set $name AppDirectory $svc | Out-Null
    & $nssm set $name Start SERVICE_AUTO_START | Out-Null
    & $nssm set $name AppStdout "$log\$name.out.log" | Out-Null
    & $nssm set $name AppStderr "$log\$name.err.log" | Out-Null
    & $nssm set $name AppRotateFiles 1 | Out-Null
    & $nssm set $name AppRotateOnline 1 | Out-Null
    & $nssm set $name AppRotateBytes 10485760 | Out-Null
    & $nssm set $name AppExit Default Restart | Out-Null
    & $nssm set $name AppRestartDelay 3000 | Out-Null
    & $nssm start $name | Out-Null
    Write-Output "installed+started: $name"
}

# 清掉历史遗留的旧 NSSM 服务（旧路径 .tools\nssm、已停，用途相同留着混淆）
if (Get-Service API3100Gateway -ErrorAction SilentlyContinue) {
    & $nssm stop API3100Gateway | Out-Null
    & $nssm remove API3100Gateway confirm | Out-Null
    Write-Output 'removed legacy service API3100Gateway'
}

Install-Svc 'ai-gateway-3100' 'api_gateway.py'
Install-Svc 'web2api-3102' 'web2api.py'

Start-Sleep -Seconds 6
Write-Output '--- listen check ---'
(netstat -ano | findstr ':3100 :3102') -split "`n" | ForEach-Object { $_.Trim() }
Write-Output '--- service status ---'
& $nssm status ai-gateway-3100
& $nssm status web2api-3102
Write-Output 'DONE'
Stop-Transcript
