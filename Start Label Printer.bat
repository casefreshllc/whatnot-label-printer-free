@echo off
setlocal
cd /d "%~dp0"
title HammerSlip

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

%PY% --version >nul 2>nul
if not %errorlevel%==0 (
  echo Python is not installed.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

rem The .venv folder only works on the computer (and Windows user) that created it.
rem If it was copied from another PC, or is broken, throw it away and rebuild it.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import PIL, win32print" >nul 2>nul
  if errorlevel 1 (
    echo The setup folder came from another computer or is damaged. Rebuilding it...
    rmdir /s /q ".venv"
  )
)
if exist ".venv" if not exist ".venv\Scripts\python.exe" rmdir /s /q ".venv"

if not exist ".venv\Scripts\python.exe" (
  echo Setting things up for this computer. This takes a minute...
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)

start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:fail
echo.
echo Setup failed. Send a screenshot of this window for help.
pause
exit /b 1
