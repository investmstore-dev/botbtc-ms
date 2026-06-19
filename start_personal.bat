@echo off
title BOT Mining Store - Instancia PERSONAL (Bybit x10)
cd /d "%~dp0"

:: Instancia personal: carpeta, puertos y log propios (no choca con CFT ni ADN)
set MS_INSTANCE=personal
set MS_DATA_DIR=data_personal
set MS_PORT_OFFSET=20
set MS_LOG_FILE=botpersonal.log

echo ============================================================
echo   Instancia PERSONAL (Bybit x10, libre/compounding)
echo   puertos 8110/8111/8112  ^|  data_personal\
echo ============================================================

start /b "" pythonw app.py
timeout /t 3 >nul
start http://localhost:8112/
echo.
echo Setup (ingresa tu API key/secret): http://localhost:8112
echo Dashboard: http://localhost:8110   Log: botpersonal.log
