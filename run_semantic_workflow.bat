@echo off
setlocal

cd /d "%~dp0"

if not exist "backend\.dt_venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found at backend\.dt_venv
    echo [INFO] Run setup first:
    echo        .\setup.bat --backend
    exit /b 1
)

if "%~1"=="" goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage

set "PYTHONPATH=%CD%"
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py %*
exit /b %errorlevel%

:usage
echo.
echo Backend semantic workflow launcher
echo.
echo Usage:
echo   .\run_semantic_workflow.bat instance-link --ontology-id ONTOLOGY --import-task-id TASK_ID [--apply-links]
echo   .\run_semantic_workflow.bat ontology-merge --source-ontology-id SOURCE --target-ontology-id TARGET
echo   .\run_semantic_workflow.bat ontology-validate --ontology-id ONTOLOGY
echo   .\run_semantic_workflow.bat dictionary-generate --ontology-id ONTOLOGY
echo   .\run_semantic_workflow.bat taxonomy-generate --ontology-id ONTOLOGY
echo   .\run_semantic_workflow.bat graph-chunk --ontology-id ONTOLOGY [--chunk-size 120]
echo.
echo Examples:
echo   .\run_semantic_workflow.bat instance-link --ontology-id plmxmlpdm_1781143225 --import-task-id 6636daef-9b03-4d97-9dbd-c085722984f4
echo   .\run_semantic_workflow.bat ontology-merge --source-ontology-id mbseout_1781143722 --target-ontology-id plmxmlpdm_1781143225
echo.
exit /b 0
