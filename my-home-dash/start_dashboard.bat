@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  My Home Dash — Launcher
REM  Double-click this file OR point Windows Task Scheduler at it.
REM  It activates the venv and starts the Flask server.
REM ─────────────────────────────────────────────────────────────────────────

SET "PROJ_DIR=%~dp0"
cd /d "%PROJ_DIR%"

REM Activate the virtual environment
call "%PROJ_DIR%venv\Scripts\activate.bat"

REM Start the dashboard (runs until the window is closed)
python app.py

pause
