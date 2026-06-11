@echo off
title BOT BTC Mining Store - Crypto Fund Trader
cd /d "%~dp0"

echo ============================================================
echo   BOT BTC Mining Store ^| Crypto Fund Trader v5b
echo   Iniciando en segundo plano...
echo ============================================================

:: Verificar que Python existe
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado. Instala Python 3.12+
    pause
    exit /b 1
)

:: Iniciar bot en segundo plano (sin ventana visible)
:: El log se guarda en botbtc.log
start /b "" pythonw bot.py

echo Bot iniciado. El log se guarda en botbtc.log
echo Para detener el bot, ejecuta: stop_bot.bat
echo Para ver el log en tiempo real: tail_log.bat
echo.
timeout /t 3 >nul
