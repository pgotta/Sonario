# Building and packaging Sonario

This is the authoritative Windows installation and release document.

## Repository policy

- BAT files are Windows release artifacts and **must never be committed**.
- `.gitignore` blocks `*.bat` with no exceptions.
- CI fails if a BAT file appears in the repository or if one of the required BAT sections below is missing.
- Release ZIPs add the five BAT files below to the complete repository source.
- Save recreated BAT files with Windows CRLF line endings.
- Never package credentials, OAuth tokens, API keys, history, cache, output, logs, PID files, the private browser profile, or shutdown diagnostics.
- `sonario.ico` and `static/favicon.ico` are generated from `static/icon-512.png` during setup and are not tracked.

## Supported environment

- Windows 10 or 11
- Python 3.10 or newer; Python 3.12 is the CI/reference version
- Optional NVIDIA GPU for faster local Ollama inference

## Current release behavior

- Local default: `qwen3.5:9b`; helper/smart-routing model: `qwen3.5:4b`.
- Groq cloud: `qwen/qwen3.6-27b`.
- Structured Groq calls use JSON Object Mode and layered recovery so malformed/truncated JSON does not discard a document.
- Sonario launches in a dedicated maximized Edge/Chrome app window with a private profile, browser sign-in, sync, password saving, and background mode disabled.
- Closing the Sonario window with X stops the exact Flask backend captured at launch. `stop.bat` is the manual fallback.
- Google Drive is optional, read-only, and may authorize or refresh only after an explicit connect/setup or Drive-backed job.

## First-time installation

1. Extract the complete Windows release ZIP into an empty folder.
2. Double-click `setup_all.bat` once.
3. Launch from the Sonario desktop shortcut created by setup.
4. Close Sonario with X when finished.

## Updating an installation

Back up `credentials\` before replacing an installation. Restore it afterward when moving to a new folder. Do not copy runtime logs, cache, PID files, or `.sonario-browser-profile` into a release.

## Validation before publishing

```text
python -m compileall -q .
python -m unittest discover -s tests -v
git ls-files "*.bat"
```

The final command must print nothing. Also verify BUILD contains all five headings below, no retired Scout model identifier remains, and `qwen/qwen3.6-27b` is present.

## Creating a Windows release ZIP

1. Start from a clean checkout of `main`.
2. Copy the repository into a staging directory.
3. Create the five BAT files below in the staging root using CRLF endings.
4. Run the validation suite.
5. Remove all secrets and runtime state.
6. Zip the complete staging directory and generate a SHA-256 checksum.

## Full BAT launcher contents

The scripts below are the executable release versions. Comments that do not affect execution are intentionally omitted to keep this source document maintainable.

### `setup_all.bat`

```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo.
echo   ====================================================================
echo    Sonario - setup and install (safe to re-run; skips finished steps)
echo   ====================================================================
echo.
echo   [1/6] Checking for Python...
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :py_ok
py --version >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY goto :py_ok
python3 --version >nul 2>&1
if not errorlevel 1 set "PY=python3"
if defined PY goto :py_ok
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
set "PATH=!PYDIR!;!PYDIR!Scripts\;%PATH%"
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
echo   [2/6] Setting up the virtual environment and packages...
if not exist "requirements.txt" goto :no_req
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
:tools
echo   [3/6] Installing helper tools (Git, Tesseract OCR, Poppler)...
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
:ollama
echo   [4/6] Setting up the local AI (Ollama + models)...
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
echo   [5/6] Creating the Sonario desktop shortcut...
if exist "sonario_launcher.vbs" if exist "create_sonario_shortcut.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\create_sonario_shortcut.ps1" -Root "%CD%"
  if errorlevel 1 echo   [!] The desktop shortcut could not be created automatically.
) else (
  echo   [!] Launcher files are missing; the desktop shortcut was skipped.
)
echo.
echo   [6/6] All set.
echo   ====================================================================
echo    Sonario is installed. Launch it from the new desktop icon.
echo    - It opens in a separate maximized app window with no console.
echo    - Closing that window stops the Sonario server.
echo    - Browser account sign-in and sync are disabled for this app window.
echo    - Default is Qwen3.5 9B (local, private).
echo    - Groq cloud uses Qwen 3.6 27B.
echo   ====================================================================
goto :end
:find_python
set "PYDIR="
for %%V in (313 312 311 310) do call :check_dir "%LocalAppData%\Programs\Python\Python%%V\"
if defined PYDIR exit /b
for %%V in (313 312 311 310) do call :check_dir "%ProgramFiles%\Python%%V\"
if defined PYDIR exit /b
for %%V in (313 312 311 310) do call :check_dir "%ProgramFiles(x86)%\Python%%V\"
exit /b
:check_dir
if defined PYDIR exit /b
if exist "%~1python.exe" set "PYDIR=%~1"
exit /b
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
```

### `run.bat`

```bat
@echo off
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"
title Sonario launcher
for %%F in ("requirements.txt" "app.py" "static\index.html" "static\icon-512.png") do (
  if not exist "%%~F" (
    echo [X] Missing required Sonario file: %%~F
    echo     Extract the complete Sonario ZIP into an empty folder.
    pause
    exit /b 1
  )
)
if not exist "venv\Scripts\python.exe" (
  echo [X] Sonario is not installed yet. Run setup_all.bat first.
  pause
  exit /b 1
)
set "PYEXE=%CD%\venv\Scripts\python.exe"
set "SONARIO_NO_BROWSER=1"
set "PYTHONUNBUFFERED=1"
set "SONARIO_ROOT=%CD%"
"%PYEXE%" -c "import urllib.request,sys; b=urllib.request.urlopen('http://127.0.0.1:5005',timeout=1).read(12000).decode('utf-8','ignore'); sys.exit(0 if '<title>Sonario</title>' in b else 1)" >nul 2>&1
if not errorlevel 1 (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5005" ^| findstr "LISTENING"') do (
    > ".sonario.pid" echo %%P
    goto :open_window
  )
)
netstat -ano | findstr ":5005" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [X] Port 5005 is already being used by another program.
  pause
  exit /b 1
)
if not exist "logs" mkdir "logs"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=$env:SONARIO_ROOT; $py=Join-Path $root 'venv\Scripts\python.exe';" ^
  "$out=Join-Path $root 'logs\sonario.log'; $err=Join-Path $root 'logs\sonario-error.log';" ^
  "$p=Start-Process -FilePath $py -ArgumentList @('app.py') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru;" ^
  "Set-Content -LiteralPath (Join-Path $root '.sonario.pid') -Value $p.Id"
if errorlevel 1 (
  echo [X] Sonario could not be launched.
  if exist "logs\sonario-error.log" start "" notepad "logs\sonario-error.log"
  pause
  exit /b 1
)
set "TRIES=0"
:wait_ready
"%PYEXE%" -c "import urllib.request,sys; b=urllib.request.urlopen('http://127.0.0.1:5005',timeout=2).read(12000).decode('utf-8','ignore'); sys.exit(0 if '<title>Sonario</title>' in b else 1)" >nul 2>&1
if not errorlevel 1 goto :open_window
set /a TRIES+=1
if !TRIES! LSS 60 (
  timeout /t 1 >nul
  goto :wait_ready
)
echo [X] Sonario did not start correctly.
if exist "logs\sonario-error.log" start "" notepad "logs\sonario-error.log"
call stop.bat >nul 2>&1
pause
exit /b 1
:open_window
start "" /min powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%CD%\sonario_window.ps1" -Url "http://127.0.0.1:5005" -Root "%CD%"
exit /b 0
```

### `stop.bat`

```bat
@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\stop_sonario.ps1" -Root "%CD%"
timeout /t 2 >nul
```

### `gdrive_setup.bat`

```bat
@echo off
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
if exist "venv\" call venv\Scripts\activate.bat
echo   Checking Google libraries...
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib >nul 2>&1
echo.
echo   Running a connection test. A browser may open to authorize READ-ONLY
echo   access (or to re-authorize if your previous sign-in expired) - approve
echo   it, then return here.
echo.
set "SONARIO_ALLOW_OAUTH=1"
python -c "import gdrive,sys; svc=gdrive.get_service(); print('  [OK] Connected to Google Drive successfully.')" || echo   [X] Connection test failed - see the message above.
set "SONARIO_ALLOW_OAUTH="
echo.
echo   Done. In Sonario, tick "Google Drive folder" and paste a folder link.
echo.
pause
```

### `Create Sonario Shortcut.bat`

```bat
@echo off
setlocal
cd /d "%~dp0"
title Create Sonario Shortcut
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\create_sonario_shortcut.ps1" -Root "%CD%"
if errorlevel 1 (
  echo.
  echo [X] The shortcut could not be created.
  pause
  exit /b 1
)
echo.
echo You can now launch Sonario from the desktop icon.
pause
```

