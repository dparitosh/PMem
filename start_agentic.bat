@echo off
setlocal

cd /d "%~dp0standalone\ontology_agentic_service"
if not exist "%~dp0backend\.dt_venv\Scripts\python.exe" (
  echo [ERROR] Backend Python runtime not found.
  echo [INFO] Start the agentic adapter with an activated Python environment instead.
  exit /b 1
)

echo Starting ontology agentic component adapter on port 8012...
"%~dp0backend\.dt_venv\Scripts\python.exe" start_service.py
endlocal
