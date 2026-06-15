@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   TCA Catch Reports Export - one-time setup
echo ============================================================
echo.

REM --- 1. Find a usable Python (3.10+) ------------------------------------
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )

if not defined PY (
  echo [X] Python was not found on this machine.
  echo.
  echo     Install Python 3.10 or newer, then run config.cmd again:
  echo       winget install Python.Python.3.12
  echo     or download from https://www.python.org/downloads/
  echo       ^(during install, tick "Add python.exe to PATH"^)
  echo.
  exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [X] Found Python, but it is older than 3.10. Please install 3.10+.
  %PY% --version
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v

REM --- 2. Create the virtual environment --------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creating virtual environment ^(.venv^) ...
  %PY% -m venv .venv
  if errorlevel 1 ( echo [X] Failed to create the virtual environment. & exit /b 1 )
)
set "VENVPY=.venv\Scripts\python.exe"
echo [OK] Virtual environment ready.

REM --- 3. Install dependencies ------------------------------------------
echo [..] Installing dependencies ^(this can take a minute the first time^) ...
"%VENVPY%" -m pip install --upgrade pip >nul 2>&1
"%VENVPY%" -m pip install -e . >nul 2>&1
if errorlevel 1 ( echo [X] Dependency install failed. Run:  "%VENVPY%" -m pip install -e . & exit /b 1 )
echo [OK] Dependencies installed.

REM --- 4. Make sure config files exist ----------------------------------
if not exist "config.env" (
  echo [X] config.env is missing from this folder.
  exit /b 1
)

REM config.env.local holds your private key and is not tracked by git.
REM Recreate it from a template if this is a fresh clone.
if not exist "config.env.local" (
  echo [..] Creating config.env.local for your private API key ...
  (
    echo # Local secrets - NOT tracked by git. Holds your private API key.
    echo # config.cmd fills this in for you, or paste your key after the = sign.
    echo MT_EXPORT_API_KEY=tca_live_PASTE_YOUR_KEY_HERE
  )> "config.env.local"
)

REM --- 5. Offer to store the API key -----------------------------------
findstr /c:"tca_live_PASTE_YOUR_KEY_HERE" config.env.local >nul
if errorlevel 1 (
  echo [OK] An API key is already set in config.env.local.
  echo.
  echo Setup complete. Now run:  run.cmd
  exit /b 0
)

echo.
echo The last step is your API key ^(we emailed it; it looks like tca_live_...^).
set "USERKEY="
set /p "USERKEY=Paste the API key and press Enter (or just Enter to do it later): "

if not defined USERKEY (
  echo.
  echo No key entered. Open config.env.local, paste your key after
  echo   MT_EXPORT_API_KEY=
  echo then run:  run.cmd
  exit /b 0
)

"%VENVPY%" -c "import re,sys; p='config.env.local'; s=open(p,encoding='utf-8').read(); s=re.sub(r'(?m)^MT_EXPORT_API_KEY=.*$', 'MT_EXPORT_API_KEY='+sys.argv[1].strip(), s); open(p,'w',encoding='utf-8').write(s)" "%USERKEY%"
if errorlevel 1 ( echo [X] Could not write the key to config.env.local. Please edit it by hand. & exit /b 1 )
echo [OK] API key saved to config.env.local.
echo.
echo Setup complete. Now run:  run.cmd
exit /b 0
