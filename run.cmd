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
if not exist "config.env.local" (
  echo [X] config.env.local is missing. Run config.cmd first to set your key.
  exit /b 1
)

REM --- Load settings: shared config.env first, then secret config.env.local
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env") do set "%%a=%%b"
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env.local") do set "%%a=%%b"

REM --- Validate the API key --------------------------------------------
if "%MT_EXPORT_API_KEY%"=="" (
  echo [X] No API key set. Run config.cmd, or paste your key into config.env.local.
  exit /b 1
)
echo %MT_EXPORT_API_KEY% | findstr /c:"tca_live_PASTE_YOUR_KEY_HERE" >nul
if not errorlevel 1 (
  echo [X] The API key in config.env.local is still the placeholder.
  echo     Run config.cmd to set the key we emailed you.
  exit /b 1
)

REM --- Run the sync -----------------------------------------------------
echo Pulling catch reports from the export API ...
echo.
".venv\Scripts\python.exe" -m madthinker_export sync
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Done. Your data is in "%MT_EXPORT_DB_PATH%".
  if not "%MT_EXPORT_PHOTO_DIR%"=="" echo Photos are in the "%MT_EXPORT_PHOTO_DIR%" folder.
) else (
  echo Sync exited with code %RC%. See the message above.
)
exit /b %RC%
