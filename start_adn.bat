@echo off
title BOT Mining Store - Instancia ADN (MT5)
cd /d "%~dp0"

:: Instancia ADN: carpeta de datos, puertos y log propios (no choca con la de CFT)
set MS_INSTANCE=adn
set MS_DATA_DIR=data_adn
set MS_PORT_OFFSET=10
set MS_LOG_FILE=botadn.log

echo ============================================================
echo   Instancia ADN (MT5)  ^|  puertos 8100/8101/8102  ^|  data_adn\
echo   Requiere el terminal MT5 de ADN abierto y Algo Trading ON
echo ============================================================

start /b "" pythonw app.py
timeout /t 3 >nul
start http://localhost:8102/
echo.
echo Setup/estado: http://localhost:8102   Dashboard: http://localhost:8100
echo Log: botadn.log   ^|  Para detener: stop_bot.bat (cierra todas las instancias)
