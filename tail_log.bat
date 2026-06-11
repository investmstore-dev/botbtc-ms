@echo off
title Log BOT BTC - Mining Store
cd /d "%~dp0"
echo Mostrando log en tiempo real (Ctrl+C para salir)...
echo ============================================================
powershell -command "Get-Content botbtc.log -Wait -Tail 30"
