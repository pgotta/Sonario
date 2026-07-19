from pathlib import Path

path = Path("BUILD.md")
text = path.read_text(encoding="utf-8")
old = """> **The `.bat` launchers are gitignored** (kept out of the GitHub repo). If you
> cloned the repo and don't have them, recreate each one by pasting the contents
> below into a file of the same name in the project root. Save them with **CRLF**
> line endings (Windows Notepad does this by default). The downloadable zip already
> includes them, so a zip user can skip this.
"""
new = """> **`setup_all.bat` and `run.bat` are tracked in Git.** They are included in
> normal clones, GitHub source archives, and packaged ZIPs, so a fresh download is
> ready for Windows setup and launch. `.gitattributes` forces Windows CRLF line
> endings for batch files. Other personal `.bat` helpers remain ignored.
"""
if old not in text:
    raise SystemExit("Expected BUILD.md launcher note was not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
