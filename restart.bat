@echo off
setlocal
chcp 65001 >nul 2>&1
title Werewolf Ville - Restart

set "ROOT=%~dp0"
set "PYTHON=C:\Users\XD\AppData\Local\Programs\Python\Python310\python.exe"
set "PORT=5000"
set "STDOUT=%ROOT%server.stdout.log"
set "STDERR=%ROOT%server.stderr.log"
set "PIDFILE=%ROOT%server.pid"

cd /d "%ROOT%"

echo ========================================
echo  Werewolf Ville - Restart
echo ========================================
echo.
echo [1/3] Stopping the game service on port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Stopping game server PID %%P...
    taskkill /PID %%P /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo [2/3] Starting server...
echo Chat2API and unrelated Python processes will not be stopped.
del /Q "%STDOUT%" "%STDERR%" >nul 2>&1
start "Werewolf Ville Server" /min cmd /c ""%PYTHON%" -u main.py 1>"%STDOUT%" 2>"%STDERR%""
if errorlevel 1 goto :failed

echo [3/3] Checking http://127.0.0.1:%PORT%/ ...
timeout /t 2 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/' -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 goto :failed

echo.
echo Server is running: http://127.0.0.1:%PORT%/
echo Error log: %STDERR%
echo.
pause
exit /b 0

:failed
echo.
echo ERROR: Server did not start or did not respond.
echo Error log: %STDERR%
if exist "%STDERR%" (
    echo ----------------------------------------
    type "%STDERR%"
    echo ----------------------------------------
)
pause
exit /b 1
