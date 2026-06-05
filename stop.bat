@echo off
pushd "%~dp0backend"
call ".\stop.bat" %*
set "SCRIPT_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SCRIPT_EXIT_CODE%
