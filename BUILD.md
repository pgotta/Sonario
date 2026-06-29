# Building and setting up Sonario

This covers installing Sonario, the `.bat` helper scripts, the local Ollama
models, and the Google Drive setup. For what Sonario does and how to use
it day to day, see [README.md](README.md).

## Requirements

- **Windows 10 or 11**
- **Python 3.10 or newer** (tick *Add Python to PATH* during install)

Everything else (Git, OCR tools) is installed for you by `setup.bat`.

## Install (one time)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/),
   making sure **Add Python to PATH** is checked.
2. Double-click **`setup.bat`**. It elevates once (one UAC prompt), creates a
   virtual environment, installs the Python packages, and installs **Git**,
   **Tesseract** (OCR), and **Poppler** (for scanned PDFs) via `winget`.
3. When it finishes, you are ready to run the app.

`setup.bat` is a one-time step. After that you only ever run `run.bat`.

## Run

Double-click **`run.bat`** to start the app. It activates the virtual environment
and launches the server at `http://127.0.0.1:5005`. Run this every time you want
to use Sonario.

## The .bat scripts

| Script | When to run it | What it does |
|---|---|---|
| **`setup.bat`** | Once, first | Installs Python deps, Git, Tesseract, Poppler |
| **`run.bat`** | Every time | Starts the app at `http://127.0.0.1:5005` |
| **`ollama_setup.bat`** | Once, for the local models | Installs Ollama if needed and pulls the local models (qwen3:8b + phi4-mini) |
| **`gdrive_setup.bat`** | Only for Google Drive | Opens the Google Cloud pages, verifies `credentials.json`, tests the connection |

All `.bat` files use Windows (CRLF) line endings and pause on exit so you can read
the output.

> **The `.bat` launchers are gitignored** (kept out of the GitHub repo). If you
> cloned the repo and don't have them, recreate each one by pasting the contents
> below into a file of the same name in the project root. Save them with **CRLF**
> line endings (Windows Notepad does this by default). The downloadable zip already
> includes them, so a zip user can skip this.

## The local models (the default)

Sonario's default provider runs entirely on your own machine through
[Ollama](https://ollama.com) — no account, nothing leaves your computer, and it
can't be rate-limited or suspended.

**The easy setup:** double-click **`ollama_setup.bat`** — it installs Ollama if
needed, then pulls the local models. **Or do it by hand:**

1. Install **Ollama** from [ollama.com](https://ollama.com). It runs as a
   background service and starts on its own after install.
2. Open a terminal (Command Prompt or PowerShell) and run:
   ```
   ollama pull qwen3:8b
   ollama pull phi4-mini
   ```
   Downloaded once and cached locally.
3. In Sonario, the **Qwen3 8B (recommended)** provider is already selected. Click
   **Test connection** to confirm Ollama is reachable.

The local provider options (hover each in the dropdown for details):

- **Qwen3 8B (recommended)** — the default. One strong model (~5 GB) does every
  step at full quality. Best all-round choice for a typical 8 GB gaming laptop.
- **Phi-4-mini (lightweight)** — smallest/fastest (~2.5 GB). Good for weaker or
  CPU-only machines, or when speed matters more than depth; lower quality on long
  or complex sources.
- **Smart routing** — uses phi4-mini for the heavy repetitive work and qwen3:8b
  for the final write-up. Lighter on very long jobs, but the chunk-level work is
  lower quality, and on an 8 GB GPU the two models can't both stay resident so
  Ollama swaps between them (a short pause on each swap). Needs both models pulled.
- **Ollama (any model)** — type any model name you've pulled (e.g. `qwen3:14b`,
  `llama3.1`) in the Model box.

Some reasoning models (e.g. Qwen3 in thinking mode) emit `<think>...</think>`
blocks before answering; Sonario strips that hidden reasoning out automatically so
your reports stay clean.

If **Test connection** says *"Ollama isn't running"*, install/start Ollama. If it
says *"the model isn't downloaded yet"*, run the `ollama pull` commands above.

## OCR tools (Tesseract and Poppler)

`setup.bat` installs these for you so Sonario can read scanned PDFs and images. If
you ever need to install them manually:

- **Tesseract:** https://github.com/UB-Mannheim/tesseract/wiki
- **Poppler:** https://github.com/oschwartz10612/poppler-windows

Without them, everything except scanned images and scanned PDFs still works.

**If OCR says Tesseract "not found" right after installing it:** this almost
always means Windows has not refreshed its PATH yet, not that the install failed.
Sonario now looks for Tesseract in the standard install folders automatically, but
if you still hit it, **close Sonario and run `run.bat` again in a fresh window**,
or reboot. A new window picks up the updated PATH.

## Google Drive setup (optional)

You only need this if you want to analyze a Google Drive folder. Google requires a
free, one-time setup: you create a free "app" in Google Cloud, download a
`credentials.json`, and authorize Sonario in your browser. A script cannot create
the credentials for you (Google ties them to your account), so the console steps
are manual, but they take about five minutes. Access is **read-only**.

`gdrive_setup.bat` opens each of these pages for you and verifies the result, so
you can follow along with it instead of the links below.

### Step by step (Google Cloud Console)

1. **Create a project** at https://console.cloud.google.com/projectcreate. Name it
   anything (for example "Sonario"), then make sure it is selected at the top.

2. **Enable the Drive API.** Go to **APIs & Services, then Enable APIs and
   services**, search **Google Drive API** (the first result, "Create and manage
   resources in Google Drive"), open it, and click **Enable**.

3. **Configure the OAuth consent screen** (Google now calls this the **Google Auth
   Platform**). Open **APIs & Services, then OAuth consent screen**, click **Get
   started**, then:
   - **App Information:** app name (for example "Sonario") plus your support email,
     then Next.
   - **Audience:** choose **External**, then Next. (Internal needs a Workspace
     organization.)
   - **Contact Information:** your email, then Next.
   - **Finish:** agree and **Create**.

4. **Add yourself as a Test user.** On the **Audience** page, leave the publishing
   status as **Testing** (do not publish), then under **Test users** click **Add
   users**, enter your own Gmail, and Save. Only the emails listed here can sign
   in, which is exactly what you want for personal use.

5. **Create the OAuth client.** Go to **Clients, then Create client**, set
   **Application type** to **Desktop app**, name it (for example "Sonario
   Desktop"), click **Create**, then **Download JSON**.

6. **Place the file.** Rename the downloaded `client_secret_….json` to exactly
   **`credentials.json`** and put it in Sonario's **`credentials\`** folder. (Turn
   on **View, Show, File name extensions** in File Explorer so you do not end up
   with `credentials.json.json`.) The folder should then contain `.gitkeep` and
   `credentials.json`.

7. **Connect.** Run **`gdrive_setup.bat`** to verify and test the connection, or
   just start Sonario, tick **Google Drive folder**, and paste a Drive folder
   link. The first time, a browser opens to authorize **read-only** access. Since
   the app is in Testing you will see an "unverified app" notice; click
   **Advanced, then Go to Sonario (unsafe)** to proceed. This is normal for your
   own personal app. It is "unverified" only because you have not submitted it to
   Google for public review, which a personal tool does not need.

### Do not lose `credentials.json` when updating

Google only lets you download `credentials.json` once. The Sonario download never
contains your `credentials.json` (only an empty placeholder), so a clean extract
will not touch it. But if you update by dragging a new folder over the old one and
choose "replace everything," pick **Skip** for `credentials.json` and
`token.json`, or back them up first. See `READ_BEFORE_UPDATING.txt`.

### How the Drive integration stays isolated

The Drive integration and the LLM provider never talk to each other. Drive
downloads files to a local temp folder; the app reads them from disk and sends
only plain text to your chosen LLM. The LLM call carries no trace that Drive was
involved, and Drive sees only a standard read-only desktop client.

## Updating Sonario

To update, extract the new release over your existing folder. Your local
`cache/`, `output/`, and `credentials/` contents are not included in the download,
so a clean extract leaves them in place. If your file manager asks about
replacing, keep your `credentials/credentials.json` and `credentials/token.json`
(choose Skip for those, or back them up first).

## Project layout

```
setup.bat           run once: installs Python deps + Git + Tesseract + Poppler
run.bat             start the app (run this every time)
ollama_setup.bat    install Ollama + pull the local models (qwen3:8b, phi4-mini)
gdrive_setup.bat    Google Drive setup helper (opens pages, tests connection)
app.py              Flask server: Analyze job + Summarizer job
providers.py        one OpenAI-compatible interface for every LLM
extract.py          recursive walk + text extraction (incl. OCR)
modes.py            interpretation lenses (auto/journal/work/research/general)
sources.py          Summarizer inputs: YouTube / web page / EPUB / files
pipeline.py         map / reduce / synthesize / prompts / summarize
gdrive.py           Google Drive web OAuth (read-only, isolated)
export.py           Markdown + PDF export
models.json         add custom providers without editing code
static/             single-file SPA + icons
```

## Full launcher contents
Recreate any missing launcher by pasting the matching block into a file of the
same name in the project root, saved with **CRLF** line endings.

### `setup.bat`
```bat
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
echo      First time:  ollama_setup.bat ^(local AI^)   gdrive_setup.bat ^(Drive^)
echo   ====================================================================

:end
echo.
pause
```

### `run.bat`
```bat
@echo off
REM ============================================================================
REM  Sonario - RUN. Double-click to start the app. Run setup.bat first if you
REM  haven't yet. Leave this window open while using Sonario; close it to stop.
REM ============================================================================
cd /d "%~dp0"
title Sonario

if not exist "venv\Scripts\python.exe" (
  echo.
  echo   The environment isn't set up yet. Please run  setup.bat  first.
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
echo      ollama_setup.bat   - local AI models ^(set once^)
echo      gdrive_setup.bat   - Google Drive access
echo   ====================================================================
echo.
python app.py
pause
```

### `ollama_setup.bat`

```bat
@echo off
REM ============================================================================
REM  Sonario - Ollama + local smart-routing models (the default setup).
REM
REM  Sonario's default provider runs two small models fully on your machine
REM  through Ollama - nothing leaves your computer, and it can't be rate-limited
REM  or suspended. This script:
REM    1. checks whether Ollama is installed / running,
REM    2. downloads and runs the official Ollama installer if needed,
REM    3. waits for the Ollama service to come up,
REM    4. pulls the two routing models phi4-mini + qwen3:8b (~8GB, one time).
REM
REM  Note: Ollama is a normal Windows app, so its installer may show a window and
REM  a "do you want to allow changes?" (UAC) prompt - that's expected. You only
REM  install it once.
REM ============================================================================
cd /d "%~dp0"
title Sonario - Ollama + local routing models
setlocal enableextensions enabledelayedexpansion

set "MODEL_SYNTH=qwen3:8b"
set "MODEL_FAST=phi4-mini"
set "OLLAMA_URL=https://ollama.com/download/OllamaSetup.exe"

echo.
echo   ====================================================================
echo    Local AI setup: Ollama + smart-routing models
echo    (synthesis: %MODEL_SYNTH%   fast: %MODEL_FAST%)
echo   ====================================================================
echo.

REM ---- 1. Is Ollama already responding on its default port (11434)? ----
echo   [1/4] Checking whether Ollama is already running...
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -UseBasicParsing) ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] Ollama is already running. Skipping install.
  goto :pull
)

REM ---- 2. Is the ollama command installed but not started? ----
where ollama >nul 2>&1
if %errorlevel%==0 (
  echo        Ollama is installed but not running - starting it...
  start "" ollama serve
  goto :wait_service
)

REM ---- 3. Not installed: download and run the official installer ----
echo        Ollama isn't installed yet. Downloading the official installer...
echo        (from ollama.com - this is the real Ollama, not bundled by Sonario)
if exist "OllamaSetup.exe" del /f /q "OllamaSetup.exe" >nul 2>nul
REM Use a TLS1.2 + redirect-following download, and don't swallow errors silently.
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try{Invoke-WebRequest -Uri '%OLLAMA_URL%' -OutFile 'OllamaSetup.exe' -MaximumRedirection 5 -UseBasicParsing -ErrorAction Stop}catch{Write-Host $_.Exception.Message; exit 1}"

REM Validate the download BEFORE running it. A truncated/redirected file (e.g. an
REM HTML error page saved as .exe) is the usual cause of "setup files are corrupted".
REM Real installers are many MB and start with the 'MZ' executable signature.
if not exist "OllamaSetup.exe" goto :dl_bad
powershell -NoProfile -Command "$f=Get-Item 'OllamaSetup.exe'; if($f.Length -lt 1000000){exit 1}; $b=[System.IO.File]::ReadAllBytes($f.FullName); if($b.Length -lt 2 -or $b[0]-ne 0x4D -or $b[1]-ne 0x5A){exit 1}; exit 0"
if errorlevel 1 (
  echo.
  echo   [X] The downloaded installer looks incomplete or corrupted (this can happen
  echo       with antivirus or a dropped connection). Deleting it.
  del /f /q "OllamaSetup.exe" >nul 2>nul
  goto :dl_bad
)
echo        Download looks good.
echo        Launching the Ollama installer. Follow its prompts (a UAC window
echo        and an installer window are normal). This installs Ollama as a
echo        background service that starts on its own.
echo.
echo        Press a key to start the installer...
pause >nul
start /wait "" "OllamaSetup.exe"
del /f /q "OllamaSetup.exe" >nul 2>nul

REM Make sure it's actually serving (the installer usually starts it for you).
where ollama >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo   [!] Ollama doesn't seem to be on PATH yet. You may need to close and
  echo       reopen this window (or sign out/in) so Windows picks it up, then
  echo       re-run this script. If it still fails, open the Ollama app once
  echo       from the Start menu, then re-run.
  goto :end
)
start "" ollama serve

:wait_service
echo   [2/4] Waiting for the Ollama service to come up (can take a minute on a
echo         fresh install)...
set "TRIES=0"
:wait_loop
timeout /t 2 >nul 2>&1
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -UseBasicParsing) ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto :pull
set /a TRIES+=1
REM Halfway through, nudge the server to start again in case it didn't.
if %TRIES%==20 (
  echo        Still waiting - giving the server another nudge...
  start "" ollama serve >nul 2>&1
)
if %TRIES% lss 45 goto :wait_loop
echo.
echo   [!] Ollama hasn't responded yet, but it may just be slow to start the first
echo       time. Two options:
echo         - Open the Ollama app from the Start menu (it lives in the system
echo           tray), wait a few seconds, then re-run this script; OR
echo         - Open a terminal and run:  ollama pull phi4-mini
echo           If that downloads, Ollama is fine and you can ignore this warning.
goto :end

:pull
echo   [3/4] Ollama is up.
echo   [4/4] Pulling the models (one-time downloads, ~8GB total):
echo          - %MODEL_FAST%   (fast helper, the heavy repetitive work)
echo          - %MODEL_SYNTH%  (stronger model, the final write-up)
echo        Grab a coffee - this can take a while on a slow connection.
echo        Re-runs are instant once they're cached.
echo.
echo   Pulling %MODEL_FAST% ...
ollama pull %MODEL_FAST%
if errorlevel 1 (
  echo   [X] Could not pull %MODEL_FAST%. Check your internet and re-run.
  goto :end
)
echo.
echo   Pulling %MODEL_SYNTH% ...
ollama pull %MODEL_SYNTH%
if errorlevel 1 (
  echo   [X] Could not pull %MODEL_SYNTH%. Check your internet and re-run.
  goto :end
)
echo.
echo   ====================================================================
echo    [OK] Done. The local smart-routing setup is ready.
echo   ====================================================================
echo    In Sonario, "Local (smart routing...)" is already the selected provider.
echo    Click "Test connection" to confirm. The first run is slower while a model
echo    loads into memory - that's normal.
echo.
echo    Heads-up: on an 8GB GPU the two models can't both stay resident, so Sonario
echo    swaps between them - long jobs work but aren't instant. Switch to a cloud
echo    provider in the dropdown if you need more speed.

:dl_bad
echo.
echo   ====================================================================
echo    Automatic download didn't work - install Ollama manually (1 minute)
echo   ====================================================================
echo    1. Your browser will open the Ollama download page.
echo    2. Click "Download for Windows" and run the installer.
echo    3. When it's done, run THIS script again - it will skip the download,
echo       detect Ollama, and go straight to pulling the models.
echo.
echo    Opening https://ollama.com/download ...
start "" "https://ollama.com/download"
goto :end

:end
echo.
pause
```

### `gdrive_setup.bat`
```bat
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
```
