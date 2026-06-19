@echo off
setlocal enabledelayedexpansion

:: Backend Service Startup Script
:: Usage: .\start_backend.bat [port] [--reload]
:: Examples:
::   .\start_backend.bat
::   .\start_backend.bat 8080
::   set APP_HOST=192.168.1.50 && .\start_backend.bat
::   set BACKEND_HOST=0.0.0.0 && .\start_backend.bat 8000 --reload

cd /d "%~dp0"

set "PORT=8000"
set "BIND_HOST=%BACKEND_HOST%"
if "%BIND_HOST%"=="" set "BIND_HOST=0.0.0.0"
set "LAN_HOST=%APP_HOST%"
if "%LAN_HOST%"=="" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LAN_HOST=%%I"
)
if "%LAN_HOST%"=="" set "LAN_HOST=localhost"
set "DISPLAY_HOST=%LAN_HOST%"
set "RELOAD_FLAG="

if not "%~1"=="" set "PORT=%~1"
if /I "%~1"=="--reload" (
    set "PORT=8000"
    set "RELOAD_FLAG=--reload --reload-dir backend --reload-exclude=backend/logs/* --reload-exclude=ontology_uploads/* --reload-exclude=uploads/* --reload-exclude=logs/* --reload-exclude=data/*"
)
if /I "%~2"=="--reload" (
    set "RELOAD_FLAG=--reload --reload-dir backend --reload-exclude=backend/logs/* --reload-exclude=ontology_uploads/* --reload-exclude=uploads/* --reload-exclude=logs/* --reload-exclude=data/*"
)

echo.
echo ================================================================================
echo   BACKEND SERVICE STARTUP
echo ================================================================================
echo.
echo   Bind Host: %BIND_HOST%
echo   Port: %PORT%
echo   API Docs: http://%DISPLAY_HOST%:%PORT%/docs
echo   OpenAPI: http://%DISPLAY_HOST%:%PORT%/openapi.json
if defined RELOAD_FLAG (
    echo   Mode: Development reload
) else (
    echo   Mode: Fast start
)
echo.

if not exist "backend\.dt_venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment Python not found at backend\.dt_venv
    echo [INFO] Run: cd backend ^&^& .\setup.bat
    exit /b 1
)

set "EXISTING_BACKEND_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "EXISTING_BACKEND_PID=%%P"
)

if not "%EXISTING_BACKEND_PID%"=="" (
    echo [INFO] Backend already appears to be running on port %PORT%.
    echo [INFO] Existing listener PID: %EXISTING_BACKEND_PID%
    echo [INFO] API Docs: http://%DISPLAY_HOST%:%PORT%/docs
    echo [INFO] Health:   http://%DISPLAY_HOST%:%PORT%/health
    echo.
    echo [INFO] To restart it, run:
    echo        .\stop_backend.bat
    echo        .\start_backend.bat %PORT%
    exit /b 0
)

set "PYTHONPATH=%CD%"
call backend\.dt_venv\Scripts\python.exe -m uvicorn backend.main:app --host %BIND_HOST% --port %PORT% %RELOAD_FLAG%
if errorlevel 1 (
    echo [ERROR] Backend server failed to start.
    exit /b 1
)