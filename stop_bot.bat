@echo off
title Detener BOT BTC
echo Deteniendo BOT BTC Mining Store...

:: Detener todos los procesos pythonw (bot + data_server)
taskkill /f /im pythonw.exe >nul 2>&1

:: Detener servidor dashboard (python -m http.server en puertos 8090 y 8091)
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8090 " 2^>nul') do taskkill /f /pid %%i >nul 2>&1
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8091 " 2^>nul') do taskkill /f /pid %%i >nul 2>&1

echo [OK] Bot y servidores detenidos.
timeout /t 2 >nul
