@echo off
REM ============================================================================
REM  Sonario - DeepSeek backend setup (SeeStory-style).
REM
REM  The free "DeepSeek" provider needs a small local bridge server
REM  (Deepseek-API by sums001) running on http://localhost:8001. (Port 8001 is
REM  used so it never clashes with the Windows Copilot bridge on 8000 - you can
REM  run both at once.) This downloads it (zip, with a git fallback), installs it
REM  into Sonario's own venv, signs you in once, and starts it. On re-runs it
REM  pulls the latest.
REM
REM  KEEP the window this opens OPEN while you use the DeepSeek provider
REM  (unless it starts hidden, in which case you can close it).
REM ============================================================================
cd /d "%~dp0"
title Sonario - DeepSeek backend
setlocal enableextensions enabledelayedexpansion

set "REPO=Deepseek-API"
set "VPY=%~dp0venv\Scripts\python.exe"
set "DSPORT=8001"

echo.
echo   ====================================================================
echo    DeepSeek backend
echo   ====================================================================
echo.

REM ---- 0. Sonario venv must exist (we install into it) ----
if not exist "%VPY%" (
  echo   Sonario isn't set up yet. Please run  setup.bat  first.
  goto :end
)

REM ---- 1. Already running? ----
echo   [1/5] Checking if the DeepSeek server is already running on port %DSPORT%...
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://localhost:%DSPORT%/v1/models' -TimeoutSec 3 -UseBasicParsing) ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] The DeepSeek server is already running in the background. All set.
  echo        To pull the latest bridge updates, run  deepseek_stop.bat  first,
  echo        then run this script again.
  goto :end
)
echo        Not running yet - setting it up.
echo.

REM ---- 2. Get the bridge: git clone/pull if git exists, else zip download ----
echo   [2/5] Getting the DeepSeek bridge from github.com/sums001 ...
where git >nul 2>&1
if %errorlevel%==0 (
  if exist "%REPO%\" (
    pushd "%REPO%"
    git pull --ff-only
    popd
  ) else (
    git clone https://github.com/sums001/Deepseek-API "%REPO%"
  )
  if exist "%REPO%\" goto :have_repo
)

REM --- zip fallback (no git, or clone failed) ---
echo        Git unavailable - downloading as a zip instead...
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'https://github.com/sums001/Deepseek-API/archive/refs/heads/main.zip' -OutFile 'dsa.zip' -UseBasicParsing}catch{exit 1}"
if not exist "dsa.zip" goto :dl_fail
powershell -NoProfile -Command "Expand-Archive -Path 'dsa.zip' -DestinationPath '.' -Force"
if exist "Deepseek-API-main\" (
  if exist "%REPO%\" rmdir /s /q "%REPO%"
  move /Y "Deepseek-API-main" "%REPO%" >nul
)
del /f /q dsa.zip >nul 2>nul
if not exist "%REPO%\" goto :dl_fail

:have_repo
echo        OK: %CD%\%REPO%
echo.

REM ---- 3. Install its Python requirements into Sonario's venv ----
echo   [3/5] Installing its requirements ^(already-installed ones are skipped^)...
if exist "%REPO%\requirements.txt" (
  "%VPY%" -m pip install -r "%REPO%\requirements.txt"
  if errorlevel 1 goto :pip_fail
)
echo.

REM ---- 4. Playwright Chromium (for the sign-in), skipped if present ----
echo   [4/5] Installing the Playwright Chromium browser ^(skipped if present^)...
"%VPY%" -m playwright install chromium
echo.

REM ---- 5. Sign in ONLY if there's no saved session, then start the server ----
echo   [5/5] DeepSeek sign-in
if exist "%REPO%\session\token.json" (
  echo        [OK] A saved sign-in was found - skipping login.
  echo        ^(To sign in again later, run  login_deepseek.bat^)
) else (
  echo.
  echo        First-time sign-in. A browser window will open - sign in once to
  echo        your DeepSeek account and pass any "verify you're human" check.
  echo        It finishes by itself.
  echo.
  echo        Press a key when you're ready to open the sign-in window...
  pause >nul
  pushd "%REPO%"
  "%VPY%" -m deepseek.auth
  popd
)
echo.
echo   ====================================================================
echo    Starting the DeepSeek server in the background (localhost:%DSPORT%)
echo   ====================================================================
echo.
set "PYW=%~dp0venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%VPY%"

REM --- Attempt 1: launch fully hidden via pythonw + VBScript (no window) ---
REM     The bridge reads the PORT env var, so we set it to %DSPORT% (8001).
set "VBS=%TEMP%\sonario_deepseek_start.vbs"
> "%VBS%" echo Set s = CreateObject("WScript.Shell")
>> "%VBS%" echo s.CurrentDirectory = "%~dp0%REPO%"
>> "%VBS%" echo s.Environment("PROCESS")("PORT") = "%DSPORT%"
>> "%VBS%" echo s.Run "%PYW% app.py", 0, False
cscript //nologo "%VBS%" >nul 2>&1
echo   Starting hidden... waiting for it to come up (this can take ~15s).

set "TRIES=0"
:wait_hidden
timeout /t 2 >nul 2>&1
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://localhost:%DSPORT%/v1/models' -TimeoutSec 3 -UseBasicParsing) ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto :hidden_ok
set /a TRIES+=1
if %TRIES% lss 10 goto :wait_hidden
goto :hidden_fallback

:hidden_ok
echo   [OK] The DeepSeek server is running HIDDEN in the background. There is no
echo        window to keep open - you can close this one. Stop it later with
echo        deepseek_stop.bat.
goto :end

:hidden_fallback
REM --- Attempt 2: hidden didn't answer. Fall back to a MINIMIZED window so you
REM     always end up with a working server (and can see any error). ---
echo   [!] The hidden start didn't respond. Falling back to a minimized window.
echo       ^(Keep the small "Sonario DeepSeek server" window open while you use
echo        DeepSeek - you can minimize it, just don't close it.^)
pushd "%REPO%"
set "PORT=%DSPORT%"
start "Sonario DeepSeek server" /min "%VPY%" app.py
popd

set "TRIES=0"
:wait_min
timeout /t 2 >nul 2>&1
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://localhost:%DSPORT%/v1/models' -TimeoutSec 3 -UseBasicParsing) ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto :min_ok
set /a TRIES+=1
if %TRIES% lss 10 goto :wait_min
echo   [X] The server still isn't responding. Open the "Sonario DeepSeek server"
echo       window to read the error, make sure you're signed in
echo       ^(run login_deepseek.bat^), then run this script again.
goto :end

:min_ok
echo   [OK] The DeepSeek server is up and responding ^(minimized window^).
goto :end

:dl_fail
echo.
echo   [X] Could not download the DeepSeek API. Check your internet connection,
echo       or install it by hand - see README.md.
goto :end

:pip_fail
echo.
echo   [X] Installing the API's requirements failed. Scroll up for the reason.
goto :end

:end
echo.
pause
