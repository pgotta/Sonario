@echo off
REM ============================================================================
REM  Sonario - SETUP (install only). Run this once.
REM
REM  Creates the Python environment, installs requirements, and installs the
REM  OCR tools (Tesseract + Poppler) and Git via winget. To START the app
REM  afterwards, double-click  run.bat.
REM
REM  Self-elevates so the Windows admin prompt appears ONCE up front (avoids the
REM  "0x800704c7 operation cancelled" you get when a UAC dialog hides behind the
REM  console window mid-install).
REM ============================================================================
cd /d "%~dp0"
title Sonario setup
setlocal enabledelayedexpansion

REM ---- self-elevate for the winget tool installs ----
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo   Setup needs administrator rights to install OCR tools and Git.
  echo   Please click YES on the Windows prompt that appears...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"

echo.
echo   ====================================================================
echo    Sonario setup
echo   ====================================================================
echo.

REM ---- 1. Python ----
python --version >nul 2>&1
if errorlevel 1 (
  echo   [X] Python not found. Install Python 3.10+ from
  echo       https://www.python.org/downloads/  and tick "Add Python to PATH",
  echo       then run setup.bat again.
  goto :end
)
echo   [OK] Python found.

REM ---- 2. venv + Python packages ----
if not exist "venv\" (
  echo   Creating virtual environment...
  python -m venv venv
)
call venv\Scripts\activate.bat
echo   Installing Python packages ^(already-installed ones are skipped^)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo   [X] Python package install failed. Scroll up for the error.
  goto :end
)
echo   [OK] Python packages installed.
echo.

set "HAVE_WINGET=0"
winget --version >nul 2>&1
if %errorlevel%==0 set "HAVE_WINGET=1"
if "!HAVE_WINGET!"=="0" echo   [!] winget not found - the tools below must be installed manually.

REM ---- 3. Git ----
where git >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] Git already installed.
) else (
  echo   Installing Git...
  if "!HAVE_WINGET!"=="1" (
    winget install -e --id Git.Git --silent --accept-source-agreements --accept-package-agreements
  ) else (
    echo   [!] Install Git manually: https://git-scm.com/download/win
  )
)
echo.

REM ---- 4. Tesseract OCR ----
where tesseract >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] Tesseract already installed.
) else (
  echo   Installing Tesseract OCR...
  if "!HAVE_WINGET!"=="1" (
    winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-source-agreements --accept-package-agreements
  ) else (
    echo   [!] Install Tesseract manually: https://github.com/UB-Mannheim/tesseract/wiki
  )
)
echo.

REM ---- 5. Poppler ----
where pdftoppm >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] Poppler already installed.
) else (
  echo   Installing Poppler...
  if "!HAVE_WINGET!"=="1" (
    winget install -e --id oschwartz10612.Poppler --silent --accept-source-agreements --accept-package-agreements
  ) else (
    echo   [!] Install Poppler manually: https://github.com/oschwartz10612/poppler-windows
  )
)
echo.

REM ---- 6. Verify ----
echo   ====================================================================
echo    Verifying
echo   ====================================================================
set "G=0"
where git >nul 2>&1 && set "G=1"
if exist "%ProgramFiles%\Git\cmd\git.exe" set "G=1"
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "G=1"
if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "G=1"
if "!G!"=="1" (echo   [OK] Git) else echo   [MISSING] Git - re-run setup.bat, or install from git-scm.com
set "T=0"
where tesseract >nul 2>&1 && set "T=1"
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "T=1"
if "!T!"=="1" (echo   [OK] Tesseract OCR) else echo   [MISSING] Tesseract - re-run setup.bat and click YES on the admin prompt
where pdftoppm >nul 2>&1 && (echo   [OK] Poppler) || echo   [MISSING] Poppler ^(or PATH not refreshed - it will work next launch^)
echo.
echo   ^(If something shows [MISSING] right after it installed, it just means
echo    this window's PATH hasn't refreshed yet - it is installed. A new
echo    window, or a reboot, will see it.^)
echo.
echo   Note: the OCR tools are only needed for SCANNED PDFs and images.
echo   Everything else works without them.
echo.
echo   ====================================================================
echo    Setup complete.  Now double-click  run.bat  to start Sonario.
echo      Optional:  copilot_setup.bat ^(free AI^)   gdrive_setup.bat ^(Drive^)
echo   ====================================================================

:end
echo.
pause
