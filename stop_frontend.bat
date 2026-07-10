@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if exist "service-boundaries.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("service-boundaries.env") do (
        set "LINE=%%A"
        if not "!LINE!"=="" if /I not "!LINE:~0,1!"=="#" set "%%A=%%B"
    )
)

set "PORT=%FRONTEND_PORT%"
if "%PORT%"=="" set "PORT=3000"

:: ────────────────────────────────────────────────────────────────────────────
:: Frontend Service Stop Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Stop the React frontend dev server
:: Location: Project root directory
:: Usage:    .\stop_frontend.bat
::
:: This script:
::   - Finds and terminates Node.js process running on the configured frontend port
::   - Gracefully shuts down the frontend service
:: ────────────────────────────────────────────────────────────────────────────

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo   FRONTEND SERVICE STOP
echo ════════════════════════════════════════════════════════════════════════════
echo.

:: Try to stop via named window first (from start.bat)
taskkill /FI "WINDOWTITLE eq DT-Frontend*" /T /F >nul 2>&1
if not errorlevel 1 (
    echo [OK] Frontend stopped (named window: DT-Frontend)
    echo.
    goto end
)

:: If no named window, try to kill Node processes on the configured port
echo [INFO] Looking for Node.js processes on port %PORT%...
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique) -join ' '"`) do set "LISTENER_PIDS=%%P"

for %%P in (%LISTENER_PIDS%) do (
    taskkill /PID %%P /T /F >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Frontend stopped (PID: %%P)
        echo.
        goto end
    )
)

echo [INFO] Frontend service was not running
echo.

:end
echo ════════════════════════════════════════════════════════════════════════════
endlocal
