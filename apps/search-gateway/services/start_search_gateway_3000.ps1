# start_search_gateway_3000.ps1 — spawn :3000 search gateway detached from any job
# Called by: Startup folder bat (logon) and watchdog_gateway.bat :3000 branch (auto-heal).
# WMI Win32_Process.Create parents the process to WmiPrvSE so it survives the
# caller's session/job closing — the root cause of the gateway dying silently.
$wd = 'D:\项目\ai-hub\search_gateway\services'
$py = 'C:\Users\郭永涛\AppData\Local\Programs\Python\Python312\python.exe'
# guard: engine warmup takes minutes before :3000 binds, so never spawn twice
$existing = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'search_gateway\.py' }
if ($existing) { return }
$cmd = 'cmd /c cd /d "' + $wd + '" && "' + $py + '" search_gateway.py >> _run_3000_task.log 2>&1'
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd } | Out-Null
