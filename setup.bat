@echo off
setlocal

:: Root setup wrapper for DEPO.
:: Usage: setup.bat [--backend] [--frontend]
:: Delegates to backend\setup.bat, which installs backend and frontend dependencies.

cd /d "%~dp0"

if not exist "backend\setup.bat" (
    echo [ERROR] backend\setup.bat not found. Repository layout is incomplete.
    exit /b 1
)

call "backend\setup.bat" %*
exit /b %ERRORLEVEL%
