@echo off
setlocal enabledelayedexpansion

:: Frontend Service Startup Script
:: Usage: .\start_frontend.bat [port] [backend_url] [host]
:: Examples:
::   .\start_frontend.bat
::   .\start_frontend.bat 3001
::   set APP_HOST=192.168.1.50 && .\start_frontend.bat
::   .\start_frontend.bat 3000 http://192.168.1.50:8000 0.0.0.0

cd /d "%~dp0"

set "PORT=3000"
set "LAN_HOST=%APP_HOST%"
if "%LAN_HOST%"=="" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LAN_HOST=%%I"
)
if "%LAN_HOST%"=="" set "LAN_HOST=localhost"

set "BACKEND_URL=http://%LAN_HOST%:8000"
set "HOST=0.0.0.0"
set "DISPLAY_HOST=%LAN_HOST%"

if not "%~1"=="" set "PORT=%~1"
if not "%~2"=="" set "BACKEND_URL=%~2"
if not "%~3"=="" set "HOST=%~3"
if /I "%HOST%"=="0.0.0.0" set "DISPLAY_HOST=%LAN_HOST%"
if /I not "%HOST%"=="0.0.0.0" set "DISPLAY_HOST=%HOST%"

echo.
echo ================================================================================
echo   FRONTEND SERVICE STARTUP
echo ================================================================================
echo.
echo   Port: %PORT%
echo   Bind Host: %HOST%
echo   URL: http://%DISPLAY_HOST%:%PORT%
echo   Backend URL: %BACKEND_URL%
echo.

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Please install Node.js first.
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] node_modules not found in frontend/.
    echo [INFO] Run: cd frontend ^&^& npm install
    exit /b 1
)

if not exist "frontend\node_modules\react-scripts\bin\react-scripts.js" (
    echo [ERROR] Local react-scripts not found in frontend\node_modules.
    echo [INFO] Run: cd frontend ^&^& npm install
    exit /b 1
)

cd /d "%~dp0frontend"
set "PORT=%PORT%"
set "HOST=%HOST%"
set "REACT_APP_BACKEND_URL=%BACKEND_URL%"
set "BROWSER=none"
set "FAST_REFRESH=true"

call "node_modules\.bin\react-scripts.cmd" start
if errorlevel 1 (
    echo [ERROR] Frontend dev server failed to start.
    exit /b 1
)