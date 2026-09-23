$ErrorActionPreference = 'Stop'
Start-Transcript -Path 'D:\项目\ai-hub\search_gateway\scripts\_nssm_restart.log' -Force
& 'D:\Tools\nssm\nssm.exe' restart ai-gateway-3100
& 'D:\Tools\nssm\nssm.exe' restart web2api-3102
Start-Sleep -Seconds 5
& 'D:\Tools\nssm\nssm.exe' status ai-gateway-3100
& 'D:\Tools\nssm\nssm.exe' status web2api-3102
Stop-Transcript
