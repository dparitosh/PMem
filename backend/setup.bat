@echo off
setlocal enabledelayedexpansion

:: ──── DT Project Setup ────────────────────────────────────────────────────
:: Usage: setup.bat [--backend] [--frontend]
::   No flags = setup both backend and frontend
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

:: ──── Backend Setup ───────────────────────────────────────────────────────
if "%DO_BACKEND%"=="1" (
    echo.
    echo ============================================================
    echo   Backend Setup
    echo ============================================================
    echo.

    if exist "%BACKEND_ROOT%.dt_venv\Scripts\python.exe" (
        "%BACKEND_ROOT%.dt_venv\Scripts\python.exe" --version >nul 2>&1
        if errorlevel 1 (
            echo [1/3] Existing virtual environment is broken. Recreating .dt_venv ...
            rmdir /s /q "%BACKEND_ROOT%.dt_venv"
        )
    )

    if not exist "%BACKEND_ROOT%.dt_venv\Scripts\activate.bat" (
        echo [1/3] Creating Python virtual environment .dt_venv ...
        python -m venv "%BACKEND_ROOT%.dt_venv"
        if errorlevel 1 (
            echo ERROR: Failed to create virtual environment. Is Python installed?
            exit /b 1
        )
    ) else (
        echo [1/3] Virtual environment .dt_venv already exists — skipping creation.
    )

    echo [2/3] Activating virtual environment ...
    call "%BACKEND_ROOT%.dt_venv\Scripts\activate.bat"

    echo [3/3] Installing backend dependencies ...
    pip install -r "%BACKEND_ROOT%backend\requirements.txt" --quiet
    if errorlevel 1 (
        echo ERROR: pip install failed.
        exit /b 1
    )

    echo.
    echo   Backend setup complete.
    echo.
)

:: ──── Frontend Setup ──────────────────────────────────────────────────────
if "%DO_FRONTEND%"=="1" (
    echo.
    echo ============================================================
    echo   Frontend Setup
    echo ============================================================
    echo.

    where npm >nul 2>&1
    if errorlevel 1 (
        echo ERROR: npm not found. Please install Node.js first.
        exit /b 1
    )

    echo [1/1] Installing frontend dependencies ...
    pushd "%PROJECT_ROOT%frontend"
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed.
        popd
        exit /b 1
    )
    popd

    echo.
    echo   Frontend setup complete.
    echo.
)

echo ============================================================
echo   Setup finished successfully!
echo ============================================================
endlocal
