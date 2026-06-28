@echo off
setlocal enabledelayedexpansion

set "PORT=8000"
set "STOPPED_PIDS="

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

call :collect_listener_pids
if not defined LISTENER_PIDS (
    echo [INFO] Backend service was not running on port %PORT%
    echo.
    goto end
)

echo [INFO] Looking for backend process on port %PORT%...
echo [INFO] Existing listener PID(s): !LISTENER_PIDS!

:: Try to stop any legacy titled backend consoles, but verify the port is actually released.
taskkill /FI "WINDOWTITLE eq DT-Backend*" /T /F >nul 2>&1

for %%P in (%LISTENER_PIDS%) do (
    taskkill /PID %%P /T /F >nul 2>&1
    if not errorlevel 1 (
        set "STOPPED_PIDS=!STOPPED_PIDS! %%P"
    )
)

call :collect_listener_pids
if not defined LISTENER_PIDS (
    if defined STOPPED_PIDS (
        echo [OK] Backend stopped (PID(s): !STOPPED_PIDS!)
    ) else (
        echo [OK] Backend stopped
    )
    echo.
    goto end
)

echo [ERROR] Backend is still listening on port %PORT% (PID(s): !LISTENER_PIDS!)
echo [INFO] Try closing the owning terminal or stopping the process manually.
echo.
exit /b 1

:collect_listener_pids
set "LISTENER_PIDS="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique) -join ' '"`) do set "LISTENER_PIDS=%%P"
goto :eof

:end
echo ════════════════════════════════════════════════════════════════════════════
endlocal
