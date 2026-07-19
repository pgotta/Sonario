@echo off
REM ============================================================================
REM  Sonario - SETUP + INSTALL ALL (one file, run once). Idempotent: it skips
REM  anything already done, so it's safe to re-run.
REM
REM  1) Finds Python (python / py launcher / common install paths). If Python is
REM     installed but not on PATH, it ADDS it to your PATH automatically.
REM  2) Installs Python packages from requirements.txt.
REM  3) Installs Git, Tesseract OCR, Poppler via winget (skips ones present).
REM  4) Installs Ollama if needed and pulls the models (qwen3.5:9b + qwen3.5:4b).
REM  5) Done -> run  run.bat  to start Sonario.
REM
REM  Runs as your normal user so it sees YOUR Python. winget asks for admin on
REM  its own when it needs it. Groq (cloud) needs no install - just a free key.
REM ============================================================================

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo   ====================================================================
echo    Sonario - setup and install (safe to re-run; skips finished steps)
echo   ====================================================================
echo.

REM =====================  1. PYTHON  =====================
echo   [1/5] Checking for Python...
set "PY="

REM a) plain 'python' on PATH
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :py_ok

REM b) the 'py' launcher (installed with Python, often works when python doesn't)
py --version >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY goto :py_ok

REM c) python3
python3 --version >nul 2>&1
if not errorlevel 1 set "PY=python3"
if defined PY goto :py_ok

REM d) not on PATH - hunt common install locations, then add to PATH
echo   Not on PATH - looking in the usual install folders...
call :find_python
if defined PYDIR goto :py_addpath

echo   [X] Python was not found anywhere I looked.
echo       Install Python 3.10+ from https://www.python.org/downloads/
echo       On the first installer screen, TICK "Add python.exe to PATH".
echo       Then re-run this script.
goto :fail

:py_addpath
echo   Found Python at: !PYDIR!
echo   Adding it to your PATH (so 'python' works everywhere)...
REM Add to the CURRENT session so the rest of this run works immediately:
set "PATH=!PYDIR!;!PYDIR!Scripts\;%PATH%"
REM Persist to your USER PATH for future sessions (setx, no admin needed):
for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "USERPATH=%%B"
if not defined USERPATH set "USERPATH="
echo !USERPATH! | find /i "!PYDIR!" >nul
if not errorlevel 1 goto :py_path_done
if not defined USERPATH goto :setx_fresh
setx Path "!USERPATH!;!PYDIR!;!PYDIR!Scripts\" >nul
goto :py_path_done
:setx_fresh
setx Path "!PYDIR!;!PYDIR!Scripts\" >nul
:py_path_done
set "PY=python"
python --version >nul 2>&1
if errorlevel 1 set "PY=!PYDIR!python.exe"
echo   [OK] PATH updated. (New terminals will have Python on PATH from now on.)

:py_ok
echo   Using: %PY%
%PY% --version
echo.

REM =====================  2. PYTHON PACKAGES  =====================
echo   [2/5] Setting up the virtual environment and packages...
if not exist "requirements.txt" goto :no_req
REM Create the venv if it isn't there yet (run.bat expects venv\Scripts\python.exe).
if exist "venv\Scripts\python.exe" goto :venv_ready
echo   Creating virtual environment (venv)...
%PY% -m venv venv
if errorlevel 1 goto :venv_fail
:venv_ready
echo   Installing packages into the venv from requirements.txt...
"venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail
echo   [OK] Virtual environment ready and packages installed.
echo.
goto :tools

:venv_fail
echo   [X] Could not create the virtual environment with %PY%.
echo       Make sure your Python install includes the 'venv' module (the standard
echo       python.org installer does), then re-run this script.
goto :fail

:no_req
echo   [X] requirements.txt not found next to this script.
echo       Put setup_all.bat in the Sonario folder (next to app.py) and re-run.
goto :fail

:pip_fail
echo   [X] Some Python packages failed to install. Check your internet and re-run.
goto :fail

REM =====================  3. GIT / OCR TOOLS  =====================
:tools
echo   [3/5] Installing helper tools (Git, Tesseract OCR, Poppler)...
echo         (Windows may show an admin prompt for these - that is expected.)
where winget >nul 2>&1
if errorlevel 1 goto :no_winget
call :winget_install Git.Git "Git"
call :winget_install UB-Mannheim.TesseractOCR "Tesseract OCR"
call :winget_install oschwartz10612.Poppler "Poppler"
echo.
goto :ollama

:no_winget
echo   [!] winget is not available on this PC. Skipping Git/OCR auto-install.
echo       Sonario still works; only SCANNED PDFs/images (OCR) will be unavailable.
echo.
goto :ollama

REM =====================  4. OLLAMA + MODELS  =====================
:ollama
echo   [4/5] Setting up the local AI (Ollama + models)...
where ollama >nul 2>&1
if errorlevel 1 goto :install_ollama
echo   [OK] Ollama is already installed.
goto :wait_ollama

:install_ollama
echo   Ollama isn't installed. Downloading the official installer from ollama.com...
if exist "OllamaSetup.exe" del /f /q "OllamaSetup.exe" >nul 2>nul
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try{Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile 'OllamaSetup.exe' -MaximumRedirection 5 -UseBasicParsing -ErrorAction Stop}catch{Write-Host $_.Exception.Message; exit 1}"
if not exist "OllamaSetup.exe" goto :ollama_manual
powershell -NoProfile -Command "$f=Get-Item 'OllamaSetup.exe'; if($f.Length -lt 1000000){exit 1}; $b=[System.IO.File]::ReadAllBytes($f.FullName); if($b[0]-ne 0x4D -or $b[1]-ne 0x5A){exit 1}; exit 0"
if errorlevel 1 goto :ollama_bad_file
echo   Launching the Ollama installer - follow its prompts, then come back here.
echo   Press a key to start it...
pause >nul
start /wait "" "OllamaSetup.exe"
del /f /q "OllamaSetup.exe" >nul 2>nul
goto :wait_ollama

:ollama_bad_file
del /f /q "OllamaSetup.exe" >nul 2>nul
:ollama_manual
echo   [!] Automatic download failed. Opening the Ollama download page - install
echo       it manually (Download for Windows), then re-run this script.
start "" "https://ollama.com/download"
goto :fail

:wait_ollama
echo   Waiting for the Ollama service to come up...
set "TRIES=0"
:wait_loop
timeout /t 2 >nul 2>&1
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -UseBasicParsing | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% EQU 0 goto :pull_models
set /a TRIES+=1
if %TRIES% EQU 20 start "" ollama serve >nul 2>&1
if %TRIES% LSS 45 goto :wait_loop
echo   [!] Ollama hasn't responded yet. It may just be slow the first time.
echo       Open the Ollama app from the Start menu, wait a bit, then re-run this
echo       script (it will skip finished steps and just pull the models).
goto :finish

:pull_models
echo   Pulling qwen3.5:4b (fast helper, ~3.4GB; skipped if already present)...
ollama pull qwen3.5:4b
echo   Pulling qwen3.5:9b (main model, ~6.6GB; skipped if already present)...
ollama pull qwen3.5:9b
echo   [OK] Local models ready.

:finish
echo.
echo   [5/5] All set.
echo   ====================================================================
echo    Sonario is installed. Double-click  run.bat  to start it.
echo    - Default is Qwen3.5 9B (local, private). Just run and go.
echo    - Fast cloud option: pick Groq in the app, paste a free key from
echo      console.groq.com (no install needed).
echo    - Google Drive is optional: run  gdrive_setup.bat.
echo   ====================================================================
goto :end

REM =====================  helpers  =====================

REM Find a Python install folder in the usual spots. Sets PYDIR (with trailing \).
:find_python
set "PYDIR="
REM Newest first. %LocalAppData% per-user installs:
for %%V in (313 312 311 310) do call :check_dir "%LocalAppData%\Programs\Python\Python%%V\"
if defined PYDIR exit /b
REM All-users installs under Program Files:
for %%V in (313 312 311 310) do call :check_dir "%ProgramFiles%\Python%%V\"
if defined PYDIR exit /b
for %%V in (313 312 311 310) do call :check_dir "%ProgramFiles(x86)%\Python%%V\"
exit /b

:check_dir
if defined PYDIR exit /b
if exist "%~1python.exe" set "PYDIR=%~1"
exit /b

REM Install one winget package if not already present.
:winget_install
winget list --id %~1 >nul 2>&1
if %errorlevel% EQU 0 goto :wi_skip
echo       Installing %~2 ...
winget install --id %~1 -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :wi_failed
echo       [OK] %~2 installed.
exit /b
:wi_skip
echo       %~2 already installed - skipping.
exit /b
:wi_failed
echo       [!] %~2 install skipped or failed - Sonario still runs without it.
exit /b

:fail
echo.
echo   Setup did not fully complete - see the message above.

:end
echo.
pause
endlocal
