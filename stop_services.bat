@echo off
setlocal enabledelayedexpansion

:: DEPO stack stop script.
:: Stops frontend and backend using their service-specific stop scripts.

cd /d "%~dp0"

echo.
echo ================================================================================
echo   DEPO SERVICE STACK STOP
echo ================================================================================
echo.

call "%~dp0stop_frontend.bat"
if errorlevel 1 (
    echo [WARN] Frontend stop reported an issue.
)

call "%~dp0stop_backend.bat"
if errorlevel 1 (
    echo [WARN] Backend stop reported an issue.
)

call "%~dp0stop_agentic.bat"

echo.
echo [OK] Stop sequence completed.
echo.
endlocal
