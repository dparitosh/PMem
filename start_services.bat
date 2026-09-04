@echo off
setlocal enabledelayedexpansion

:: Legacy development convenience script. Customer/bootstrap deployments use
:: infra\deployment\invoke-depo-lifecycle.ps1 and the production frontend host.
:: Starts backend and frontend as separate service windows using the same
:: optional service-boundaries.env manifest.

cd /d "%~dp0"

echo.
echo ================================================================================
echo   DEPO SERVICE STACK STARTUP
echo ================================================================================
echo.
echo [NOTICE] This script starts the legacy compatibility host for development.
echo [NOTICE] For the supported microservice deployment, run:
echo powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local
echo.
if exist "service-boundaries.env" (
    echo   Runtime manifest: service-boundaries.env
) else (
    echo   Runtime manifest: service-boundaries.env not found; using script defaults
)
echo.

start "DT-Backend" cmd /k call "%~dp0start_backend.bat"
start "DT-Frontend" cmd /k call "%~dp0start_frontend.bat"
start "DT-Agentic" cmd /k call "%~dp0start_agentic.bat"

echo [OK] Backend, frontend, and agentic adapter startup windows opened.
echo [INFO] Use stop_services.bat to stop all services.
echo.
endlocal
