@echo off
rem KL Music Manager launcher for Windows (double-click in Explorer)
cd /d "%~dp0"

echo ========================================================
echo           Launching KL Music Manager (Windows)
echo ========================================================
echo Your browser will open automatically at http://127.0.0.1:5055
echo To stop KL Music Manager, close this window.
echo ========================================================

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3 is not installed.
    echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

%PY% app.py
if errorlevel 1 (
    echo.
    echo KL Music Manager exited with an error. Missing packages? Run:
    echo     %PY% -m pip install -r requirements.txt
    pause
)
