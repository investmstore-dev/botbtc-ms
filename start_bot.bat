@echo off
title BOT BTC Mining Store - Crypto Fund Trader
cd /d "%~dp0"

echo ============================================================
echo   BOT BTC Mining Store ^| Crypto Fund Trader v5b
echo ============================================================

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado.
    pause & exit /b 1
)

:: 1. Bot principal (sin ventana)
start /b "" pythonw -m logic.bot
echo [OK] Bot iniciado en segundo plano

:: 2. Servidor de datos para el dashboard (puerto 8091, con CORS)
start /b "" pythonw -m utils.data_server
echo [OK] Servidor de datos iniciado en http://localhost:8091

:: 3. Dashboard (puerto 8090)
start /b "" python -m http.server 8090 --directory "..\botbtc-dashboard-ms"
echo [OK] Dashboard iniciado en http://localhost:8090

:: Esperar 2 segundos y abrir el dashboard en el navegador
timeout /t 2 >nul
start http://localhost:8090/index.html

echo.
echo Todo corriendo. Para detener: ejecuta stop_bot.bat
echo Log del bot: tail_log.bat
