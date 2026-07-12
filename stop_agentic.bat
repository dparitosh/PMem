@echo off
setlocal

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8012" ^| findstr "LISTENING"') do (
  taskkill /PID %%P /F >nul 2>&1
)
echo Agentic adapter stop sequence completed.
endlocal
