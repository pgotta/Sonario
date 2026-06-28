@echo off
REM ============================================================================
REM  Sonario - re-sign in to Windows Copilot.
REM
REM  You only need this if your saved sign-in expired (Sonario shows a Copilot
REM  auth/connection error even though the server is running). It opens the
REM  Microsoft sign-in again and saves a fresh session.
REM ============================================================================
cd /d "%~dp0"
title Sonario - Copilot sign-in
setlocal enableextensions

set "REPO=Windows-Copilot-API"
set "VPY=%~dp0venv\Scripts\python.exe"

echo.
echo   ====================================================================
echo    Windows Copilot - sign in again
echo   ====================================================================
echo.

if not exist "%VPY%" (
  echo   Sonario isn't set up yet. Run  setup.bat  first.
  goto :end
)
if not exist "%REPO%\" (
  echo   The Copilot bridge isn't installed yet. Run  copilot_setup.bat  first.
  goto :end
)

echo   A browser window will open. Sign in once and pass any "verify you're
echo   human" check. It finishes by itself when sign-in is detected.
echo.
echo   Press a key when you're ready...
pause >nul
pushd "%REPO%"
"%VPY%" -m copilot login
popd
echo.
echo   [OK] Done. If the Copilot server isn't running, start it with
echo        copilot_setup.bat (it will skip sign-in now that you're signed in).

:end
echo.
pause
