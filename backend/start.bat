@echo off
setlocal enabledelayedexpansion

:: ──── DT Project Start ────────────────────────────────────────────────────
:: Usage: start.bat [--backend] [--frontend]
::   No flags = start both backend and frontend
:: Each service runs in its own named window so stop.bat can find it.
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

set "BACKEND_ROOT=%~dp0"
for %%I in ("%BACKEND_ROOT%..") do set "PROJECT_ROOT=%%~fI\"

:: ──── Start Backend ───────────────────────────────────────────────────────
if not "%DO_BACKEND%"=="1" goto :skip_backend

echo Starting backend (FastAPI / uvicorn) ...
if not exist "%BACKEND_ROOT%.dt_venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    exit /b 1
)

start "DT-Backend" cmd /k "cd /d %BACKEND_ROOT% && call %BACKEND_ROOT%.dt_venv\Scripts\activate.bat && set PYTHONPATH=%BACKEND_ROOT% && python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --timeout-keep-alive 180"
echo   Backend window opened (title: DT-Backend).

:skip_backend

:: ──── Start Frontend ──────────────────────────────────────────────────────
if not "%DO_FRONTEND%"=="1" goto :skip_frontend

echo Starting frontend (React dev server) ...
if not exist "%PROJECT_ROOT%frontend\node_modules\react-scripts\bin\react-scripts.js" (
    echo ERROR: Frontend dependencies not found. Run setup.bat --frontend first.
    exit /b 1
)

start "DT-Frontend" cmd /k "cd /d %PROJECT_ROOT%frontend && set BROWSER=none && node node_modules\react-scripts\bin\react-scripts.js start"
echo   Frontend window opened (title: DT-Frontend).

:skip_frontend

echo.
echo Services launched. Use stop.bat to shut them down.
endlocal
