@echo off
REM ============================================================================
REM  Sonario - re-sign in to DeepSeek.
REM
REM  You only need this if your saved sign-in expired (Sonario shows a DeepSeek
REM  auth/connection error even though the server is running). It opens the
REM  DeepSeek sign-in again and saves a fresh session.
REM ============================================================================
cd /d "%~dp0"
title Sonario - DeepSeek sign-in
setlocal enableextensions

set "REPO=Deepseek-API"
set "VPY=%~dp0venv\Scripts\python.exe"

echo.
echo   ====================================================================
echo    DeepSeek - sign in again
echo   ====================================================================
echo.

if not exist "%VPY%" (
  echo   Sonario isn't set up yet. Run  setup.bat  first.
  goto :end
)
if not exist "%REPO%\" (
  echo   The DeepSeek bridge isn't installed yet. Run  deepseek_setup.bat  first.
  goto :end
)

echo   A browser window will open. Sign in once to your DeepSeek account and pass
echo   any "verify you're human" check. It finishes by itself when sign-in is
echo   detected.
echo.
echo   Press a key when you're ready...
pause >nul
pushd "%REPO%"
"%VPY%" -m deepseek.auth
popd
echo.
echo   [OK] Done. If the DeepSeek server isn't running, start it with
echo        deepseek_setup.bat (it will skip sign-in now that you're signed in).

:end
echo.
pause
