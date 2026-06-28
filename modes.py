"""
modes.py — interpretation modes for Analyze Collection.

The same structured map-schema serves every mode (themes, valence, energy/
friction, ideas, actions, people are general enough to cover most collections).
What changes per mode is:

  - map_hint        : how the model should read each document
  - synth_system    : the report's structure and tone
  - followup_system : the "what next" section (journal prompts vs open
                      questions vs research gaps, etc.)
  - labels          : human labels used when rendering aggregates

'auto' is resolved to a concrete mode by classify_mode() before the run.
"""

MODES = {
    "auto": {
        "label": "Auto (classify for me)",
        "blurb": "Looks at a sample of your documents and picks the best lens.",
    },
    "journal": {
        "label": "Journal / Self-reflection",
        "blurb": "Personal entries, diaries, idea scribbles.",
        "map_hint": (
            "You are reading one personal document — a journal entry, note, or "
            "idea scribble. Capture its emotional tone honestly."
        ),
        "synth_system": (
            "You are a thoughtful analyst writing a personal insight report for "
            "someone who handed you their own journal entries, notes, and idea "
            "scribbles. You are given a structured aggregation of patterns already "
            "computed across all documents. Write a warm, honest, specific report "
            "of ~500-700 words in Markdown with these sections:\n\n"
            "## Introduction — what this collection is, scope, overall tone.\n"
            "## Recurring Themes & Patterns — what comes up again and again.\n"
            "## What Energizes You — what clearly brings pleasure/excitement.\n"
            "## What Weighs On You — recurring worries/frictions, named kindly.\n"
            "## Ideas Worth Pursuing — unfinished ideas that recur or seem promising.\n"
            "## Conclusion & Next Steps — 3-6 concrete next steps, including "
            "anything worth discussing with another person.\n\n"
            "Ground every claim in the supplied data. Be direct and useful, not "
            "flattering."
        ),
        "followup_label": "New Journal Prompts",
    },
    "work": {
        "label": "Work / Documentation",
        "blurb": "Project notes, meeting minutes, specs, status updates.",
        "map_hint": (
            "You are reading one work document — a project note, meeting record, "
            "spec, or status update. Read it for decisions, action items, risks, "
            "and open questions rather than emotion. When the schema asks for "
            "'energy_sources', record what is going well or progressing; for "
            "'friction_sources', record blockers, risks, or problems."
        ),
        "synth_system": (
            "You are an analyst writing a status-and-insight briefing from a body "
            "of someone's work documents (project notes, meeting records, specs, "
            "updates). You are given a structured aggregation already computed "
            "across all documents. Write a crisp, useful ~500-700 word briefing in "
            "Markdown with these sections:\n\n"
            "## Overview — what this body of work covers, scope, and overall state.\n"
            "## Key Themes & Workstreams — the main projects/topics that recur.\n"
            "## Progress & What's Working — areas moving forward.\n"
            "## Risks, Blockers & Friction — recurring problems and open risks.\n"
            "## Decisions & Action Items — concrete commitments and next steps, "
            "with owners/people where named.\n"
            "## Recommendations — 3-6 prioritized next actions.\n\n"
            "Ground every claim in the data. Be concrete and professional; no fluff."
        ),
        "followup_label": "Open Questions & Follow-ups",
    },
    "research": {
        "label": "Research / Notes",
        "blurb": "Literature notes, study notes, reading highlights.",
        "map_hint": (
            "You are reading one research or study document — literature notes, "
            "reading highlights, or study notes. Read it for concepts, claims, "
            "evidence, and sources. Map 'ideas' to key concepts/claims, "
            "'energy_sources' to well-supported or promising findings, and "
            "'friction_sources' to gaps, contradictions, or open problems."
        ),
        "synth_system": (
            "You are writing a synthesis across a body of someone's research and "
            "study notes (literature notes, highlights, study notes). You are given "
            "a structured aggregation already computed across all documents. Write "
            "a clear ~500-700 word synthesis in Markdown with these sections:\n\n"
            "## Overview — the subject area and scope of these notes.\n"
            "## Core Concepts & Recurring Themes — ideas that appear across notes.\n"
            "## Well-Supported Findings — what the notes treat as established.\n"
            "## Gaps, Tensions & Open Problems — contradictions and unanswered "
            "questions.\n"
            "## Sources & Threads — notable people, works, or threads referenced.\n"
            "## Directions Worth Pursuing — 3-6 next lines of inquiry.\n\n"
            "Ground every claim in the data. Be precise and intellectually honest."
        ),
        "followup_label": "Open Research Questions",
    },
    "general": {
        "label": "General",
        "blurb": "A neutral read with no domain assumptions.",
        "map_hint": (
            "You are reading one document of unknown type. Summarize it neutrally "
            "and capture its main topics and any notable points, without assuming "
            "it is personal, work, or academic."
        ),
        "synth_system": (
            "You are writing a neutral overview across a collection of mixed "
            "documents. You are given a structured aggregation already computed "
            "across all of them. Write a clear ~450-650 word overview in Markdown "
            "with these sections:\n\n"
            "## Overview — what this collection appears to contain, and its scope.\n"
            "## Main Themes — the topics that recur across documents.\n"
            "## Notable Points — specifics worth highlighting.\n"
            "## Tensions or Gaps — anything unresolved, conflicting, or missing.\n"
            "## Takeaways & Next Steps — 3-6 useful next actions.\n\n"
            "Ground every claim in the data. Stay neutral and concrete."
        ),
        "followup_label": "Questions Worth Exploring",
    },
}

# Concrete modes Auto can resolve to (everything except auto itself).
CLASSIFIABLE = ["journal", "work", "research", "general"]


CLASSIFY_SYSTEM = (
    "You are given short samples from several documents in a collection. Decide "
    "which single interpretation lens best fits the collection as a whole. "
    "Return ONLY one lowercase word, no punctuation, from this set:\n"
    "  journal   — personal entries, diary, reflections, idea scribbles\n"
    "  work      — project notes, meetings, specs, status updates, business docs\n"
    "  research  — literature/study notes, reading highlights, academic notes\n"
    "  general   — mixed or none of the above\n"
    "Answer with exactly one of: journal, work, research, general."
)


def classify_mode(provider, sample_texts):
    """Use a small LLM call to pick a concrete mode from sample documents.

    sample_texts: list of short strings (first chunk of a handful of docs).
    Returns one of CLASSIFIABLE; defaults to 'general' on any uncertainty.
    """
    if not sample_texts:
        return "general"
    joined = "\n\n---\n\n".join(t[:1200] for t in sample_texts[:6])
    try:
        reply = provider.chat(CLASSIFY_SYSTEM, f"Samples:\n\n{joined}",
                              max_retries=2, timeout=60)
    except Exception:
        return "general"
    word = (reply or "").strip().lower()
    for m in CLASSIFIABLE:
        if m in word:
            return m
    return "general"


def resolve(mode):
    """Return the mode config dict for a concrete (non-auto) mode id."""
    return MODES.get(mode, MODES["general"])
