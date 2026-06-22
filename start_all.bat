@echo off
title BOT Mining Store - Iniciar TODAS las instancias
cd /d "%~dp0"

echo ============================================================
echo   Iniciando las 3 instancias (CFT + ADN + PERSONAL)
echo   Cada una en su propio entorno (sin cruzar cuentas)
echo ============================================================
echo.
echo   IMPORTANTE: el terminal MT5 de ADN debe estar ABIERTO
echo   con "Algo Trading" activado.
echo.

:: Cada .bat corre en su propio cmd (entorno aislado) para no cruzar variables
start "" cmd /c start_bot.bat
timeout /t 6 >nul
start "" cmd /c start_adn.bat
timeout /t 6 >nul
start "" cmd /c start_personal.bat

echo.
echo   Listo. Dashboards:
echo     CFT      -> http://localhost:8090
echo     ADN      -> http://localhost:8100
echo     PERSONAL -> http://localhost:8110
timeout /t 3 >nul
