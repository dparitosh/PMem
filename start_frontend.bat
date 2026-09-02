@echo off
setlocal enabledelayedexpansion

:: Frontend Service Startup Script (Vite)
:: Usage: .\start_frontend.bat [port] [backend_url] [host]
:: Examples:
::   .\start_frontend.bat
::   .\start_frontend.bat 3001
::   set APP_HOST=192.168.1.50 && .\start_frontend.bat
::   .\start_frontend.bat 3000 http://192.168.1.50:8000 0.0.0.0

cd /d "%~dp0"

if exist "service-boundaries.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("service-boundaries.env") do (
        set "LINE=%%A"
        if not "!LINE!"=="" if /I not "!LINE:~0,1!"=="#" set "%%A=%%B"
    )
)

set "PORT=%FRONTEND_PORT%"
if "%PORT%"=="" set "PORT=3000"
set "LAN_HOST=%APP_HOST%"
if "%LAN_HOST%"=="" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LAN_HOST=%%I"
)
if "%LAN_HOST%"=="" set "LAN_HOST=localhost"

set "BACKEND_URL=%REACT_APP_BACKEND_URL%"
if "%BACKEND_URL%"=="" set "BACKEND_URL=http://127.0.0.1:8000"
set "HOST=%FRONTEND_HOST%"
if "%HOST%"=="" set "HOST=0.0.0.0"
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

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 20 LTS or newer.
    exit /b 1
)

for /f "usebackq delims=" %%N in (`node -p "process.versions.node.split('.')[0]"`) do set "NODE_MAJOR=%%N"
if "!NODE_MAJOR!"=="" (
    echo [ERROR] Unable to detect Node.js version. Please install Node.js 20 LTS or newer.
    exit /b 1
)
if !NODE_MAJOR! LSS 20 (
    echo [ERROR] Node.js 20 LTS or newer is required. Detected Node.js major version !NODE_MAJOR!.
    echo [INFO] Install Node.js 20 LTS, then run: cd frontend ^&^& npm install
    exit /b 1
)
echo [INFO] Node.js major version !NODE_MAJOR! detected.

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Please install Node.js 20 LTS or newer.
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] node_modules not found in frontend/.
    echo [INFO] Run: cd frontend ^&^& npm install
    exit /b 1
)

if not exist "frontend\node_modules\.bin\vite.cmd" (
    echo [ERROR] Local Vite executable not found in frontend\node_modules.
    echo [INFO] Run: cd frontend ^&^& npm install
    exit /b 1
)

cd /d "%~dp0frontend"
set "PORT=%PORT%"
set "HOST=%HOST%"
set "FRONTEND_HOST=%HOST%"
set "FRONTEND_PORT=%PORT%"
set "VITE_BACKEND_URL=%BACKEND_URL%"
set "BROWSER=none"

call npm.cmd run dev -- --host %HOST% --port %PORT%
if errorlevel 1 (
    echo [ERROR] Frontend dev server failed to start.
    exit /b 1
)
