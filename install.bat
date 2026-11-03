@echo off
rem MAKER-Rebuild - instalador para Windows (atalho para install.ps1).
rem   install.bat                 instala (executavel pronto; se nao houver, via Python)
rem   install.bat --exe | --python | --from-local | --uninstall | --dry-run | --prefix DIR | --version X.Y.Z
setlocal EnableDelayedExpansion
set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"
set "ARGS="
:loop
if "%~1"=="" goto run
set "A=%~1"
if /i "!A!"=="--exe" goto a_exe
if /i "!A!"=="--python" goto a_python
if /i "!A!"=="--from-local" goto a_local
if /i "!A!"=="--uninstall" goto a_uninstall
if /i "!A!"=="--dry-run" goto a_dry
if /i "!A!"=="--prefix" goto a_prefix
if /i "!A!"=="--version" goto a_version
set "ARGS=!ARGS! %1"
shift
goto loop
:a_exe
set "ARGS=!ARGS! -Mode exe"
shift
goto loop
:a_python
set "ARGS=!ARGS! -Mode python"
shift
goto loop
:a_local
set "ARGS=!ARGS! -FromLocal"
shift
goto loop
:a_uninstall
set "ARGS=!ARGS! -Uninstall"
shift
goto loop
:a_dry
set "ARGS=!ARGS! -DryRun"
shift
goto loop
:a_prefix
set "ARGS=!ARGS! -Prefix "%~2""
shift
shift
goto loop
:a_version
set "ARGS=!ARGS! -Version %~2"
shift
shift
goto loop
:run
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" !ARGS!
exit /b %ERRORLEVEL%
