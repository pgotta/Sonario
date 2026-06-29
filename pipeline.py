"""
pipeline.py — the four-stage engine.

  1. walk & extract     (extract.py)
  2. MAP    each doc -> structured JSON note   [throttled, cached, resumable]
  3. REDUCE aggregate notes in pure Python     [deterministic, free]
  4. SYNTHESIZE the page-long report           [1-2 LLM calls]

The map stage is the only expensive part and the only place the Copilot rate
limit bites. Every note is cached to cache/<hash>.json, so a crash at doc 180
re-uses the first 179 on the next run. Nothing is ever silently re-done.
"""

import os
import json
import collections

from extract import walk_folder, extract_text, file_hash
import modes as modes_mod

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Cap text sent per doc so one huge file can't blow the context window.
MAX_CHARS_PER_DOC = 12000


def _map_system(mode_cfg):
    """Build the map-stage system prompt for a given mode config."""
    hint = mode_cfg.get("map_hint", "You are reading one document.")
    return (
        hint + " Return ONLY a JSON object, no prose, no markdown fences. "
        "Be faithful to the text; do not invent. Use this exact schema:\n"
        "{\n"
        '  "gist": "1-2 sentence summary",\n'
        '  "themes": ["short topic labels, 1-4 words each"],\n'
        '  "valence": "positive | negative | mixed | neutral",\n'
        '  "energy_sources": ["see instructions above for what to record here"],\n'
        '  "friction_sources": ["see instructions above for what to record here"],\n'
        '  "ideas": ["distinct ideas, projects, or concepts mentioned"],\n'
        '  "action_items": ["concrete next steps mentioned or implied"],\n'
        '  "people": ["names or roles of other people referenced"]\n'
        "}\n"
        "Keep every list to at most 6 items. Use [] for empty lists."
    )


# Default (journal) system prompt kept for backward compatibility / direct calls.
MAP_SYSTEM = _map_system(modes_mod.MODES["journal"])


def map_document(provider, text, map_system=None):
    """One LLM call -> structured note dict. Raises on hard failure.

    Per-document work runs once per file (dozens to hundreds of times per job),
    so it routes to the FAST helper model when one is configured.
    """
    fast = getattr(provider, "fast", provider)
    sys_prompt = map_system or MAP_SYSTEM
    cap = MAX_CHARS_PER_DOC
    snippet = text[:cap]
    user = f"Document:\n\"\"\"\n{snippet}\n\"\"\""
    note = fast.chat_json(sys_prompt, user)
    if not isinstance(note, dict):
        # one corrective retry with a blunt instruction
        note = fast.chat_json(
            sys_prompt,
            user + "\n\nReturn ONLY the JSON object. No other text.",
        )
    if not isinstance(note, dict):
        raise RuntimeError("model did not return valid JSON")
    return _normalize_note(note)


def _normalize_note(note):
    keys_list = ["themes", "energy_sources", "friction_sources",
                 "ideas", "action_items", "people"]
    out = {"gist": str(note.get("gist", "")).strip(),
           "valence": str(note.get("valence", "neutral")).strip().lower()}
    for k in keys_list:
        v = note.get(k, [])
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            v = []
        out[k] = [str(x).strip() for x in v if str(x).strip()][:6]
    if out["valence"] not in {"positive", "negative", "mixed", "neutral"}:
        out["valence"] = "neutral"
    return out


def cached_note_path(h):
    return os.path.join(CACHE_DIR, f"{h}.json")


def run_map(provider, files, progress=None, stop_flag=None, map_system=None):
    """
    Map every file, using cache. Yields nothing; calls progress(dict) per file.
    Returns (notes, skipped) where notes is a list of per-doc records.
    """
    notes = []
    skipped = []
    total = len(files)
    for i, path in enumerate(files):
        if stop_flag and stop_flag():
            break
        rel = os.path.basename(path)
        h = file_hash(path)
        cache_path = cached_note_path(h)

        # Resume: reuse cached note if present.
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                notes.append(rec)
                if progress:
                    progress({"i": i + 1, "total": total, "file": rel,
                              "status": "cached"})
                continue
            except Exception:
                pass  # corrupt cache -> recompute

        text, note_flag = extract_text(path)
        if not text or len(text.strip()) < 15:
            skipped.append({"file": rel, "reason": note_flag or "empty/too short"})
            if progress:
                progress({"i": i + 1, "total": total, "file": rel,
                          "status": "skipped", "reason": note_flag})
            continue

        try:
            note = map_document(provider, text, map_system=map_system)
        except Exception as e:
            skipped.append({"file": rel, "reason": f"map failed: {e}"})
            if progress:
                progress({"i": i + 1, "total": total, "file": rel,
                          "status": "error", "reason": str(e)[:120]})
            continue

        rec = {"file": rel, "path": path, "hash": h,
               "ocr": note_flag == "ocr", "words": len(text.split()), **note}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        notes.append(rec)
        if progress:
            progress({"i": i + 1, "total": total, "file": rel, "status": "done"})
    return notes, skipped


def _tally(notes, field):
    c = collections.Counter()
    for n in notes:
        for item in n.get(field, []):
            c[item.strip().lower()] += 1
    return c


def reduce_notes(notes):
    """Pure-Python aggregation. No LLM. This is the differentiator."""
    if not notes:
        return {}

    themes = _tally(notes, "themes")
    energy = _tally(notes, "energy_sources")
    friction = _tally(notes, "friction_sources")
    ideas = _tally(notes, "ideas")
    actions = _tally(notes, "action_items")
    people = _tally(notes, "people")

    valence_counts = collections.Counter(n.get("valence", "neutral") for n in notes)

    # "Repeated" = appears across multiple documents.
    repeated_themes = [(k, v) for k, v in themes.most_common() if v >= 2]
    repeated_ideas = [(k, v) for k, v in ideas.most_common() if v >= 2]

    return {
        "doc_count": len(notes),
        "ocr_count": sum(1 for n in notes if n.get("ocr")),
        "valence_counts": dict(valence_counts),
        "top_themes": themes.most_common(12),
        "repeated_themes": repeated_themes,
        "top_energy": energy.most_common(10),
        "top_friction": friction.most_common(10),
        "top_ideas": ideas.most_common(12),
        "repeated_ideas": repeated_ideas,
        "top_actions": actions.most_common(12),
        "top_people": people.most_common(10),
    }


_NO_DASH_RULE = (
    " IMPORTANT STYLE RULE: never use em dashes or en dashes anywhere in your "
    "output. Do not use the characters '\u2014' or '\u2013'. Use a comma, a colon, "
    "or a plain hyphen instead. This is a strict requirement."
)

SYNTH_SYSTEM = (
    "You are a thoughtful analyst writing a personal insight report for someone "
    "who has handed you a body of their own journal entries, notes, and idea "
    "scribbles. You are given a structured aggregation of patterns already "
    "computed across all their documents. Write a warm, honest, specific report "
    "of roughly 500-700 words in Markdown with these sections:\n\n"
    "## Introduction: what this collection is, scope, overall tone.\n"
    "## Recurring Themes & Patterns: what comes up again and again.\n"
    "## What Energizes You: what clearly brings pleasure or excitement, with specifics.\n"
    "## What Weighs On You: recurring worries or frictions, named plainly but kindly.\n"
    "## Ideas Worth Pursuing: unfinished ideas that recur or seem promising.\n"
    "## Conclusion & Next Steps: 3-6 concrete, actionable next steps, including "
    "anything worth discussing with another person.\n\n"
    "Ground every claim in the supplied data. Refer to real themes by name. Do "
    "not invent events. Be direct and useful, not flattering." + _NO_DASH_RULE
)


def synthesize(provider, reduced, sample_gists=None, mode_cfg=None):
    """Turn the reduced aggregation into the final Markdown report.

    mode_cfg supplies the section structure and tone (journal vs work vs
    research vs general). Falls back to the journal-style SYNTH_SYSTEM.
    """
    system = (mode_cfg or {}).get("synth_system", SYNTH_SYSTEM)
    payload = dict(reduced)
    if sample_gists:
        payload["sample_gists"] = sample_gists[:25]
    user = (
        "Here is the aggregated analysis across all documents (JSON). Write the "
        "report from it.\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    # Final report: quality-sensitive, runs once -> SYNTH model.
    synth = getattr(provider, "synth", provider)
    return _clean_summary(synth.chat(system, user))


PROMPTS_SYSTEM = (
    "You are a perceptive, warm journaling companion. You are given an aggregated "
    "analysis of someone's journal entries: what recurs, what energizes them, "
    "what weighs on them, and which ideas keep resurfacing. Your job is to write "
    "NEW writing prompts that press them to go deeper, especially on things they "
    "circle back to but may be avoiding examining fully.\n\n"
    "Return ONLY a JSON object, no prose or fences, with this schema:\n"
    "{\n"
    '  "dig_deeper": [\n'
    '    {"about": "the recurring theme this targets",\n'
    '     "prompt": "a specific, probing question or writing prompt",\n'
    '     "why": "one sentence: why this is worth examining now"}\n'
    "  ],\n"
    '  "unfinished_ideas": [\n'
    '    {"idea": "a recurring idea from their notes",\n'
    '     "prompt": "a prompt to push the idea forward or decide on it"}\n'
    "  ],\n"
    '  "what_brings_joy": [\n'
    '    {"prompt": "a prompt that helps them notice and protect what energizes them"}\n'
    "  ]\n"
    "}\n"
    "Rules: ground every prompt in a SPECIFIC theme from the data, by name. Favor "
    "the things that recur most (those carry the most weight). For friction that "
    "recurs, write prompts that gently open it up rather than solve it. Prompts "
    "should be answerable in a paragraph or two. 3-5 items in dig_deeper, 2-4 in "
    "unfinished_ideas, 2-3 in what_brings_joy. Be specific, never generic, no "
    "'How are you feeling today?' filler." + _NO_DASH_RULE
)

# Mode-specific follow-up generators. Each keeps the SAME 3-bucket JSON shape so
# the UI renders identically; only the framing/labels differ. The render layer
# maps bucket keys to the mode's section titles.
_FOLLOWUP_SYSTEMS = {
    "work": (
        "You are a sharp project analyst. You are given an aggregated analysis of "
        "someone's work documents: recurring workstreams, what's progressing, "
        "blockers/risks, and recurring action items. Produce concrete follow-ups. "
        "Return ONLY a JSON object, no fences, with this schema:\n"
        "{\n"
        '  "dig_deeper": [{"about":"the risk/blocker/topic","prompt":"a pointed '
        'open question to resolve","why":"one sentence: why it matters now"}],\n'
        '  "unfinished_ideas": [{"idea":"a recurring initiative/decision","prompt":'
        '"the decision or next step needed to move it"}],\n'
        '  "what_brings_joy": [{"prompt":"a question that builds on what is working '
        'well, to reinforce or scale it"}]\n'
        "}\n"
        "Ground every item in a SPECIFIC theme from the data, by name. Favor what "
        "recurs most. 3-5 in dig_deeper, 2-4 in unfinished_ideas, 2-3 in "
        "what_brings_joy. Be concrete and actionable; no filler." + _NO_DASH_RULE
    ),
    "research": (
        "You are a rigorous research advisor. You are given an aggregated analysis "
        "of someone's research/study notes: recurring concepts, well-supported "
        "findings, and gaps or contradictions. Produce open research questions. "
        "Return ONLY a JSON object, no fences, with this schema:\n"
        "{\n"
        '  "dig_deeper": [{"about":"the gap/tension/concept","prompt":"a precise '
        'research question to pursue","why":"one sentence: why it is worth it"}],\n'
        '  "unfinished_ideas": [{"idea":"a recurring concept/thread","prompt":"a '
        'next line of inquiry to develop it"}],\n'
        '  "what_brings_joy": [{"prompt":"a question that extends a well-supported '
        'finding into new territory"}]\n'
        "}\n"
        "Ground every item in a SPECIFIC theme from the data, by name. Favor what "
        "recurs most. 3-5 in dig_deeper, 2-4 in unfinished_ideas, 2-3 in "
        "what_brings_joy. Be precise and intellectually honest." + _NO_DASH_RULE
    ),
    "general": (
        "You are a thoughtful analyst. You are given an aggregated analysis of a "
        "mixed collection of documents: recurring themes, notable points, and "
        "gaps. Produce useful questions worth exploring. Return ONLY a JSON object, "
        "no fences, with this schema:\n"
        "{\n"
        '  "dig_deeper": [{"about":"the theme/gap","prompt":"a specific question '
        'worth exploring","why":"one sentence: why"}],\n'
        '  "unfinished_ideas": [{"idea":"a recurring topic","prompt":"a next step '
        'to develop it"}],\n'
        '  "what_brings_joy": [{"prompt":"a question that builds on a strong point '
        'in the collection"}]\n'
        "}\n"
        "Ground every item in a SPECIFIC theme from the data, by name. Favor what "
        "recurs most. 3-5 in dig_deeper, 2-4 in unfinished_ideas, 2-3 in "
        "what_brings_joy. Be specific and useful." + _NO_DASH_RULE
    ),
}


def generate_prompts(provider, reduced, mode=None):
    """
    Produce structured follow-ups that press deeper on what recurs. The framing
    depends on mode: journal -> introspective prompts; work -> open questions &
    decisions; research -> research questions; general -> questions to explore.
    Returns a dict (3-bucket schema) or None on failure.

    Deliberately a separate pass from synthesize(): the report describes the
    past; these point at the future.
    """
    system = _FOLLOWUP_SYSTEMS.get(mode, PROMPTS_SYSTEM)
    focus = {
        "repeated_themes": reduced.get("repeated_themes", []),
        "top_friction": reduced.get("top_friction", []),
        "top_energy": reduced.get("top_energy", []),
        "repeated_ideas": reduced.get("repeated_ideas", []),
        "top_ideas": reduced.get("top_ideas", [])[:8],
        "valence_counts": reduced.get("valence_counts", {}),
        "doc_count": reduced.get("doc_count", 0),
    }
    user = (
        "Aggregated analysis (JSON). Write follow-ups weighted toward what "
        "recurs.\n\n" + json.dumps(focus, ensure_ascii=False, indent=2)
    )
    # User-facing follow-ups, runs once -> SYNTH model for quality.
    synth = getattr(provider, "synth", provider)
    data = synth.chat_json(system, user)
    if not isinstance(data, dict):
        return None
    return _normalize_prompts(data)


def _clean_field(s):
    """Strip ca:// links and em dashes from a short text field."""
    s = _CA_LINK.sub(r"\1", str(s or ""))
    s = _BARE_CA.sub("", s)
    s = s.replace("\u2014", ", ").replace("\u2013", "-")
    s = _re.sub(r"\s+,", ",", s)        # " ," -> ","
    s = _re.sub(r",\s{2,}", ", ", s)    # ",  " -> ", "
    return _re.sub(r"\s{2,}", " ", s).strip()


def _normalize_prompts(data):
    out = {"dig_deeper": [], "unfinished_ideas": [], "what_brings_joy": []}
    for item in (data.get("dig_deeper") or [])[:5]:
        if isinstance(item, dict) and item.get("prompt"):
            out["dig_deeper"].append({
                "about": _clean_field(item.get("about", "")),
                "prompt": _clean_field(item["prompt"]),
                "why": _clean_field(item.get("why", "")),
            })
    for item in (data.get("unfinished_ideas") or [])[:4]:
        if isinstance(item, dict) and item.get("prompt"):
            out["unfinished_ideas"].append({
                "idea": _clean_field(item.get("idea", "")),
                "prompt": _clean_field(item["prompt"]),
            })
    for item in (data.get("what_brings_joy") or [])[:3]:
        if isinstance(item, dict) and item.get("prompt"):
            out["what_brings_joy"].append({"prompt": _clean_field(item["prompt"])})
    return out


# Per-mode labels for the follow-up section and its three buckets.
FOLLOWUP_LABELS = {
    "journal": {
        "title": "New Journal Prompts",
        "lead": "Prompts drawn from what you keep returning to, written to press you a little deeper.",
        "dig_deeper": "Dig deeper",
        "unfinished_ideas": "Ideas worth deciding on",
        "what_brings_joy": "Notice what lifts you",
    },
    "work": {
        "title": "Open Questions & Follow-ups",
        "lead": "Questions and next steps drawn from what recurs across these documents.",
        "dig_deeper": "Open questions to resolve",
        "unfinished_ideas": "Decisions & initiatives to move",
        "what_brings_joy": "Build on what's working",
    },
    "research": {
        "title": "Open Research Questions",
        "lead": "Questions and directions drawn from the concepts and gaps that recur.",
        "dig_deeper": "Gaps worth investigating",
        "unfinished_ideas": "Threads to develop",
        "what_brings_joy": "Extend strong findings",
    },
    "general": {
        "title": "Questions Worth Exploring",
        "lead": "Questions and next steps drawn from what recurs across the collection.",
        "dig_deeper": "Worth a closer look",
        "unfinished_ideas": "Topics to develop",
        "what_brings_joy": "Build on strong points",
    },
}


def prompts_to_markdown(prompts, mode="journal"):
    """Render the prompts dict to Markdown, with section labels for the mode."""
    if not prompts:
        return ""
    L = FOLLOWUP_LABELS.get(mode, FOLLOWUP_LABELS["journal"])
    lines = ["", f"## {L['title']}", "", f"_{L['lead']}_", ""]
    if prompts.get("dig_deeper"):
        lines.append(f"### {L['dig_deeper']}")
        for p in prompts["dig_deeper"]:
            about = f" *(on {p['about']})*" if p.get("about") else ""
            lines.append(f"- **{p['prompt']}**{about}")
            if p.get("why"):
                lines.append(f"  - {p['why']}")
        lines.append("")
    if prompts.get("unfinished_ideas"):
        lines.append(f"### {L['unfinished_ideas']}")
        for p in prompts["unfinished_ideas"]:
            idea = f"*{p['idea']}*: " if p.get("idea") else ""
            lines.append(f"- {idea}{p['prompt']}")
        lines.append("")
    if prompts.get("what_brings_joy"):
        lines.append(f"### {L['what_brings_joy']}")
        for p in prompts["what_brings_joy"]:
            lines.append(f"- {p['prompt']}")
        lines.append("")
    return _clean_summary("\n".join(lines))


# ── Summarizer (separate screen: files / YouTube / web -> 1-page summary) ──────

# Roughly chars that fit comfortably in one pass for an 8B-class local model.
SUMMARY_SINGLE_LIMIT = 14000
CHUNK_SIZE = 12000
def _limits_for(provider):
    """Return (single_limit, chunk_size) tuned to the provider."""
    return SUMMARY_SINGLE_LIMIT, CHUNK_SIZE

_NO_STYLE = (
    " Use plain hyphens or commas, never em dashes or en dashes. Do not offer "
    "follow-up help, suggestions, or meta-commentary about the summary itself; "
    "end when the content ends. Do NOT add citations, reference links, or "
    "markdown links of any kind (no [text](url) syntax) - plain text only."
)

SUMMARY_SYSTEM = (
    "You write clear, well-structured study notes from a document, transcript, or "
    "article. Produce SKIMMABLE notes in Markdown, NOT a wall of prose. Aim for "
    "roughly one page. Follow this structure:\n\n"
    "**One bold sentence** at the very top giving the overall gist.\n\n"
    "## Overview\nTwo or three sentences of context, no more.\n\n"
    "Then 3 to 6 thematic sections, each with its own '## ' sub-headline named "
    "for the actual topic (for example '## Identifying the Plant', '## Removal "
    "Methods', '## Safety Risks'). Do NOT use generic headers like 'Summary' or "
    "'Key Points'. Under each sub-headline, prefer:\n"
    "- bullet points with a **bold lead-in phrase** then a short explanation, and/"
    "or\n"
    "- a compact Markdown table when the content compares items, lists "
    "options/steps/types, or has any row-and-column structure (for example a "
    "table of methods vs effectiveness, seasons vs appearance, tools vs use).\n"
    "When you use a table, format it as proper GitHub Markdown: a header row, then "
    "a separator row of dashes, then the data rows, with NO blank lines between any "
    "of them. Example:\n"
    "| Column A | Column B |\n| --- | --- |\n| value | value |\n"
    "Use tables and bullet lists generously wherever the content supports them; "
    "reserve plain paragraphs for genuinely narrative material.\n\n"
    "## Takeaway\nOne or two sentences on the core 'so what'.\n\n"
    "Be faithful to the source; never invent facts. If it is a video transcript, "
    "summarize what is said, not the act of speaking. Keep it tight and scannable."
    + _NO_STYLE
)

CHUNK_SYSTEM = (
    "You are condensing one section of a longer work so it can later be combined "
    "with other sections into a single summary. Capture the section's key facts, "
    "arguments, and any notable details in a tight paragraph or two. Be faithful; "
    "do not invent. Return only the condensed notes, no preamble." + _NO_STYLE
)

REDUCE_SUMMARY_SYSTEM = (
    "You are given condensed section-notes from a single long work (a book, long "
    "article, or long video), in order. Write ONE unified set of SKIMMABLE study "
    "notes in Markdown, NOT a wall of prose. Aim for about one page. Structure:\n\n"
    "**One bold sentence** at the very top giving the overall gist.\n\n"
    "## Overview\nTwo or three sentences of context.\n\n"
    "Then 4 to 7 thematic sections, each with its own '## ' sub-headline named for "
    "the actual topic (not generic labels like 'Summary' or 'Key Points'). Under "
    "each, prefer bullet points with a **bold lead-in phrase** plus a short "
    "explanation, and use a compact Markdown table whenever the material compares "
    "items, lists options/steps/types/examples, or has row-and-column structure "
    "(for example: case examples with issue and outcome, methods vs effectiveness, "
    "stages vs description). When you use a table, format it as proper GitHub "
    "Markdown: a header row, then a separator row of dashes, then data rows, with "
    "NO blank lines between any of them (| A | B |, then | --- | --- |, then rows). "
    "Use tables and lists generously; reserve paragraphs "
    "for genuinely narrative material.\n\n"
    "## Takeaway\nOne or two sentences on the core message.\n\n"
    "Synthesize across ALL sections, not just the first. Be faithful; never invent. "
    "Keep it tight and scannable." + _NO_STYLE
)

DETAILED_SUMMARY_SYSTEM = (
    "You write a THOROUGH, in-depth prose summary of a document, long article, or "
    "long video transcript. This is the 'Detailed' view: the reader wants real "
    "depth and nuance, not a quick skim. Aim for roughly TWO FULL PAGES or more "
    "for substantial sources - do not compress aggressively, and do not omit "
    "important supporting detail, examples, names, numbers, or step-by-step "
    "reasoning that appears in the source.\n\n"
    "Write in clear, well-organized PROSE (flowing paragraphs), not bullet lists. "
    "Use '## ' sub-headlines named for the actual topics to organize the piece, "
    "with several paragraphs of genuine explanation under each. Walk through the "
    "material in a logical order, preserving the source's specifics: concrete "
    "examples, case studies, anecdotes, figures, and the connective 'why' between "
    "ideas. Where the source gives a sequence or process, explain it fully rather "
    "than just naming it.\n\n"
    "Start with one bold sentence giving the overall thesis, then an '## Overview' "
    "of a short paragraph, then the detailed sections, and end with a '## Bottom "
    "line' paragraph. Be faithful to the source; never invent facts or add outside "
    "information. If it is a transcript, summarize what is said, not the act of "
    "speaking. Favor completeness and clarity over brevity." + _NO_STYLE
)

BULLETS_SYSTEM = (
    "Rewrite the given summary as a simplified, skimmable bulleted outline in "
    "Markdown, plainer and shorter than the original. Use:\n\n"
    "**A one-line takeaway** in bold at the top.\n\n"
    "Then 5-10 top-level bullets of the most important points, each a short, "
    "plain-language line. Use a couple of indented sub-bullets only where a point "
    "really needs one detail. No long paragraphs and no fluff. Output ONLY the "
    "bullets and the takeaway line; do not write any closing sentence, and do not "
    "offer to make a cheat-sheet, outline, or any further help." + _NO_STYLE
)

import re as _re
_CA_LINK = _re.compile(r"\[([^\]]+)\]\((?:ca|sandbox|attachment)://[^)]*\)")
_BARE_CA = _re.compile(r"\(?(?:ca|sandbox|attachment)://[^\s)]+\)?")
# trailing "If you want, I can..." style offers the model sometimes appends
_OFFER = _re.compile(
    r"\n+\s*(?:if you(?:'d| would)? (?:want|like)|i can (?:also )?(?:turn|make|"
    r"break|create|provide)|let me know|would you like|want me to)\b.*$",
    _re.IGNORECASE | _re.DOTALL)


def _clean_summary(md):
    """Strip model-invented citation links, em dashes, and trailing offers of
    further help so the summary ends cleanly on its content."""
    if not md:
        return md
    md = _CA_LINK.sub(r"\1", md)
    md = _BARE_CA.sub("", md)
    md = _OFFER.sub("", md)           # drop "If you want, I can..." tails
    md = md.replace("\u2014", ", ").replace("\u2013", "-")  # em/en dash -> plain
    md = _re.sub(r"\s+,", ",", md)    # tidy any " ," from the swap
    md = _re.sub(r",\s{2,}", ", ", md)  # collapse ",  " -> ", "
    return md.rstrip()


def _hard_split(s, size):
    """Split a long string with no good break points, preferring sentence then
    word boundaries, guaranteeing every piece is <= size."""
    out = []
    while len(s) > size:
        window = s[:size]
        # prefer to break at a sentence end, else a space, else hard cut
        cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if cut < size * 0.5:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = size
        out.append(s[:cut + 1].strip())
        s = s[cut + 1:].strip()
    if s:
        out.append(s)
    return out


def _chunk_text(text, size=CHUNK_SIZE):
    """Split into <=size chunks. Breaks on paragraphs/lines first, but also
    hard-splits any single piece that is itself longer than `size` (e.g. a
    YouTube transcript joined into one long line with no newlines)."""
    paras = text.split("\n")
    chunks, cur = [], ""
    for p in paras:
        # a single paragraph/line bigger than size must be broken down
        if len(p) > size:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_hard_split(p, size))
            continue
        if len(cur) + len(p) + 1 > size and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks


def _final_combine(provider, joined, single_limit, chunk_size, progress=None):
    """Turn the accumulated section notes into the final one-page summary.

    Resilient by design, because this is the call most likely to be rejected by
    Copilot on a very long source (it's the largest single request, fired after
    a long run when the session is most rate-limited). Strategy:
      1. One-shot combine (the normal, best-quality path).
      2. If that fails, combine the notes in small batches and then combine the
         batch results - smaller payloads are far less likely to be rejected.
      3. If even that fails, stitch the cleaned notes together locally with no
         LLM call at all, so a finished run is never thrown away.
    The worst case is a slightly less polished summary, not a crash.
    """
    synth = getattr(provider, "synth", provider)
    fast = getattr(provider, "fast", provider)
    # 1) normal one-shot combine (final output -> SYNTH model)
    try:
        return synth.chat(REDUCE_SUMMARY_SYSTEM,
                          f"Section notes, in order:\n\n{joined}")
    except Exception:
        pass

    # 2) hierarchical combine: break notes into small batches, summarize each
    #    (cheap repetitive work -> FAST model), then one final pass (SYNTH).
    if progress:
        progress({"phase": "synthesizing", "final": True, "recovering": True})
    blocks = [b for b in joined.split("\n\n") if b.strip()]
    # ~5 note-blocks per batch keeps each combine request small
    batch_size = 5
    partials = []
    for i in range(0, len(blocks), batch_size):
        batch = "\n\n".join(blocks[i:i + batch_size])
        try:
            partials.append(fast.chat(CHUNK_SYSTEM, batch))
        except Exception:
            # keep the raw notes for this batch rather than dropping them
            partials.append(batch[:1500])
    small = "\n\n".join(partials)
    if len(small) > single_limit:
        small = small[:single_limit]
    try:
        return synth.chat(REDUCE_SUMMARY_SYSTEM,
                          f"Section notes, in order:\n\n{small}")
    except Exception:
        pass

    # 3) pure-local fallback: no provider call. Stitch the notes into a readable
    #    document so the user still gets the full content of their long video.
    stitched = small if partials else joined
    header = ("**Combined from section notes.** The AI provider could not merge "
              "the sections into a single polished summary (this can happen on "
              "very long videos with Windows Copilot), so the section notes are "
              "presented in order below.\n\n")
    return header + stitched


def summarize_text(provider, text, meta=None, progress=None):
    """
    Produce a one-page summary of arbitrary text.

    Short text -> single pass. Long text (books, long transcripts) -> map-reduce.
    Returns a dict: {"full": <markdown>, "bullets": <markdown>}: the full prose
    summary and a simplified bulleted version, both generated in this scan so the
    UI can toggle instantly.
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Nothing to summarize. No text was extracted.")

    single_limit, chunk_size = _limits_for(provider)
    note_suffix = ""
    synth = getattr(provider, "synth", provider)
    fast = getattr(provider, "fast", provider)
    detail_source = None   # richest material for the long "Detailed" view

    if len(text) <= single_limit:
        if progress:
            progress({"phase": "summarizing", "chunk": 1, "chunks": 1})
        full = synth.chat(SUMMARY_SYSTEM, f"Source:\n\"\"\"\n{text}\n\"\"\"")
        detail_source = text   # short doc: detailed can read the whole thing
    else:
        # Long source: map-reduce. Resilient to occasional provider failures.
        # a failed chunk is skipped (with a marker) rather than aborting the whole
        # job, which matters for 100+ chunk books on Copilot.
        chunks = _chunk_text(text, size=chunk_size)
        notes = []
        failed = 0
        for i, ch in enumerate(chunks):
            if progress:
                progress({"phase": "condensing", "chunk": i + 1, "chunks": len(chunks)})
            try:
                note = fast.chat(CHUNK_SYSTEM, f"Section {i+1} of {len(chunks)}:\n"
                                               f"\"\"\"\n{ch}\n\"\"\"")
                notes.append(f"[Section {i+1}]\n{note}")
            except Exception:
                failed += 1
                notes.append(f"[Section {i+1}]\n(this section could not be processed)")
        if failed and failed >= len(chunks):
            raise RuntimeError("The summary failed. The AI model rejected every "
                               "section. Check that Ollama is running and the model "
                               "is pulled (Test connection), then try again.")

        if progress:
            progress({"phase": "synthesizing", "chunk": len(chunks), "chunks": len(chunks)})
        joined = "\n\n".join(notes)
        # Keep the FULL, un-condensed section notes as the source for the detailed
        # view. The while-loop below compresses `joined` down toward one page for
        # the normal summary; the detailed view wants this richer material instead.
        detail_source = joined
        # The reduce phase may take several rounds of condensing for very long
        # books. Report a CUMULATIVE, monotonic step count so the UI never appears
        # to go backwards (e.g. "pass 1 of 2" then back to "pass 1 of 2"), which
        # makes it look stuck. We don't know the total rounds up front, so we show
        # an ever-increasing "still condensing" count instead of a fake X-of-Y.
        condense_step = 0
        round_no = 0
        while len(joined) > single_limit:
            round_no += 1
            batch_notes = []
            batches = _chunk_text(joined, size=chunk_size)
            for b in batches:
                condense_step += 1
                if progress:
                    progress({"phase": "synthesizing", "reduce_step": condense_step,
                              "reduce_round": round_no})
                try:
                    batch_notes.append(fast.chat(CHUNK_SYSTEM, b))
                except Exception:
                    batch_notes.append(b[:1500])
            new_joined = "\n\n".join(batch_notes)
            if len(new_joined) >= len(joined):
                joined = new_joined[:single_limit]
                break
            joined = new_joined
        if progress:
            progress({"phase": "synthesizing", "final": True})
        # Final combine. On a very long source this is the single biggest call,
        # and Copilot can reject it (e.g. 502 "too-many-messages") right at the
        # finish line after 20+ minutes of work. So this is made resilient:
        #   1) try the normal one-shot combine,
        #   2) if it fails, combine the notes in small batches (hierarchical),
        #   3) if even that fails, stitch the section notes locally (no LLM) so
        #      the run NEVER throws away all that work.
        full = _final_combine(provider, joined, single_limit, chunk_size, progress)
        if failed:
            note_suffix = (f"\n\n---\n_Note: {failed} of {len(chunks)} sections "
                           f"couldn't be processed and were skipped, so this "
                           f"summary may be incomplete._")

    full = _clean_summary(full) + note_suffix

    # One extra pass to produce the simplified bulleted version for the toggle.
    # This just reformats the already-written summary, so it routes to FAST.
    if progress:
        progress({"phase": "finalizing"})
    try:
        bullets = _clean_summary(fast.chat(BULLETS_SYSTEM, full))
    except Exception:
        bullets = ""  # toggle just won't have a simplified view if this fails

    # The long, thorough "Detailed" view - generated from the richest material we
    # have (section notes for long sources, full text for short ones) so it can be
    # genuinely in-depth rather than a re-expansion of the one-page summary.
    if progress:
        progress({"phase": "detailing"})
    try:
        detailed = _build_detailed(synth, detail_source or full, single_limit) + note_suffix
    except Exception:
        detailed = ""  # toggle just won't have a detailed view if this fails

    return {"full": full, "bullets": bullets, "detailed": detailed}


def _build_detailed(synth, source, single_limit):
    """Write a long, thorough prose summary from the richest source material.

    For sources that fit, one pass. For very long ones, split the section notes
    into large batches, write a detailed pass per batch, and join them - this
    keeps depth (no aggressive compression) while staying within model limits.
    """
    source = (source or "").strip()
    if not source:
        return ""
    # Detailed prose can be long, so allow a larger input window than the normal
    # one-page limit before we have to batch.
    cap = max(single_limit, 16000)
    if len(source) <= cap:
        return _clean_summary(synth.chat(DETAILED_SUMMARY_SYSTEM,
                                         f"Source material:\n\"\"\"\n{source}\n\"\"\""))
    # Too big for one pass: batch the section notes and write detailed prose for
    # each batch, then concatenate (sections are already in order).
    blocks = [b for b in source.split("\n\n") if b.strip()]
    batches, cur, cur_len = [], [], 0
    for b in blocks:
        if cur_len + len(b) > cap and cur:
            batches.append("\n\n".join(cur)); cur, cur_len = [], 0
        cur.append(b); cur_len += len(b) + 2
    if cur:
        batches.append("\n\n".join(cur))
    parts = []
    for i, batch in enumerate(batches):
        try:
            piece = synth.chat(
                DETAILED_SUMMARY_SYSTEM,
                f"This is part {i+1} of {len(batches)} of the source material, in "
                f"order. Write the detailed summary for THIS part; it will be joined "
                f"with the others. Do not repeat an overall intro each time.\n\n"
                f"\"\"\"\n{batch}\n\"\"\"")
            parts.append(_clean_summary(piece))
        except Exception:
            continue
    return "\n\n".join(p for p in parts if p)


ASK_SYSTEM = (
    "You are answering a user's question about a specific source they have "
    "(a document, ebook, video transcript, web article, or a collection of their "
    "documents). You are given the most relevant excerpts from the FULL source "
    "text (not just a summary), plus the summary for orientation. Answer using "
    "the excerpts. Be direct, concrete, and specific - if they ask for actionable "
    "steps or a day-to-day plan, lay out the concrete steps the source gives, even "
    "if the summary left them out. If the excerpts genuinely don't contain the "
    "answer, say so plainly rather than guessing. Use plain hyphens, never em "
    "dashes. Do not add links or citations."
)

# crude but exact: detect counting/occurrence questions we can answer with code
_COUNT_Q = _re.compile(
    r"how many times|how often|number of times|count (?:the |of )?|how many "
    r"(?:times )?(?:does|did|is|are|was|were)\b|frequency of", _re.IGNORECASE)
_QUOTED = _re.compile(r"[\"'\u2018\u2019\u201c\u201d]([^\"'\u2018\u2019\u201c\u201d]{1,40})[\"'\u2018\u2019\u201c\u201d]")


def _try_exact_count(question, text):
    """If the question is a 'how many times does X appear' style, count it exactly
    in the raw text and return a Markdown answer. Otherwise return None."""
    if not text or not _COUNT_Q.search(question):
        return None
    # find the target term: prefer a quoted phrase, else the word after 'word/term'
    term = None
    m = _QUOTED.search(question)
    if m:
        term = m.group(1).strip()
    if not term:
        m = _re.search(r"\b(?:word|term|phrase|name)\s+([A-Za-z][\w'-]*)", question, _re.IGNORECASE)
        if m:
            term = m.group(1).strip()
    if not term:
        # last resort: the longest capitalized word in the question (e.g. Apple)
        caps = _re.findall(r"\b[A-Z][a-z]{2,}\b", question)
        caps = [c for c in caps if c.lower() not in ("how", "many", "times", "does",
                "did", "the", "word", "story", "book", "what", "this")]
        if caps:
            term = max(caps, key=len)
    if not term:
        return None
    # whole-word, case-insensitive count
    pattern = _re.compile(r"\b" + _re.escape(term) + r"\b", _re.IGNORECASE)
    n = len(pattern.findall(text))
    return (f"The word **{term}** appears **{n} time" + ("s" if n != 1 else "") +
            f"** in the full text (whole-word, case-insensitive).")


def _retrieve(question, text, max_chars):
    """Lightweight local retrieval: split the text into windows and rank them by
    overlap with the question's keywords, returning the top windows up to
    max_chars. No embeddings - keeps it dependency-free and fully local."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    # keywords from the question (drop short/stopwords)
    stop = set("the a an and or of to in is are was were be been being on for with "
               "what how many times does did this that these those it its as at by "
               "from i you me my your we our they them their he she his her about "
               "which who whom whose when where why can could would should do done".split())
    qwords = [w for w in _re.findall(r"[a-z][a-z'-]{2,}", question.lower())
              if w not in stop]
    if not qwords:
        return text[:max_chars]
    qset = set(qwords)
    win = 1800
    windows = [text[i:i + win] for i in range(0, len(text), win)]
    scored = []
    for idx, w in enumerate(windows):
        wl = w.lower()
        score = sum(wl.count(k) for k in qset)
        if score:
            scored.append((score, idx, w))
    if not scored:
        return text[:max_chars]
    scored.sort(key=lambda t: (-t[0], t[1]))
    picked, used = [], 0
    for score, idx, w in scored:
        if used + len(w) > max_chars:
            continue
        picked.append((idx, w))
        used += len(w)
        if used >= max_chars:
            break
    picked.sort(key=lambda t: t[0])  # restore document order
    return "\n...\n".join(w for _, w in picked)


def answer_question(provider, question, context, extra=None):
    """Answer a user question grounded in the FULL raw source. Counting/occurrence
    questions are answered exactly by code; analytical questions retrieve the most
    relevant excerpts from the raw text and ask the model from those."""
    question = (question or "").strip()
    if not question:
        raise RuntimeError("Please type a question.")

    # 1) exact counting questions -> answer precisely from the raw text
    counted = _try_exact_count(question, context or "")
    if counted is not None:
        return counted

    # 2) analytical questions -> retrieve relevant excerpts, then ask the model
    single_limit, _ = _limits_for(provider)
    budget = max(1500, single_limit - len(question) - 600)
    excerpts = _retrieve(question, context or "", budget)
    parts = []
    if extra:
        parts.append("Summary (for orientation):\n" + extra[:1500])
    parts.append("Relevant excerpts from the FULL source:\n\"\"\"\n" + excerpts + "\n\"\"\"")
    parts.append("Question: " + question)
    # User-facing answer, runs once per question -> SYNTH model for quality.
    synth = getattr(provider, "synth", provider)
    return _clean_summary(synth.chat(ASK_SYSTEM, "\n\n".join(parts)))


def summary_header(meta):
    """A small Markdown header line describing the source, for the export."""
    if not meta:
        return ""
    bits = []
    if meta.get("title"):
        bits.append(f"**{meta['title']}**")
    if meta.get("kind"):
        bits.append(meta["kind"])
    if meta.get("approx_minutes"):
        bits.append(f"~{meta['approx_minutes']} min")
    if meta.get("chapter_count"):
        bits.append(f"{meta['chapter_count']} chapters")
    return " · ".join(bits)
