@echo off
title Build BOT Mining Store .exe
cd /d "%~dp0"

echo ============================================================
echo   Empaquetando BOT Mining Store en un .exe
echo ============================================================

where python >nul 2>&1
if errorlevel 1 ( echo ERROR: Python no encontrado. & pause & exit /b 1 )

echo.
echo [1/3] Instalando dependencias...
pip install -r requirements.txt pyinstaller >nul

echo [2/3] Copiando dashboard a web\dashboard...
if exist "..\botbtc-dashboard-ms" (
    if exist "web\dashboard" rmdir /s /q "web\dashboard"
    xcopy /e /i /y "..\botbtc-dashboard-ms" "web\dashboard" >nul
    echo     dashboard copiado.
) else (
    echo     ADVERTENCIA: no se encontro ..\botbtc-dashboard-ms (dashboard no se empaquetara^)
)

echo [3/3] Ejecutando PyInstaller...
pyinstaller --clean -y BotMiningStore.spec

echo.
echo ============================================================
echo   Listo: dist\BotMiningStore.exe
echo   Copia ese .exe (junto a un archivo .env opcional) al otro PC.
echo ============================================================
pause
