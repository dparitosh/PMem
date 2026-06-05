@echo off
setlocal enabledelayedexpansion

:: ──── DT Project Stop ─────────────────────────────────────────────────────
:: Usage: stop.bat [--backend] [--frontend]
::   No flags = stop both backend and frontend
:: Stops services by closing the named console windows opened by start.bat.
:: ───────────────────────────────────────────────────────────────────────────

set "DO_BACKEND=0"
set "DO_FRONTEND=0"
set "ANY_FLAG=0"

:parse_args
if "%~1"=="" goto :check_flags
if /i "%~1"=="--backend"  (set "DO_BACKEND=1" & set "ANY_FLAG=1")
if /i "%~1"=="--frontend" (set "DO_FRONTEND=1" & set "ANY_FLAG=1")
shift
goto :parse_args

:check_flags
if "%ANY_FLAG%"=="0" (
    set "DO_BACKEND=1"
    set "DO_FRONTEND=1"
)

:: ──── Stop Backend ────────────────────────────────────────────────────────
if "%DO_BACKEND%"=="1" (
    echo Stopping backend ...
    taskkill /FI "WINDOWTITLE eq DT-Backend*" /T /F >nul 2>&1
    if errorlevel 1 (
        echo   Backend was not running.
    ) else (
        echo   Backend stopped.
    )
)

:: ──── Stop Frontend ───────────────────────────────────────────────────────
if "%DO_FRONTEND%"=="1" (
    echo Stopping frontend ...
    taskkill /FI "WINDOWTITLE eq DT-Frontend*" /T /F >nul 2>&1
    if errorlevel 1 (
        echo   Frontend was not running.
    ) else (
        echo   Frontend stopped.
    )
)

echo.
echo Done.
endlocal
