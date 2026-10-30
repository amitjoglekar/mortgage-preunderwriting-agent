@echo off
REM Double-click to start the Pre-Underwriting Agent on Windows.
REM First run: creates a private Python environment and installs dependencies (1-3 minutes).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer. Then run this file again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Setting up for the first time. This takes 1-3 minutes...
  python -m venv .venv
  if errorlevel 1 goto :fail
  ".venv\Scripts\python" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

echo.
echo Starting the app. Open http://localhost:8000 in your browser.
echo Keep this window open while you use the app. Press Ctrl+C or close the window to stop.
echo.
".venv\Scripts\python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
exit /b 0

:fail
echo.
echo Setup failed. Delete the .venv folder in this directory and try again.
echo See GETTING_STARTED.md (Troubleshooting) for help.
pause
exit /b 1
