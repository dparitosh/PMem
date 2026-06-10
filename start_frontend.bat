@echo off
setlocal enabledelayedexpansion

:: ────────────────────────────────────────────────────────────────────────────
:: Frontend Service Startup Script
:: ────────────────────────────────────────────────────────────────────────────
:: Purpose: Start React frontend dev server on port 3000
:: Location: Project root directory
:: Usage:    .\start_frontend.bat [port]
::
:: Examples:
::   .\start_frontend.bat          # Start on default port 3000
::   .\start_frontend.bat 3001     # Start on port 3001
::
:: Dependencies:
::   - Node.js 18+ and npm
::   - node_modules installed in frontend/
::   - package.json with npm scripts
:: ────────────────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0"

:: Parse command line arguments
set "PORT=3000"
if not "%~1"=="" set "PORT=%~1"

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo   FRONTEND SERVICE STARTUP
echo ════════════════════════════════════════════════════════════════════════════
echo.
echo   Port: %PORT%
echo   URL: http://localhost:%PORT%
echo.

:: Check if Node.js is installed
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Please install Node.js first.
    echo.
    echo [INFO] Download Node.js from: https://nodejs.org/
    echo.
    exit /b 1
)

:: Check if node_modules exists
if not exist "frontend\node_modules" (
    echo [WARNING] node_modules not found in frontend/
    echo.
    echo [INFO] Run setup to install dependencies:
    echo        cd backend
    echo        .\setup.bat --frontend
    echo.
    echo [INFO] Or install manually:
    echo        cd frontend
    echo        npm install
    echo.
    exit /b 1
)

:: Check if react-scripts is installed locally
if not exist "frontend\node_modules\react-scripts\bin\react-scripts.js" (
    echo [ERROR] Local react-scripts not found in frontend\node_modules
    echo.
    echo [INFO] Dependencies look incomplete. Repair with:
    echo        cd frontend
    echo        npm install
    echo.
    exit /b 1
)

echo [1/2] Verifying npm installation...
for /f "tokens=*" %%i in ('npm.cmd --version') do set "NPM_VERSION=%%i"
echo        npm version: %NPM_VERSION%

echo [2/2] Starting React development server...
echo.
echo ════════════════════════════════════════════════════════════════════════════

cd /d "%~dp0frontend"
set "PORT=%PORT%"
set "REACT_APP_BACKEND_URL=http://localhost:8000"

if exist "node_modules\.bin\react-scripts.cmd" (
    call "node_modules\.bin\react-scripts.cmd" start
) else (
    call npm.cmd start
)

if errorlevel 1 (
    echo.
    echo [ERROR] Frontend dev server failed to start
    exit /b 1
)

endlocal
