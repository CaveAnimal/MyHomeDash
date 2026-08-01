@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_granite3_3_8b.ps1"
endlocal