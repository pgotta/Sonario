@echo off
REM ============================================================================
REM  Sonario - RUN. Double-click to start the app. Run setup_all.bat first if
REM  you haven't yet. Leave this window open while using Sonario; close it to stop.
REM ============================================================================
cd /d "%~dp0"
title Sonario

if not exist "venv\Scripts\python.exe" (
  echo.
  echo   The environment isn't set up yet. Please run  setup_all.bat  first.
  echo.
  pause
  exit /b 1
)

call venv\Scripts\activate.bat

REM Make sure Tesseract is on PATH for this session even if winget's PATH entry
REM hasn't propagated yet (common right after install). Harmless if not present.
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles%\Tesseract-OCR;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\tesseract.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
if exist "%ProgramFiles%\poppler\Library\bin\pdftoppm.exe" set "PATH=%ProgramFiles%\poppler\Library\bin;%PATH%"

echo.
echo   ====================================================================
echo    Starting Sonario...  your browser will open automatically.
echo    Leave this window open while you use the app. Close it to stop.
echo.
echo    First-time setup:
echo      setup_all.bat      - one-time full install ^(Python deps + local AI^)
echo      gdrive_setup.bat   - Google Drive access ^(optional^)
echo   ====================================================================
echo.
python app.py
pause
