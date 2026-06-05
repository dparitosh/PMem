@echo off
setlocal enabledelayedexpansion

:: ────────────────────────────────────────────────────────────────────────────
:: Backend Service Stop Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Stop the FastAPI backend server
:: Location: Project root directory
:: Usage:    .\stop_backend.bat
::
:: This script:
::   - Finds and terminates Python uvicorn process running on port 8000
::   - Gracefully shuts down the backend service
:: ────────────────────────────────────────────────────────────────────────────

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo   BACKEND SERVICE STOP
echo ════════════════════════════════════════════════════════════════════════════
echo.

:: Try to stop via named window first (from start.bat)
taskkill /FI "WINDOWTITLE eq DT-Backend*" /T /F >nul 2>&1
if not errorlevel 1 (
    echo [OK] Backend stopped (named window: DT-Backend)
    echo.
    goto end
)

:: If no named window, try to kill Python processes on port 8000
echo [INFO] Looking for Python processes on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
    set "PID=%%a"
    taskkill /PID !PID! /F >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Backend stopped (PID: !PID!)
        echo.
        goto end
    )
)

echo [INFO] Backend service was not running
echo.

:end
echo ════════════════════════════════════════════════════════════════════════════
endlocal
