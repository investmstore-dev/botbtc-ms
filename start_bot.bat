@echo off
title BOT Mining Store - Instancia CFT (Bybit)
cd /d "%~dp0"

:: Instancia CFT = instancia por defecto (data/, puertos 8090/8091/8092)
:: (limpia cualquier variable de instancia heredada para no cruzar cuentas)
set "MS_INSTANCE="
set "MS_DATA_DIR="
set "MS_PORT_OFFSET="
set "MS_LOG_FILE="
set "MS_ENTRY_END="

echo ============================================================
echo   Instancia CFT (Bybit)  ^|  puertos 8090/8091/8092  ^|  data\
echo ============================================================

start /b "" pythonw app.py
timeout /t 3 >nul
start http://localhost:8090/index.html
echo.
echo Dashboard: http://localhost:8090   Setup: http://localhost:8092
echo Log: botbtc.log
