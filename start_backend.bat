@echo off
setlocal enabledelayedexpansion

:: ────────────────────────────────────────────────────────────────────────────
:: Backend Service Startup Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Start FastAPI backend server on port 8000
:: Location: Project root directory
:: Usage:    .\start_backend.bat [port]
::
:: Examples:
::   .\start_backend.bat          # Start on default port 8000
::   .\start_backend.bat 8080     # Start on port 8080
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
if not "%~1"=="" set "PORT=%~1"

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo   BACKEND SERVICE STARTUP
echo ════════════════════════════════════════════════════════════════════════════
echo.
echo   Port: %PORT%
echo   API Docs: http://localhost:%PORT%/docs
echo   OpenAPI: http://localhost:%PORT%/openapi.json
echo.

:: Check if virtual environment exists
if not exist "backend\.dt_venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at backend\.dt_venv
    echo.
    echo [INFO] Run setup to create it:
    echo        cd backend
    echo        .\setup.bat
    echo.
    exit /b 1
)

echo [1/2] Activating Python virtual environment...
call backend\.dt_venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    exit /b 1
)

echo [2/2] Starting FastAPI server...
echo.
echo ════════════════════════════════════════════════════════════════════════════
set PYTHONPATH=%CD%
python -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% --reload --reload-dir backend --reload-exclude="backend/logs/*" --reload-exclude="ontology_uploads/*" --reload-exclude="uploads/*" --reload-exclude="logs/*" --reload-exclude="data/*"

if errorlevel 1 (
    echo.
    echo [ERROR] Backend server failed to start
    exit /b 1
)

endlocal
