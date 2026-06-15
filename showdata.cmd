@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Preconditions ----------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [X] Not set up yet. Run config.cmd first.
  exit /b 1
)
if not exist "config.env" (
  echo [X] config.env is missing from this folder.
  exit /b 1
)

REM Load shared settings (we only need the database path; no API key required
REM just to view what has already been pulled).
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env") do set "%%a=%%b"

".venv\Scripts\python.exe" -m madthinker_export show
exit /b %ERRORLEVEL%
