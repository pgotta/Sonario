@echo off
REM ============================================================================
REM  Sonario — Google Drive setup helper.
REM
REM  Google Drive requires a free Google Cloud "OAuth client" that only YOU can
REM  create (Google ties it to your account and won't let a script make it).
REM  This helper opens the right pages, checks your credentials file is in place,
REM  installs the needed libraries, and runs a connection test.
REM ============================================================================
cd /d "%~dp0"
title Sonario - Google Drive setup
setlocal enabledelayedexpansion

echo.
echo   ====================================================================
echo    Google Drive setup (web, one-time, ~5 minutes)
echo   ====================================================================
echo.
echo   You will create a free Google "app" so Sonario can READ your Drive.
echo   Follow these steps (Sonario's "Google Drive setup" tab has them too):
echo.
echo     1. Create a new project (any name) and select it at the top.
echo     2. APIs ^& Services -^> Enable APIs and services: search "Google Drive
echo        API" (the first result) and click Enable.
echo     3. APIs ^& Services -^> OAuth consent screen -^> Get started: app name +
echo        your email; Audience = External; contact email; Create.
echo     4. On the Audience page, leave status as "Testing" and under
echo        "Test users -^> Add users" add your own Gmail address.
echo     5. Clients -^> Create client: Application type = "Desktop app",
echo        Create, then Download JSON.
echo     6. Rename that file to exactly  credentials.json  and put it in:
echo            %~dp0credentials\
echo        (Tip: turn on File Explorer's "File name extensions" so you don't
echo         get credentials.json.json by accident.)
echo.
echo   Press any key to open the Google Cloud Console pages in your browser...
pause >nul
start "" "https://console.cloud.google.com/projectcreate"
start "" "https://console.cloud.google.com/apis/library/drive.googleapis.com"
start "" "https://console.cloud.google.com/auth/clients"
echo.

if not exist "credentials\" mkdir credentials

echo   --------------------------------------------------------------------
echo   When you've placed credentials.json into the credentials\ folder,
echo   press any key to verify and test the connection.
echo   --------------------------------------------------------------------
pause >nul

if not exist "credentials\credentials.json" (
  echo.
  echo   [X] credentials\credentials.json was not found.
  echo       Make sure the downloaded file is renamed exactly to
  echo       "credentials.json" and placed in the credentials\ folder.
  echo.
  pause
  exit /b 1
)
echo   [OK] credentials.json found.

REM ensure libs are present (uses Sonario's venv if it exists)
if exist "venv\" call venv\Scripts\activate.bat
echo   Checking Google libraries...
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib >nul 2>&1

echo.
echo   Running a connection test. A browser may open to authorize READ-ONLY
echo   access the first time - approve it, then return here.
echo.
python -c "import gdrive,sys; svc=gdrive.get_service(); print('  [OK] Connected to Google Drive successfully.')" || echo   [X] Connection test failed - see the message above.
echo.
echo   Done. In Sonario, tick "Google Drive folder" and paste a folder link.
echo.
pause
