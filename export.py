"""
export.py — write the report to .md and .pdf.

PDF uses reportlab (pure-Python, no system deps) so it works on a fresh Windows
box with just pip. We render the Markdown report into a clean styled PDF.
"""

import os
import re
import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _slug(source_label):
    """Turn a source label into a short, safe, descriptive filename prefix.

    The label may be a folder path, a document/video title, or - when several
    folders were analyzed at once - a "A + B + C" string. We want the filename to
    say WHAT was analyzed:
      - multiple sources joined by " + "  -> use just the first one
      - a path                            -> use its final folder/file name
      - a title                           -> cleaned up
    Falls back to 'report' if nothing usable. Always returns a filesystem-safe,
    length-capped string.
    """
    s = (source_label or "").strip()
    if not s:
        return "report"
    # Strip Markdown bold markers the summary header uses around the title.
    s = s.replace("**", "")
    # If several sources/fields were combined, keep only the FIRST piece - that's
    # the folder name or the document/video title; the rest is metadata or extra
    # folders we deliberately drop ("if it's more than one folder just pick one").
    for sep in (" · ", " + ", " | ", ", "):
        if sep in s:
            s = s.split(sep)[0].strip()
            break
    # Strip a leading descriptor some labels carry (e.g. "Folder: ", "Video: ").
    s = re.sub(r"^(folder|video|document|file|source|youtube)\s*[:\-]\s*", "",
               s, flags=re.IGNORECASE).strip()
    # If it looks like a path, take the last component (the folder/file name).
    if ("\\" in s) or ("/" in s):
        s = re.split(r"[\\/]", s.rstrip("\\/"))[-1] or s
    # Drop a file extension if present.
    s = re.sub(r"\.(txt|md|pdf|docx?|epub|html?)$", "", s, flags=re.IGNORECASE)
    # Keep letters, numbers, spaces, dashes; collapse the rest to underscores.
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"[\s]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        return "report"
    return s[:60]  # keep filenames sane


def save_markdown(report_md, source_label=""):
    name = f"{_slug(source_label)}_{_stamp()}.md"
    path = os.path.join(OUTPUT_DIR, name)
    header = f"<!-- Source: {source_label} | Generated: {datetime.datetime.now():%Y-%m-%d %H:%M} -->\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + report_md)
    return path


def save_pdf(report_md, source_label=""):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    ListFlowable, ListItem)

    name = f"{_slug(source_label)}_{_stamp()}.pdf"
    path = os.path.join(OUTPUT_DIR, name)

    doc = SimpleDocTemplate(path, pagesize=LETTER,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            title="Insight Report")
    ss = getSampleStyleSheet()
    accent = colors.HexColor("#2f6f6a")

    h1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=22, leading=26,
                        textColor=colors.HexColor("#1a2421"), spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, leading=18,
                        textColor=accent, spaceBefore=16, spaceAfter=6)
    body = ParagraphStyle("Body", parent=ss["BodyText"], fontSize=10.5,
                          leading=15.5, spaceAfter=8)
    meta = ParagraphStyle("Meta", parent=ss["Normal"], fontSize=8.5,
                          textColor=colors.HexColor("#8a8a8a"), spaceAfter=18)

    flow = [Paragraph("Insight Report", h1)]
    sub = source_label or "Personal document collection"
    flow.append(Paragraph(f"{sub} &nbsp;·&nbsp; {datetime.datetime.now():%B %d, %Y}", meta))

    bullet_buffer = []

    def flush_bullets():
        if bullet_buffer:
            items = [ListItem(Paragraph(_md_inline(b), body), leftIndent=10)
                     for b in bullet_buffer]
            flow.append(ListFlowable(items, bulletType="bullet", start="•",
                                     leftIndent=14))
            flow.append(Spacer(1, 4))
            bullet_buffer.clear()

    for line in report_md.splitlines():
        s = line.rstrip()
        if not s.strip():
            flush_bullets()
            continue
        if s.startswith("## "):
            flush_bullets()
            flow.append(Paragraph(_md_inline(s[3:]), h2))
        elif s.startswith("# "):
            flush_bullets()
            flow.append(Paragraph(_md_inline(s[2:]), h1))
        elif re.match(r"^\s*[-*]\s+", s):
            bullet_buffer.append(re.sub(r"^\s*[-*]\s+", "", s))
        elif re.match(r"^\s*\d+\.\s+", s):
            bullet_buffer.append(re.sub(r"^\s*\d+\.\s+", "", s))
        else:
            flush_bullets()
            flow.append(Paragraph(_md_inline(s), body))
    flush_bullets()

    doc.build(flow)
    return path


def _md_inline(text):
    """Minimal inline markdown -> reportlab markup (bold, italic). Escapes &<>."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return text
