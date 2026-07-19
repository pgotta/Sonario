# Building and setting up Sonario

This covers installing Sonario, the `.bat` helper scripts, the local Ollama
models, and the Google Drive setup. For what Sonario does and how to use
it day to day, see [README.md](README.md).

## Requirements

- **Windows 10 or 11**
- **Python 3.10 or newer** (tick *Add Python to PATH* during install)

Everything else (Git, OCR tools, Ollama) is installed for you by `setup_all.bat`.

## Install (one time)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/),
   making sure **Add Python to PATH** is checked.
2. Double-click **`setup_all.bat`**. It creates a
   virtual environment, installs the Python packages, and installs **Git**,
   **Tesseract** (OCR), and **Poppler** (for scanned PDFs) via `winget`.
3. When it finishes, you are ready to run the app.

`setup_all.bat` is a one-time step (safe to re-run; it skips anything already done). After that you only ever run `run.bat`.

## Run

Double-click **`run.bat`** to start the app. It activates the virtual environment
and launches the server at `http://127.0.0.1:5005`. Run this every time you want
to use Sonario.

## The .bat scripts

| Script | When to run it | What it does |
|---|---|---|
| **`setup_all.bat`** | Once, first (safe to re-run) | Everything: finds Python (fixes PATH if needed), creates the venv, installs Python deps + Git + Tesseract + Poppler, installs Ollama, pulls the local models (qwen3.5:9b + qwen3.5:4b) |
| **`run.bat`** | Every time | Starts the app at `http://127.0.0.1:5005` |
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

**The easy setup:** double-click **`setup_all.bat`** — it installs Ollama if
needed, then pulls the local models. **Or do it by hand:**

1. Install **Ollama** from [ollama.com](https://ollama.com). It runs as a
   background service and starts on its own after install.
2. Open a terminal (Command Prompt or PowerShell) and run:
   ```
   ollama pull qwen3.5:9b
   ollama pull qwen3.5:4b
   ```
   Downloaded once and cached locally.
3. In Sonario, the **Qwen3.5 9B (recommended)** provider is already selected. Click
   **Test connection** to confirm Ollama is reachable.

The local provider options (hover each in the dropdown for details):

- **Qwen3.5 9B (recommended)** — the default. One strong model (~5 GB) does every
  step at full quality. Best all-round choice for a typical 8 GB gaming laptop.
- **Qwen3.5 4B (lightweight)** — smallest/fastest (~2.5 GB). Good for weaker or
  CPU-only machines, or when speed matters more than depth; lower quality on long
  or complex sources.
- **Smart routing** — uses qwen3.5:4b for the heavy repetitive work and qwen3.5:9b
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

## Groq cloud (optional, fast)

Groq is a cloud engine that summarizes with **Qwen 3.6 27B** in seconds and
handles long videos or whole books in one pass, thanks to its 128k-token context.
It's the same engine as the Sonario mobile app. The trade-off: your text is sent
to Groq's servers, so use a local model instead for anything sensitive.

Setup (about a minute):

1. Go to [console.groq.com](https://console.groq.com) and sign in (free, no credit
   card).
2. Open **API Keys**, click **Create API Key**, and copy it. You only see the full
   key once, so copy it now.
3. In Sonario, pick **Groq - Qwen 3.6 27B** from the provider dropdown, paste the
   key into the **API key** box, and click **Test connection**.

Notes:

- **Remembering the key.** By default the key is held only in memory for the
  current run. Tick **"Remember this key on this PC"** under the key box and
  Sonario saves it to `credentials/api_keys.json` so it's filled in automatically
  every time you start the app. Untick it to forget the key immediately.
- **Honest note on that:** a remembered key is stored in **plain text** in your
  `credentials/` folder (which is gitignored, so it is never committed). Anything
  that can read your user account's files can read it. There is no meaningful way
  to encrypt it locally, because the app would need the decryption key sitting
  right next to it - this is the same trade-off every desktop app makes when it
  offers to remember a key. It never leaves your machine. If you'd rather not
  store a key at all, leave the box unticked, or use the local models.
- Groq has a generous free tier with per-minute rate limits. Sonario queues calls below the minute limits and follows Groq's reset headers. If the organization-wide daily quota is exhausted, switch to a local model or continue after reset.
- The model string (`qwen/qwen3.6-27b`) and endpoint
  (`https://api.groq.com/openai/v1`) are filled in for you; you only need the key.

## OCR tools (Tesseract and Poppler)

`setup_all.bat` installs these for you so Sonario can read scanned PDFs and images. If
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

### If Google Drive says "sign-in expired" (token expired or revoked)

Google Drive sign-ins do not last forever - this is Google's policy, not a
Sonario limitation. If you see **"sign-in expired"** on the badge, or an
`invalid_grant: Token has been expired or revoked` error, your saved sign-in
(`credentials/token.json`) is no longer valid. Here is why it happens and how to
make it last as long as possible.

**Why it expires:**

- **The big one - "Testing" status expires every 7 days.** While your app's
  publishing status is **Testing** (the default from step 4 above), Google expires
  its refresh tokens after **7 days**. So you will have to re-authorize about once
  a week. This is the most common cause.
- Other triggers: you changed your Google password, you revoked the app's access
  in your Google account, or the token went unused for ~6 months.

**How to re-authorize (takes ~15 seconds):**

Just run **`gdrive_setup.bat`** again, or tick **Google Drive folder** and paste a
link - Sonario detects the dead token, deletes it, and reopens the browser
authorize screen. Approve it and you are reconnected. (You do **not** need a new
`credentials.json` - the same one keeps working; only the per-session `token.json`
refreshes.)

**How to make it last far longer (stop the weekly expiry):**

Move your app from **Testing** to **In production**:

1. In [Google Cloud Console](https://console.cloud.google.com/), open **APIs &
   Services, then OAuth consent screen** (the **Audience** page).
2. Under **Publishing status**, click **Publish app** and confirm.

Once published, refresh tokens no longer expire on the 7-day timer, so a single
sign-in lasts effectively until you change your password or revoke it. You will
still see the "unverified app" notice when signing in (click **Advanced, then Go
to Sonario**) - that is fine, because as a personal Desktop-app client you do
**not** need to complete Google's verification review. Publishing here just stops
the test-mode token expiry; it does not make your app public or send it to Google
for review, since Desktop-app credentials are tied to your own account.

> If you would rather not publish, that is fine too - just expect to re-run
> `gdrive_setup.bat` about once a week. Both options are safe.

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
setup_all.bat       run once: venv + Python deps + Git/OCR tools + Ollama + models
run.bat             start the app (run this every time)
gdrive_setup.bat    Google Drive setup helper (opens pages, tests connection)
app.py              Flask server: Analyze job + Summarizer job
providers.py        one OpenAI-compatible interface for every LLM
extract.py          recursive walk + text extraction (incl. OCR)
modes.py            interpretation lenses (auto/journal/work/research/general)
sources.py          Summarizer inputs: YouTube / web page / EPUB / files
pipeline.py         map / reduce / synthesize / prompts / summarize
gdrive.py           Google Drive web OAuth (read-only, isolated)
export.py           Markdown + PDF export
keystore.py       remembers cloud API keys locally (opt-in)
models.json         add custom providers without editing code
static/             single-file SPA + icons
```

## Full launcher contents
Recreate any missing launcher by pasting the matching block into a file of the
same name in the project root, saved with **CRLF** line endings.

### `setup_all.bat`
```bat
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
```

### `run.bat`
```bat
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
