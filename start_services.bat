@echo off
setlocal enabledelayedexpansion

:: DEPO stack startup script.
:: Starts backend and frontend as separate service windows using the same
:: optional service-boundaries.env manifest.

cd /d "%~dp0"

echo.
echo ================================================================================
echo   DEPO SERVICE STACK STARTUP
echo ================================================================================
echo.
if exist "service-boundaries.env" (
    echo   Runtime manifest: service-boundaries.env
) else (
    echo   Runtime manifest: service-boundaries.env not found; using script defaults
)
echo.

start "DT-Backend" cmd /k call "%~dp0start_backend.bat"
start "DT-Frontend" cmd /k call "%~dp0start_frontend.bat"

echo [OK] Backend and frontend startup windows opened.
echo [INFO] Use stop_services.bat to stop both services.
echo.
endlocal
