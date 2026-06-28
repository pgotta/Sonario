"""
gdrive.py — web-based Google Drive access via OAuth.

Newbie setup (documented in the UI's Setup tab):
  1. Create a Google Cloud project, enable the Drive API.
  2. Configure an OAuth consent screen (External, add yourself as a test user).
  3. Create an OAuth client ID of type "Desktop app", download credentials.json.
  4. Drop credentials.json into the app's credentials/ folder.
  5. Paste a Drive folder link in the app and click Connect — a browser opens
     once to authorize; the token is cached in credentials/token.json.

Read-only scope. We recursively list a folder, download Google Docs as plain
text and binary files as-is into a temp dir, then feed them to extract.py.
"""

import os
import re
import io
import tempfile

CREDS_DIR = os.path.join(os.path.dirname(__file__), "credentials")
os.makedirs(CREDS_DIR, exist_ok=True)
CREDENTIALS_FILE = os.path.join(CREDS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDS_DIR, "token.json")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google-native types we export to something extract.py understands.
EXPORT_MAP = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
}


def folder_id_from_link(link):
    """Pull the folder ID out of a Drive folder URL (or accept a raw ID)."""
    link = link.strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", link):
        return link
    return None


def credentials_present():
    return os.path.exists(CREDENTIALS_FILE)


def get_service():
    """Build an authorized Drive service, running the OAuth flow if needed."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not credentials_present():
        raise RuntimeError(
            "credentials.json not found. Add it to the credentials/ folder "
            "(see the Setup tab for the 5-step guide)."
        )

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _list_children(service, folder_id):
    files = []
    page_token = None
    q = f"'{folder_id}' in parents and trashed = false"
    while True:
        resp = service.files().list(
            q=q, spaces="drive",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token, pageSize=200,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_folder(folder_id, progress=None):
    """
    Recursively download a Drive folder into a temp dir.
    Returns (local_dir, count). Raises on auth/setup errors.
    """
    from googleapiclient.http import MediaIoBaseDownload

    service = get_service()
    local_dir = tempfile.mkdtemp(prefix="insight_gdrive_")
    count = [0]

    def recurse(fid, rel):
        for item in _list_children(service, fid):
            name = item["name"]
            mime = item["mimeType"]
            if mime == "application/vnd.google-apps.folder":
                sub = os.path.join(rel, _safe(name))
                os.makedirs(os.path.join(local_dir, sub), exist_ok=True)
                recurse(item["id"], sub)
                continue

            if mime in EXPORT_MAP:
                export_mime, ext = EXPORT_MAP[mime]
                req = service.files().export_media(fileId=item["id"],
                                                   mimeType=export_mime)
                out_name = _safe(name) + ext
            elif mime.startswith("application/vnd.google-apps"):
                continue  # forms, drawings, etc. — skip
            else:
                req = service.files().get_media(fileId=item["id"])
                out_name = _safe(name)

            dest = os.path.join(local_dir, rel, out_name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                buf = io.BytesIO()
                downloader = MediaIoBaseDownload(buf, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                with open(dest, "wb") as f:
                    f.write(buf.getvalue())
                count[0] += 1
                if progress:
                    progress({"file": name, "count": count[0]})
            except Exception as e:
                if progress:
                    progress({"file": name, "error": str(e)[:120]})

    recurse(folder_id, "")
    return local_dir, count[0]


def _safe(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "untitled"
