@echo off
pushd "%~dp0backend"
call ".\setup.bat" %*
set "SCRIPT_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SCRIPT_EXIT_CODE%
