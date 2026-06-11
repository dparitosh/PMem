@echo off
setlocal enabledelayedexpansion

:: ────────────────────────────────────────────────────────────────────────────
:: Backend Service Startup Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Start FastAPI backend server on port 8000
:: Location: Project root directory
:: Usage:    .\start_backend.bat [port] [--reload]
::
:: Examples:
::   .\start_backend.bat                # Start fast on default port 8000
::   .\start_backend.bat 8080           # Start fast on port 8080
::   .\start_backend.bat 8000 --reload  # Start with file watching
::
:: Dependencies:
::   - Python 3.11+
::   - Virtual environment at backend/.dt_venv
::   - requirements.txt installed
:: ────────────────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0"

:: Parse command line arguments
set "PORT=8000"
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
echo ════════════════════════════════════════════════════════════════════════════
echo   BACKEND SERVICE STARTUP
echo ════════════════════════════════════════════════════════════════════════════
echo.
echo   Port: %PORT%
echo   API Docs: http://localhost:%PORT%/docs
echo   OpenAPI: http://localhost:%PORT%/openapi.json
if defined RELOAD_FLAG (
    echo   Mode: Development reload
) else (
    echo   Mode: Fast start
)
echo.

:: Check if virtual environment exists
if not exist "backend\.dt_venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment Python not found at backend\.dt_venv
    echo.
    echo [INFO] Run setup to create it:
    echo        cd backend
    echo        .\setup.bat
    echo.
    exit /b 1
)

echo [1/1] Starting FastAPI server...
echo.
echo ════════════════════════════════════════════════════════════════════════════
set PYTHONPATH=%CD%
call backend\.dt_venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% %RELOAD_FLAG%

if errorlevel 1 (
    echo.
    echo [ERROR] Backend server failed to start
    exit /b 1
)

endlocal
