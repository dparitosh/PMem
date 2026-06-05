@echo off
setlocal enabledelayedexpansion

:: ────────────────────────────────────────────────────────────────────────────
:: Frontend Service Stop Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Stop the React frontend dev server
:: Location: Project root directory
:: Usage:    .\stop_frontend.bat
::
:: This script:
::   - Finds and terminates Node.js process running on port 3000
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

:: If no named window, try to kill Node processes on port 3000
echo [INFO] Looking for Node.js processes on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000"') do (
    set "PID=%%a"
    taskkill /PID !PID! /F >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Frontend stopped (PID: !PID!)
        echo.
        goto end
    )
)

echo [INFO] Frontend service was not running
echo.

:end
echo ════════════════════════════════════════════════════════════════════════════
endlocal
