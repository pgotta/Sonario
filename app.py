"""
app.py — Anchors Aweigh server.

Single-user local Flask server + single-file SPA. Runs one analysis job at a
time in a background thread; the UI polls /status for live progress. Provider
defaults to a local Ollama model (Qwen3.5 9B). Source is a Windows folder path or
a Google Drive folder link.

Behavioral rules:
  - Never re-run a job while one is in flight.
  - The map stage is resumable via the on-disk cache; restarting after a crash
    reuses everything already analyzed.
  - On a fatal provider error during synthesis, the job stops and reports it
    rather than emitting a half-baked report.

ISOLATION CONTRACT (Drive <-> LLM provider):
  The Google Drive module (gdrive.py) and the LLM provider module (providers.py)
  never communicate. They each talk only to this app. The ONLY thing that passes
  between them is plain file text that has been written to a LOCAL temp folder by
  Drive and then read back from that local folder by extract.py. Concretely:

      Drive API  --(downloads files)-->  local temp dir  --(read by extract)-->
      plain text  --(sent by providers)-->  LLM

  - The LLM provider receives text from a local path. It carries no marker that
    the text originated in Drive; nothing references Drive in the provider call.
  - The Drive client is a standard read-only desktop OAuth client. It carries no
    marker that an LLM is downstream; nothing references the provider in the
    Drive call.
  - No shared session, credential, or header crosses the two. This separation is
    intentional and must be preserved.
"""

import os
import threading
import time
import traceback
import webbrowser
import tempfile

from flask import Flask, request, jsonify, send_from_directory, send_file

import providers
import pipeline
import extract
import export
import sources
import sysmon
import keystore

APP_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(APP_DIR, "static"))

# ---- session history (persist finished results so they survive a refresh) ----
import json as _json
import uuid as _uuid

HISTORY_DIR = os.path.join(APP_DIR, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)


def _history_save(kind, payload):
    """Persist a finished result so it can be restored later. kind is
    'analyze' or 'summary'. Returns the session id."""
    try:
        sid = _uuid.uuid4().hex[:12]
        rec = {
            "id": sid,
            "kind": kind,
            "title": payload.get("title") or payload.get("source_label") or "Untitled",
            "created": time.time(),
            "payload": payload,
        }
        with open(os.path.join(HISTORY_DIR, f"{kind}_{sid}.json"), "w",
                  encoding="utf-8") as f:
            _json.dump(rec, f, ensure_ascii=False)
        return sid
    except Exception:
        return None


def _history_list():
    """Return lightweight metadata for all saved sessions, newest first."""
    out = []
    try:
        for fn in os.listdir(HISTORY_DIR):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(HISTORY_DIR, fn), encoding="utf-8") as f:
                    rec = _json.load(f)
                out.append({"id": rec["id"], "kind": rec["kind"],
                            "title": rec.get("title", "Untitled"),
                            "created": rec.get("created", 0)})
            except Exception:
                continue
    except Exception:
        pass
    out.sort(key=lambda r: r.get("created", 0), reverse=True)
    return out


def _history_get(kind, sid):
    """Load a full saved session payload, or None."""
    try:
        with open(os.path.join(HISTORY_DIR, f"{kind}_{sid}.json"),
                  encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return None


def _history_clear():
    """Delete every saved session."""
    n = 0
    try:
        for fn in os.listdir(HISTORY_DIR):
            if fn.endswith(".json"):
                try:
                    os.remove(os.path.join(HISTORY_DIR, fn))
                    n += 1
                except Exception:
                    pass
    except Exception:
        pass
    return n


# ---- single global job state -------------------------------------------------
JOB = {
    "running": False,
    "stage": "idle",      # idle | extracting | mapping | reducing | synthesizing | done | error
    "progress": {"i": 0, "total": 0, "file": "", "status": ""},
    "log": [],
    "report_md": None,
    "prompts": None,
    "files": None,
    "mode": None,
    "mode_label": "",
    "followup_labels": None,
    "md_path": None,
    "pdf_path": None,
    "skipped": [],
    "error": None,
    "source_label": "",
}
_stop = threading.Event()
_lock = threading.Lock()


def log(msg):
    JOB["log"].append(msg)
    JOB["log"] = JOB["log"][-200:]


def _job_rate_wait(seconds):
    prefix = "Groq rate window:"
    message = (f"{prefix} waiting {seconds}s before the next call…" if seconds > 0
               else f"{prefix} ready; continuing.")
    if JOB["log"] and JOB["log"][-1].startswith(prefix): JOB["log"][-1] = message
    else: log(message)


def _build_provider(cfg, on_wait=None):
    """Build the provider the pipeline will use.

    Returns a RoutingProvider in all cases (via providers.as_router), so the
    pipeline can always use `.fast` / `.synth`. When the chosen preset is a
    routed local setup (or the UI supplies a separate fast model), the two roles
    use different models; otherwise both roles point at the same single provider
    and routing is a transparent no-op (cloud providers behave exactly as before).
    """
    pid = cfg.get("provider", "local-qwen8b")
    preset = providers.PROVIDERS.get(pid, {})

    # API key: use what the UI sent; if it's blank, fall back to a key the user
    # chose to remember (keystore). Lets you start the app and go without
    # retyping a cloud key every launch.
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key and preset.get("needs_key"):
        api_key = keystore.get_key(pid)

    # The synthesis (main) provider - the user-facing model.
    synth = providers.LLMProvider(
        provider_id=pid,
        base_url=cfg.get("base_url") or None,
        model=cfg.get("model") or None,
        api_key=api_key or None,
        on_wait=on_wait,
    )

    # Decide the fast/helper model. Priority: explicit UI value, then the preset's
    # fast_model (for routed presets like local-smart). If neither, fast == synth.
    fast_model = (cfg.get("fast_model") or "").strip() or preset.get("fast_model")
    if fast_model and fast_model != synth.model:
        fast = providers.LLMProvider(
            provider_id=pid,
            base_url=cfg.get("base_url") or None,
            model=fast_model,
            api_key=api_key or None,
            on_wait=on_wait,
        )
        return providers.RoutingProvider(synth=synth, fast=fast)

    return providers.as_router(synth)


def run_job(cfg):
    try:
        _stop.clear()
        JOB.update(stage="extracting", error=None, report_md=None, prompts=None,
                   mode=None, mode_label="", followup_labels=None,
                   md_path=None, pdf_path=None, skipped=[], log=[],
                   files=None, _raw_cache=None)
        provider = _build_provider(cfg, on_wait=_job_rate_wait)

        # ---- resolve source(s) to a combined list of files ----
        # The UI sends booleans use_folder / use_gdrive so either or BOTH can run.
        use_folder = cfg.get("use_folder", cfg.get("source_type") == "folder")
        use_gdrive = cfg.get("use_gdrive", cfg.get("source_type") == "gdrive")
        if not use_folder and not use_gdrive:
            # backward-compat: fall back to single source_type
            if cfg.get("source_type") == "gdrive":
                use_gdrive = True
            else:
                use_folder = True

        files = []
        labels = []

        if use_folder:
            root = cfg.get("folder_path", "").strip().strip('"')
            if not root or not os.path.isdir(root):
                raise RuntimeError(f"Windows folder not found: {root!r}")
            f = extract.walk_folder(root)
            log(f"Windows folder: found {len(f)} supported file(s).")
            files.extend(f)
            labels.append(root)

        if use_gdrive:
            import gdrive
            link = cfg.get("gdrive_link", "")
            fid = gdrive.folder_id_from_link(link)
            if not fid:
                raise RuntimeError("Could not read a folder ID from that Drive link.")
            log("Connecting to Google Drive…")
            local_dir, n = gdrive.download_folder(
                fid, progress=lambda d: log(
                    f"Downloaded: {d.get('file','?')}" if "error" not in d
                    else f"Drive error on {d.get('file','?')}: {d['error']}"))
            f = extract.walk_folder(local_dir)
            log(f"Google Drive: downloaded {n}, found {len(f)} supported file(s).")
            files.extend(f)
            labels.append("Google Drive folder")

        JOB["source_label"] = " + ".join(labels) if labels else "documents"

        if not files:
            raise RuntimeError("No supported documents found in the selected source(s).")
        log(f"Total: {len(files)} supported file(s) across {len(labels)} source(s).")
        JOB["progress"] = {"i": 0, "total": len(files), "file": "", "status": ""}

        # ---- RESOLVE INTERPRETATION MODE ----
        import modes as modes_mod
        requested = cfg.get("mode", "auto")
        if requested == "auto":
            JOB["stage"] = "classifying"
            log("Auto: sampling documents to pick an interpretation lens…")
            samples = []
            for pth in files[:8]:
                txt, _ = extract.extract_text(pth)
                if txt and len(txt.strip()) >= 40:
                    samples.append(txt)
                if len(samples) >= 6:
                    break
            mode = modes_mod.classify_mode(provider, samples)
            log(f"Auto-selected lens: {modes_mod.MODES[mode]['label']}")
        else:
            mode = requested if requested in modes_mod.MODES else "general"
        mode_cfg = modes_mod.resolve(mode)
        JOB["mode"] = mode
        JOB["mode_label"] = modes_mod.MODES[mode]["label"]
        map_system = pipeline._map_system(mode_cfg)

        # ---- MAP (throttled, cached, resumable) ----
        JOB["stage"] = "mapping"

        def on_prog(d):
            JOB["progress"] = d
            if d["status"] in ("done", "ocr"):
                log(f"[{d['i']}/{d['total']}] analyzed {d['file']}")
            elif d["status"] == "fallback":
                if d.get("fallback") == "compact":
                    log(f"[{d['i']}/{d['total']}] analyzed {d['file']} (JSON recovered)")
                else:
                    log(f"[{d['i']}/{d['total']}] included {d['file']} (local fallback)")
            elif d["status"] == "cached":
                log(f"[{d['i']}/{d['total']}] cached {d['file']}")
            elif d["status"] == "skipped":
                log(f"[{d['i']}/{d['total']}] skipped {d['file']} ({d.get('reason','')})")
            elif d["status"] == "error":
                log(f"[{d['i']}/{d['total']}] error {d['file']}: {d.get('reason','')}")

        notes, skipped = pipeline.run_map(
            provider, files, progress=on_prog, stop_flag=_stop.is_set,
            map_system=map_system)
        JOB["skipped"] = skipped
        JOB["files"] = list(files)  # kept for the follow-up Q&A (raw retrieval)

        if _stop.is_set():
            JOB.update(stage="idle", running=False)
            log("Stopped by user.")
            return
        if not notes:
            raise RuntimeError("No documents could be analyzed (all skipped or empty).")

        # ---- REDUCE (local, free) ----
        JOB["stage"] = "reducing"
        log(f"Aggregating patterns across {len(notes)} document(s)…")
        reduced = pipeline.reduce_notes(notes)
        gists = [n["gist"] for n in notes if n.get("gist")]

        # ---- SYNTHESIZE ----
        JOB["stage"] = "synthesizing"
        log("Writing your insight report…")
        report = pipeline.synthesize(provider, reduced, sample_gists=gists,
                                     mode_cfg=mode_cfg)
        JOB["report_md"] = report

        # ---- FOLLOW-UPS (separate pass, framing depends on mode) ----
        JOB["stage"] = "prompting"
        log("Drafting follow-ups from what recurs…")
        prompts = None
        try:
            prompts = pipeline.generate_prompts(provider, reduced, mode=mode)
            JOB["prompts"] = prompts
            JOB["followup_labels"] = pipeline.FOLLOWUP_LABELS.get(mode)
        except Exception as e:
            log(f"Follow-up generation skipped: {e}")  # non-fatal

        # ---- EXPORT ----
        full_md = report + (pipeline.prompts_to_markdown(prompts, mode=mode) if prompts else "")
        md_path = export.save_markdown(full_md, JOB["source_label"])
        pdf_path = None
        try:
            pdf_path = export.save_pdf(full_md, JOB["source_label"])
        except Exception as e:
            log(f"PDF export failed (Markdown still saved): {e}")
        JOB["md_path"], JOB["pdf_path"] = md_path, pdf_path
        JOB["stage"] = "done"
        log("Done. Report ready.")
        # persist so it can be restored later (these runs can take 20-30 min)
        _history_save("analyze", {
            "source_label": JOB.get("source_label", ""),
            "title": JOB.get("source_label", "") or "Analysis",
            "report_md": JOB.get("report_md"),
            "prompts": JOB.get("prompts"),
            "followup_labels": JOB.get("followup_labels"),
            "mode": JOB.get("mode"),
            "mode_label": JOB.get("mode_label", ""),
        })
    except Exception as e:
        JOB["stage"] = "error"
        JOB["error"] = str(e)
        log("ERROR: " + str(e))
        traceback.print_exc()
    finally:
        JOB["running"] = False


# ---- routes ------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/providers")
def api_providers():
    return jsonify({k: {kk: vv for kk, vv in v.items()}
                    for k, v in providers.PROVIDERS.items()})


@app.route("/api/keys")
def api_keys():
    """Which providers have a remembered key (never returns the keys themselves)."""
    try:
        return jsonify({"saved": keystore.saved_providers()})
    except Exception:
        return jsonify({"saved": []})


@app.route("/api/keys/save", methods=["POST"])
def api_keys_save():
    """Remember (or update) an API key for a provider, at the user's request.

    The key is written in plain text to credentials/api_keys.json - see
    keystore.py for the honest security note. Opt-in only: the UI calls this when
    the user ticks "Remember".
    """
    data = request.get_json(force=True) or {}
    pid = (data.get("provider") or "").strip()
    key = (data.get("api_key") or "").strip()
    if not pid:
        return jsonify({"ok": False, "message": "No provider given."})
    if not key:
        return jsonify({"ok": False, "message": "No key given."})
    ok = keystore.save_key(pid, key)
    return jsonify({"ok": ok,
                    "message": "Key remembered." if ok else "Could not save the key."})


@app.route("/api/keys/forget", methods=["POST"])
def api_keys_forget():
    """Delete a remembered key."""
    data = request.get_json(force=True) or {}
    pid = (data.get("provider") or "").strip()
    if not pid:
        return jsonify({"ok": False, "message": "No provider given."})
    ok = keystore.forget_key(pid)
    return jsonify({"ok": ok, "message": "Key forgotten." if ok else "Could not remove the key."})


@app.route("/api/keys/get", methods=["POST"])
def api_keys_get():
    """Return a remembered key so the UI can prefill the box on load.

    This only ever serves 127.0.0.1 (single-user local app), and only returns a
    key the user explicitly chose to save on this machine.
    """
    data = request.get_json(force=True) or {}
    pid = (data.get("provider") or "").strip()
    return jsonify({"api_key": keystore.get_key(pid) if pid else ""})


@app.route("/api/sysload")
def api_sysload():
    """Live CPU / GPU / RAM load for the on-screen meter. Always 200, never raises."""
    try:
        return jsonify(sysmon.read())
    except Exception:
        return jsonify({"cpu_percent": None, "ram_percent": None,
                        "gpu_available": False})


@app.route("/api/modes")
def api_modes():
    import modes as modes_mod
    return jsonify({k: {"label": v["label"], "blurb": v.get("blurb", "")}
                    for k, v in modes_mod.MODES.items()})


@app.route("/api/gdrive_status")
def gdrive_status():
    try:
        import gdrive
        status = gdrive.connection_status()
        return jsonify({"credentials_present": gdrive.credentials_present(),
                        "creds_dir": gdrive.CREDS_DIR,
                        "state": status["state"],
                        "status_message": status["message"]})
    except Exception as e:
        return jsonify({"credentials_present": False, "state": "error",
                        "error": str(e)})


@app.route("/api/gdrive_connect", methods=["POST"])
def gdrive_connect():
    """Run/redo the Google Drive authorization. Opens the system browser to the
    Google consent screen (deliberate user action), so we allow the OAuth flow
    here. Used for first sign-in and for re-authorizing after a token expires."""
    try:
        import gdrive
        if not gdrive.credentials_present():
            return jsonify({"ok": False,
                            "message": "Add credentials.json first (see the setup guide)."})
        os.environ["SONARIO_ALLOW_OAUTH"] = "1"
        try:
            gdrive.get_service()  # opens browser if needed, saves fresh token.json
        finally:
            os.environ["SONARIO_ALLOW_OAUTH"] = ""
        return jsonify({"ok": True, "message": "Connected to Google Drive."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)[:200]})


@app.route("/api/test_provider", methods=["POST"])
def test_provider():
    cfg = request.get_json(force=True)
    try:
        prov = _build_provider(cfg)
        ok, msg = providers.check_provider(prov)
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/api/ask", methods=["POST"])
def ask():
    """Answer a user's question about the most recent summary or folder analysis."""
    data = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    scope = data.get("scope", "summary")  # 'summary' | 'analyze'
    if not question:
        return jsonify({"ok": False, "message": "Please type a question."})
    try:
        prov = _build_provider(data)
        if scope == "analyze":
            report = JOB.get("report_md") or ""
            if not report and not JOB.get("files"):
                return jsonify({"ok": False, "message": "Run an analysis first."})
            # Build (and cache) raw context from the analyzed files so questions can
            # dig into the actual document text, not just the synthesized report.
            context = JOB.get("_raw_cache")
            if not context:
                raw_parts, total = [], 0
                CAP = 600000  # ~600k chars of raw text across the collection
                for pth in (JOB.get("files") or []):
                    if total >= CAP:
                        break
                    try:
                        txt, _flag = extract.extract_text(pth)
                    except Exception:
                        txt = ""
                    if txt:
                        block = f"\n\n===== {os.path.basename(pth)} =====\n{txt}"
                        raw_parts.append(block)
                        total += len(block)
                context = "".join(raw_parts) if raw_parts else report
                JOB["_raw_cache"] = context
            extra = report  # report gives the model orientation
        else:
            context = SUM.get("source_text") or ""
            extra = SUM.get("summary_md") or ""
            if not context and not extra:
                return jsonify({"ok": False, "message": "Summarize something first."})
        result = pipeline.answer_question(prov, question, context, extra=extra)
        answer = result.get("answer", "") if isinstance(result, dict) else result
        citations = result.get("citations", []) if isinstance(result, dict) else []

        # For a YouTube transcript, map each citation's char offset to the nearest
        # segment timestamp so the UI can make it a clickable jump. The transcript
        # text is " ".join(segment texts), so we can rebuild each segment's start
        # offset and find which segment a citation falls in.
        segments = SUM.get("segments") if scope != "analyze" else None
        if citations and segments:
            bounds = []  # (char_start, ts, t_seconds)
            pos = 0
            for seg in segments:
                bounds.append((pos, seg.get("ts", ""), seg.get("t", 0)))
                pos += len(seg.get("text", "")) + 1  # +1 for the joining space
            for c in citations:
                cs = c.get("char_start", 0)
                # find the last segment whose start offset is <= the citation
                ts, tsec = "", 0
                for b_start, b_ts, b_t in bounds:
                    if b_start <= cs:
                        ts, tsec = b_ts, b_t
                    else:
                        break
                c["ts"] = ts
                c["t"] = tsec

        return jsonify({"ok": True, "answer": answer, "citations": citations})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/api/history")
def history_list():
    return jsonify({"sessions": _history_list()})


@app.route("/api/history/<kind>/<sid>")
def history_get(kind, sid):
    rec = _history_get(kind, sid)
    if not rec:
        return jsonify({"ok": False, "message": "Session not found."}), 404
    payload = rec.get("payload", {})
    # Rehydrate the live state for this kind so the ask-a-question box works on a
    # restored session (it reads from JOB / SUM). Only do this when no run is
    # currently in progress, so we never clobber an active job.
    try:
        if kind == "summary" and not SUM.get("running"):
            SUM["summary_md"] = payload.get("summary_md")
            SUM["bullets_md"] = payload.get("bullets_md")
            SUM["detailed_md"] = payload.get("detailed_md")
            SUM["chapter_md"] = payload.get("chapter_md")
            SUM["source_text"] = payload.get("source_text")
            SUM["source_label"] = payload.get("source_label", "")
            SUM["title"] = payload.get("title", "")
            SUM["is_youtube"] = payload.get("is_youtube", False)
            SUM["video_id"] = payload.get("video_id")
            SUM["segments"] = payload.get("segments")
        elif kind == "analyze" and JOB.get("stage") != "extracting" and not JOB.get("running"):
            JOB["report_md"] = payload.get("report_md")
            JOB["prompts"] = payload.get("prompts")
            JOB["followup_labels"] = payload.get("followup_labels")
            JOB["_raw_cache"] = None  # restored sessions answer from the report
    except Exception:
        pass
    return jsonify({"ok": True, "kind": rec["kind"], "title": rec.get("title"),
                    "payload": payload})


@app.route("/api/history/clear", methods=["POST"])
def history_clear():
    n = _history_clear()
    return jsonify({"ok": True, "cleared": n})


@app.route("/api/start", methods=["POST"])
def start():
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "A job is already running."}), 409
        cfg = request.get_json(force=True)
        JOB["running"] = True
    threading.Thread(target=run_job, args=(cfg,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop():
    _stop.set()
    return jsonify({"ok": True})


@app.route("/api/status")
def status():
    return jsonify({
        "running": JOB["running"], "stage": JOB["stage"],
        "progress": JOB["progress"], "log": JOB["log"][-60:],
        "error": JOB["error"], "skipped": JOB["skipped"],
        "report_md": JOB["report_md"] if JOB["stage"] == "done" else None,
        "prompts": JOB["prompts"] if JOB["stage"] == "done" else None,
        "mode": JOB["mode"], "mode_label": JOB["mode_label"],
        "followup_labels": JOB["followup_labels"] if JOB["stage"] == "done" else None,
        "has_pdf": bool(JOB["pdf_path"]),
        "source_label": JOB["source_label"],
    })


@app.route("/api/download/<kind>")
def download(kind):
    path = JOB["md_path"] if kind == "md" else JOB["pdf_path"]
    if not path or not os.path.exists(path):
        return "Not ready", 404
    return send_file(path, as_attachment=True)


# ============================================================================
#  SUMMARIZER  — separate screen. Upload a file / paste a YouTube or web link,
#  get a one-page summary. Runs as its own background job (books and long videos
#  take time), independent of the Analyze Collection job above.
# ============================================================================
SUM = {
    "running": False, "stage": "idle", "detail": "",
    "summary_md": None, "md_path": None, "pdf_path": None,
    "bullets_md": None, "detailed_md": None, "chapter_md": None,
    "source_label": "", "title": "", "error": None,
    "is_youtube": False, "video_id": None, "segments": None,
    "source_text": None,
    # progress tracking for the bar + ETA
    "cur": 0, "total": 0, "phase": "", "started": 0.0, "eta_sec": None, "reduce_step": 0,
}
_sum_lock = threading.Lock()


def _summary_rate_wait(seconds):
    if seconds > 0:
        SUM["stage"] = "rate_wait"; SUM["detail"] = f"Groq rate window: continuing in {seconds}s…"
    elif SUM.get("stage") == "rate_wait":
        SUM["stage"] = SUM.get("phase") or "summarizing"; SUM["detail"] = "Groq rate window ready; continuing…"


def _fmt_eta(sec):
    """Human ETA string from seconds remaining."""
    if sec is None or sec < 0:
        return None
    sec = int(sec)
    if sec < 60:
        return f"about {max(sec, 5)}s left"
    m = sec // 60
    if m < 60:
        return f"about {m} min left" if sec % 60 < 30 else f"about {m+1} min left"
    h, m = divmod(m, 60)
    return f"about {h}h {m}m left"


def _sum_progress(d):
    ph = d.get("phase", "")
    now = time.time()
    if ph == "condensing":
        cur, total = d["chunk"], d["chunks"]
        SUM["stage"] = "condensing"
        SUM["phase"] = "condensing"
        SUM["cur"], SUM["total"] = cur, total
        # ETA from average time per completed chunk
        if SUM["started"] and cur > 1:
            per = (now - SUM["started"]) / (cur - 1)
            SUM["eta_sec"] = per * (total - cur + 1)
        SUM["detail"] = f"Reading section {cur} of {total}…"
        eta = _fmt_eta(SUM["eta_sec"])
        if eta:
            SUM["detail"] += f"  ({eta})"
    elif ph == "synthesizing":
        SUM["stage"] = "synthesizing"
        SUM["phase"] = "synthesizing"
        SUM["eta_sec"] = None  # not reliably predictable in this phase
        if d.get("final"):
            # the single final write of the one-page summary
            SUM["detail"] = "Writing the one-page summary…"
        elif d.get("reduce_step"):
            # cumulative, ever-increasing count so it never looks like it went back
            step = d["reduce_step"]
            SUM["cur"] = step
            SUM["reduce_step"] = step
            SUM["detail"] = (f"Condensing a long source, this part takes a while "
                             f"(step {step})…")
        else:
            SUM["detail"] = "Writing the summary…"
    elif ph == "finalizing":
        SUM["stage"] = "synthesizing"
        SUM["phase"] = "finalizing"
        SUM["detail"] = "Finishing up, preparing the bulleted view…"
        SUM["eta_sec"] = None
    elif ph == "detailing":
        SUM["stage"] = "synthesizing"
        SUM["phase"] = "finalizing"
        SUM["detail"] = "Writing the long Detailed version…"
        SUM["eta_sec"] = None
    elif ph == "chapters":
        SUM["stage"] = "synthesizing"
        SUM["phase"] = "finalizing"
        c = d.get("chunk"); t = d.get("chunks")
        SUM["detail"] = (f"Summarizing chapter {c} of {t}…" if c and t
                         else "Summarizing each chapter…")
        SUM["eta_sec"] = None
    elif ph == "summarizing":
        SUM["stage"] = "summarizing"
        SUM["phase"] = "summarizing"
        SUM["detail"] = "Summarizing…"


def run_summary(cfg):
    try:
        SUM.update(stage="fetching", error=None, summary_md=None,
                   md_path=None, pdf_path=None, detail="", source_label="", title="",
                   bullets_md=None,
                   is_youtube=False, video_id=None, segments=None,
                   cur=0, total=0, phase="", started=0.0, eta_sec=None, reduce_step=0)
        provider = _build_provider(cfg, on_wait=_summary_rate_wait)
        intype = cfg.get("input_type")  # 'file' | 'link'

        if intype == "file":
            path = cfg.get("file_path", "")
            if not path or not os.path.exists(path):
                raise RuntimeError("Uploaded file not found.")
            text, meta = sources.fetch_file(path)
        else:
            link = (cfg.get("link") or "").strip()
            kind = sources.detect_kind(link)
            if kind == "youtube":
                SUM["detail"] = "Fetching video transcript…"
                text, meta = sources.fetch_youtube(link)
            elif kind == "url":
                SUM["detail"] = "Fetching web page…"
                html = _fetch_url_html(link)
                text, meta = sources.fetch_webpage(link, fetched_html=html)
            else:
                raise RuntimeError("That doesn't look like a YouTube or web link.")

        if meta.get("error"):
            raise RuntimeError(meta["error"])
        if not text or len(text.strip()) < 40:
            raise RuntimeError("Couldn't extract enough text to summarize.")

        # For YouTube, carry the timestamped transcript through for the reader view.
        if meta.get("segments"):
            SUM["is_youtube"] = True
            SUM["video_id"] = meta.get("video_id")
            SUM["segments"] = meta["segments"]

        SUM["title"] = (meta.get("title") or "").strip()
        SUM["source_label"] = pipeline.summary_header(meta) or "Summary"
        SUM["stage"] = "summarizing"
        SUM["started"] = time.time()
        result = pipeline.summarize_text(provider, text, meta=meta,
                                         progress=_sum_progress)
        # result is {"full":..., "bullets":..., "detailed":...}
        summary = result.get("full", "") if isinstance(result, dict) else result
        bullets = result.get("bullets", "") if isinstance(result, dict) else ""
        detailed = result.get("detailed", "") if isinstance(result, dict) else ""
        SUM["summary_md"] = summary
        SUM["bullets_md"] = bullets
        SUM["detailed_md"] = detailed
        SUM["source_text"] = text  # kept for the follow-up Q&A box

        # EPUBs carry per-chapter text: generate a chapter-by-chapter summary for
        # the "Chapter" toggle. Only EPUBs have this; other sources leave it empty.
        chapters = meta.get("chapters") or []
        if chapters:
            try:
                SUM["chapter_md"] = pipeline.summarize_chapters(
                    provider, chapters, progress=_sum_progress)
            except Exception:
                SUM["chapter_md"] = ""
        else:
            SUM["chapter_md"] = ""

        head = pipeline.summary_header(meta)
        full_md = (f"# Summary\n\n_{head}_\n\n" if head else "# Summary\n\n") + summary
        SUM["md_path"] = export.save_markdown(full_md, SUM["source_label"])
        try:
            SUM["pdf_path"] = export.save_pdf(full_md, SUM["source_label"])
        except Exception:
            SUM["pdf_path"] = None
        SUM["stage"] = "done"
        # persist so it can be restored later (long videos/books take a while)
        _history_save("summary", {
            "source_label": SUM.get("source_label", ""),
            "title": SUM.get("title") or SUM.get("source_label") or "Summary",
            "summary_md": SUM.get("summary_md"),
            "bullets_md": SUM.get("bullets_md"),
            "detailed_md": SUM.get("detailed_md"),
            "chapter_md": SUM.get("chapter_md"),
            "source_text": SUM.get("source_text"),
            "is_youtube": SUM.get("is_youtube", False),
            "video_id": SUM.get("video_id"),
            "segments": SUM.get("segments"),
        })
    except Exception as e:
        SUM["stage"] = "error"
        SUM["error"] = str(e)
        traceback.print_exc()
    finally:
        SUM["running"] = False


def _fetch_url_html(url):
    """Server-side page fetch with a normal UA. Kept here so the source module
    stays free of network concerns."""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AnchorsAwai/1.0)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


@app.route("/api/summarize", methods=["POST"])
def summarize():
    with _sum_lock:
        if SUM["running"]:
            return jsonify({"ok": False, "message": "A summary is already running."}), 409
        SUM["running"] = True

    intype = request.form.get("input_type", "link")
    cfg = {
        "provider": request.form.get("provider", "local-qwen8b"),
        "model": request.form.get("model", ""),
        "fast_model": request.form.get("fast_model", ""),
        "base_url": request.form.get("base_url", ""),
        "api_key": request.form.get("api_key", ""),
        "input_type": intype,
        "link": request.form.get("link", ""),
    }

    if intype == "file":
        f = request.files.get("file")
        if not f or not f.filename:
            SUM["running"] = False
            return jsonify({"ok": False, "message": "No file uploaded."}), 400
        tmpdir = tempfile.mkdtemp(prefix="anchors_sum_")
        safe = os.path.basename(f.filename).replace("/", "_").replace("\\", "_")
        dest = os.path.join(tmpdir, safe)
        f.save(dest)
        cfg["file_path"] = dest

    threading.Thread(target=run_summary, args=(cfg,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/summary_status")
def summary_status():
    done = SUM["stage"] == "done"
    # progress percentage: bias most of the bar to the condensing phase, which
    # is the long part of a big book; the final fold takes the last slice.
    pct = 0
    st = SUM["stage"]
    if st == "fetching":
        pct = 8
    elif st in ("summarizing",):
        pct = 20
    elif st == "condensing" and SUM["total"]:
        pct = 15 + int((SUM["cur"] / SUM["total"]) * 70)  # 15→85%
    elif st == "synthesizing":
        if SUM["phase"] == "finalizing":
            pct = 95
        else:
            step = SUM.get("reduce_step", 0) or 0
            pct = 86 + int(8 * (1 - (0.78 ** step)))
    elif done:
        pct = 100
    return jsonify({
        "running": SUM["running"], "stage": SUM["stage"], "detail": SUM["detail"],
        "error": SUM["error"], "source_label": SUM["source_label"],
        "title": SUM["title"],
        "summary_md": SUM["summary_md"] if done else None,
        "bullets_md": SUM["bullets_md"] if done else None,
        "detailed_md": SUM["detailed_md"] if done else None,
        "chapter_md": SUM["chapter_md"] if done else None,
        "has_pdf": bool(SUM["pdf_path"]),
        "is_youtube": SUM["is_youtube"] if done else False,
        "video_id": SUM["video_id"] if done else None,
        "segments": SUM["segments"] if done else None,
        "pct": pct, "cur": SUM["cur"], "total": SUM["total"],
        "phase": SUM["phase"], "eta": _fmt_eta(SUM["eta_sec"]),
    })


@app.route("/api/summary_download/<kind>")
def summary_download(kind):
    path = SUM["md_path"] if kind == "md" else SUM["pdf_path"]
    if not path or not os.path.exists(path):
        return "Not ready", 404
    return send_file(path, as_attachment=True)


def main():
    port = int(os.environ.get("PORT", "5005"))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Sonario running at {url}\n")
    # The Windows desktop launcher opens Sonario in its own app window. Keep the
    # normal browser-opening behavior when app.py is run directly for development.
    no_browser = os.environ.get("SONARIO_NO_BROWSER", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not no_browser:
        try:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
