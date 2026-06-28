"""
sources.py — turn any input (file, YouTube link, web URL) into text for the
Summarizer screen.

  - Files (.docx .pdf .txt .md .rtf, images via OCR)  -> reuse extract.py
  - EPUB (whole book)                                 -> per-chapter text
  - YouTube link                                      -> transcript (captions)
  - Web page URL                                       -> main article text

YouTube uses captions, not audio: works for the large majority of videos
(including hour-plus ones) that have manual or auto-generated captions. Videos
with captions disabled return a clear message rather than failing silently.
"""

import re

import extract  # existing file-text extractor


# ── input-type detection ──────────────────────────────────────────────────────
_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def detect_kind(text):
    """Classify a pasted string as 'youtube', 'url', or 'unknown'."""
    t = text.strip()
    if _YT_RE.search(t):
        return "youtube"
    if re.match(r"^https?://", t, re.I):
        return "url"
    return "unknown"


# ── YouTube ───────────────────────────────────────────────────────────────────
def youtube_id(link):
    m = _YT_RE.search(link)
    if m:
        return m.group(1)
    # bare 11-char id
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", link.strip()):
        return link.strip()
    return None


def fetch_youtube(link):
    """Return (text, meta). meta carries title/length info when available."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled, NoTranscriptFound, VideoUnavailable,
    )

    vid = youtube_id(link)
    if not vid:
        return "", {"error": "Could not read a video ID from that link."}

    api = YouTubeTranscriptApi()
    try:
        # Prefer English, fall back to whatever transcript exists.
        try:
            fetched = api.fetch(vid, languages=("en", "en-US", "en-GB"))
        except NoTranscriptFound:
            tlist = api.list(vid)
            transcript = None
            for t in tlist:
                transcript = t
                break
            if transcript is None:
                return "", {"error": "This video has no captions available."}
            fetched = transcript.fetch()
    except TranscriptsDisabled:
        return "", {"error": "Captions are disabled on this video, so it can't "
                             "be summarized from a transcript."}
    except VideoUnavailable:
        return "", {"error": "That video is unavailable (private, removed, or "
                             "region-locked)."}
    except Exception as e:
        return "", {"error": f"Could not fetch transcript: {e}"}

    # FetchedTranscript is iterable of snippets with .text, .start, .duration
    parts, segments, total = [], [], 0.0
    for snip in fetched:
        txt = (getattr(snip, "text", "") or "").strip()
        start = getattr(snip, "start", None)
        dur = getattr(snip, "duration", 0.0) or 0.0
        if start is None:
            start = total  # fall back to accumulated time
        if txt:
            parts.append(txt)
            segments.append({
                "t": round(float(start), 2),
                "ts": _fmt_ts(float(start)),
                "text": txt,
            })
        total = max(total, float(start) + dur)
    text = " ".join(parts)
    mins = int(total // 60)
    title = _youtube_title(vid)
    return text, {"video_id": vid, "approx_minutes": mins,
                  "title": title, "kind": "YouTube video", "segments": segments}


def _youtube_title(vid):
    """Best-effort fetch of a video's title via YouTube's public oEmbed endpoint
    (no API key needed). Returns '' if it can't be retrieved."""
    try:
        import json
        import urllib.request
        import urllib.parse
        url = ("https://www.youtube.com/oembed?url="
               + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}", safe="")
               + "&format=json")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return (data.get("title") or "").strip()
    except Exception:
        return ""


def _fmt_ts(seconds):
    """Format seconds as M:SS or H:MM:SS for transcript timestamps."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── Web page ──────────────────────────────────────────────────────────────────
def fetch_webpage(url, fetched_html=None):
    """
    Return (text, meta). Pass fetched_html if the caller already retrieved the
    page (the server does this so it controls the HTTP request).
    """
    from bs4 import BeautifulSoup

    if not fetched_html:
        return "", {"error": "No page content was retrieved."}

    soup = BeautifulSoup(fetched_html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string
             else url)

    # Strip non-content elements.
    for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                     "form", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Prefer an <article> or <main>; else fall back to body.
    main = soup.find("article") or soup.find("main") or soup.body or soup
    # Collect block-level text.
    blocks = []
    for el in main.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        txt = el.get_text(" ", strip=True)
        if len(txt) > 1:
            blocks.append(txt)
    text = "\n".join(blocks).strip()
    if len(text) < 80:  # fallback: whole-page text
        text = main.get_text("\n", strip=True)
    return text, {"title": title, "kind": "Web page"}


# ── EPUB (whole book) ─────────────────────────────────────────────────────────
def fetch_epub(path):
    """Return (text, meta) with chapter-joined text for the whole book."""
    from ebooklib import epub
    import ebooklib
    from bs4 import BeautifulSoup

    book = epub.read_epub(path)
    title = ""
    try:
        meta = book.get_metadata("DC", "title")
        if meta:
            title = meta[0][0]
    except Exception:
        pass

    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml")
        for t in soup(["script", "style"]):
            t.decompose()
        txt = soup.get_text("\n", strip=True)
        if len(txt) > 200:  # skip nav/cover/short fragments
            chapters.append(txt)
    text = "\n\n".join(chapters)
    return text, {"title": title or "EPUB book", "kind": "EPUB book",
                  "chapter_count": len(chapters)}


# ── Files (dispatch) ──────────────────────────────────────────────────────────
def fetch_file(path):
    """Return (text, meta) for an uploaded file path."""
    import os
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    if ext == ".epub":
        return fetch_epub(path)
    text, note = extract.extract_text(path)
    return text, {"title": name, "kind": ext.lstrip(".").upper() + " file",
                  "ocr": note == "ocr",
                  "error": (note if not text else None)}
