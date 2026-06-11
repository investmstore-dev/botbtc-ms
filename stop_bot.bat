@echo off
title Detener BOT BTC
echo Deteniendo BOT BTC Mining Store...
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq BOT BTC*" >nul 2>&1
taskkill /f /im python.exe /fi "COMMANDLINE eq *bot.py*" >nul 2>&1
:: Matar por nombre de proceso asociado a bot.py
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq pythonw.exe" /fo csv /nh 2^>nul') do (
    wmic process where "ProcessId=%%~i" get commandline 2>nul | find "bot.py" >nul && taskkill /f /pid %%~i >nul 2>&1
)
echo Bot detenido.
timeout /t 2 >nul
