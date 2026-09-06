@echo off
rem ===== SearchGateway watchdog - keeps :3100 api_gateway and :3000 search_gateway alive =====
:loop
rem check :3100 api gateway
netstat -ano -p tcp | findstr ":3100" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] :3100 not listening, restarting SearchGateway
    schtasks /Run /TN "SearchGateway" >nul 2>&1
)
rem check :3000 search gateway
netstat -ano -p tcp | findstr ":3000" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] :3000 not listening, respawning search gateway
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& (Get-Item 'D:\*\ai-hub\search_gateway\services\start_search_gateway_3000.ps1').FullName"
)
timeout /t 30 /nobreak >nul 2>&1
goto loop
