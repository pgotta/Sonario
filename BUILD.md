# Building and setting up Sonario

This covers installing Sonario, the `.bat` helper scripts, the free Windows
Copilot backend, and the Google Drive setup. For what Sonario does and how to use
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
| **`copilot_setup.bat`** | Once (and to update) | Installs, signs you into, and starts the free Windows Copilot backend in the background. Skips sign-in if already done |
| **`login_copilot.bat`** | Only if the session expires | Signs you into Copilot again |
| **`copilot_stop.bat`** | When you want to stop it | Stops the background Copilot server |
| **`deepseek_setup.bat`** | Once (and to update) | Same as `copilot_setup.bat`, but for the free DeepSeek backend (runs on port 8001) |
| **`login_deepseek.bat`** | Only if the session expires | Signs you into DeepSeek again |
| **`deepseek_stop.bat`** | When you want to stop it | Stops the background DeepSeek server |
| **`gdrive_setup.bat`** | Only for Google Drive | Opens the Google Cloud pages, verifies `credentials.json`, tests the connection |

All `.bat` files use Windows (CRLF) line endings and pause on exit so you can read
the output.

## The free Windows Copilot backend

Sonario's default provider is **Windows Copilot**, which is free and needs no API
key. It works through a small local bridge,
[Windows-Copilot-API](https://github.com/sums001/Windows-Copilot-API).

Run **`copilot_setup.bat`** once. It:

1. Downloads the bridge (zip, with a git clone/pull fallback) and installs it into
   Sonario's own virtual environment.
2. **Signs you in once** (a browser window opens). Your session is saved, so later
   runs skip the sign-in and just pull the latest bridge.
3. Starts the bridge server **in the background**. It first tries to run fully
   hidden (no console, no taskbar entry) and, if that does not come up in time,
   falls back to a minimized window so you are never left with a silent failure.
   Either way it verifies the server is responding before it finishes.

You can close the setup window afterward; the server keeps running and Sonario
uses it automatically.

- **Stop it:** run **`copilot_stop.bat`** (it frees port 8000).
- **Sign in again** (only if the session expires): run **`login_copilot.bat`**.
- **Check status:** in Sonario, click **Test connection**. It tells you whether
  the server is running, signed in, or needs attention, and which script to run.

If Sonario shows *"connection refused"* or *"WinError 10061"*, the background
server is not running. Run `copilot_setup.bat` again; it skips the sign-in and
just restarts the server.

> The bridge is serialized and rate-limited, so Sonario paces calls (about 4s
> each) and caches every analyzed file. A 200-doc Analyze run takes roughly 10 to
> 20 minutes the first time and is instant on re-runs.

> The background server does not survive a reboot or logout. After a restart, run
> `copilot_setup.bat` once (it skips sign-in and relaunches in a few seconds).

## The free DeepSeek backend

DeepSeek is an optional second free provider that works exactly like the Copilot
one. It uses a small local bridge,
[Deepseek-API](https://github.com/sums001/Deepseek-API), which turns your free
signed-in [chat.deepseek.com](https://chat.deepseek.com) account into a local API.

Run **`deepseek_setup.bat`** once. It does the same three things as the Copilot
setup (download the bridge into Sonario's venv, sign you in once via a browser,
then start the server in the background, hidden if possible). The only difference
is the port: **DeepSeek runs on `localhost:8001`** so it never clashes with the
Copilot bridge on `8000` — you can run both at the same time.

- **Two models:** pick **DeepSeek** (fast) or **DeepSeek Expert** (stronger,
  slower) in the provider dropdown. Both use the same bridge and the same sign-in.
- **Stop it:** run **`deepseek_stop.bat`** (it frees port 8001).
- **Sign in again** (only if the session expires): run **`login_deepseek.bat`**.
- **Check status:** click **Test connection** in Sonario; it tells you whether the
  DeepSeek server is running, signed in, or needs attention.

> The bridge serializes calls and self-limits to about 30 requests/minute, so
> Sonario paces DeepSeek calls (about 3s each), the same way it paces Copilot.

> Because DeepSeek is a separate account from Copilot, it's a useful fallback if
> your Copilot session is ever rate-limited: switch the provider dropdown to
> DeepSeek and keep working.

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
copilot_setup.bat   install + sign in + start the free Copilot backend (hidden)
login_copilot.bat   sign in to Copilot again
copilot_stop.bat    stop the background Copilot server
deepseek_setup.bat  install + sign in + start the free DeepSeek backend (port 8001)
login_deepseek.bat  sign in to DeepSeek again
deepseek_stop.bat   stop the background DeepSeek server
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
