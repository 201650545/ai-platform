# start_api_gateway_3100.ps1 — spawn :3100 API forwarding gateway detached.
# Same pattern as start_search_gateway_3000.ps1: WMI Win32_Process.Create parents to
# WmiPrvSE so the process survives the caller's session/job closing.
$wd = $PSScriptRoot
$py  = 'C:\Users\郭永涛\AppData\Local\Programs\Python\Python312\python.exe'
$existing = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'api_gateway\.py' }
if ($existing) { Write-Output "already running PID $($existing.ProcessId)"; return }
$cmd = 'cmd /c cd /d "' + $wd + '" && "' + $py + '" api_gateway.py >> "' + $wd + '\_run_3100_api.log" 2>&1'
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd } | Out-Null
Write-Output "spawned api_gateway detached"