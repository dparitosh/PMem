@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0infra\windows\setup-depo.ps1" %*
set "setupExit=%ERRORLEVEL%"
if not "%setupExit%"=="0" echo Setup stopped. Correct the reported problem and double-click this file again to resume.
pause
exit /b %setupExit%
