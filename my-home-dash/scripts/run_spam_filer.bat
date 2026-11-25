@echo off
title MHD Spam Auto-Filer
cd /d "%~dp0..\.."
echo Starting spam auto-filer...
.venv\Scripts\python.exe my-home-dash\modules\spam_filer_runner.py my-home-dash\data\filer\task.json my-home-dash\data\filer\status.json my-home-dash\data\filer\continue.flag
echo.
if errorlevel 1 (
    echo ERROR: Filer exited with an error. See above.
) else (
    echo Filing complete.
)
pause
