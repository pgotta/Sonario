"""
providers.py — one OpenAI-compatible interface for every LLM backend.

Because Ollama, OpenAI and Gemini (compat endpoint) all speak the OpenAI
/v1/chat/completions shape, a single client works for all. Switching provider =
swapping base_url + model + key. No forked code.

The default is a local Ollama model (Qwen3 8B). For cloud providers with rate
limits, calls are paced via the throttle here.
"""

import time
import json
import threading

import requests


# Built-in provider presets. base_url points at an OpenAI-compatible endpoint.
PROVIDERS = {
    "local-qwen8b": {
        "label": "Qwen3 8B (recommended)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3:8b",
        "needs_key": False,
        "min_interval": 0.0,
        "tip": "Best all-round choice for a typical gaming laptop (8GB GPU). One strong local model does every step at full quality. ~5GB.",
        "note": "Recommended. One local model for everything via Ollama (~5GB), full quality on every step. Good on an 8GB GPU. Run ollama_setup.bat (or  ollama pull qwen3:8b  ) first.",
    },
    "local-smart": {
        "label": "Smart routing (fast + quality models)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3:8b",            # synthesis model (final reports/summaries)
        "fast_model": "phi4-mini",      # helper model (chunks, classify, JSON)
        "needs_key": False,
        "min_interval": 0.0,
        "routed": True,                 # signals app.py to build a RoutingProvider
        "tip": "Uses the lightweight model for bulk work and Qwen3 8B for the final write-up. Lighter on long jobs, but the chunk work is lower quality and it swaps models on an 8GB GPU.",
        "note": "Uses two models on your GPU via Ollama: a fast model (phi4-mini) for the heavy repetitive work and a stronger model (qwen3:8b) for the final write-up. Lighter on very long jobs, but chunk-level quality is lower than running Qwen3 8B for everything. Run ollama_setup.bat first (installs both, ~8GB total).",
    },
    "local-phi4mini": {
        "label": "Phi-4-mini (lightweight)",
        "base_url": "http://localhost:11434/v1",
        "model": "phi4-mini",
        "needs_key": False,
        "min_interval": 0.0,
        "tip": "Smallest and fastest. Good for weaker or CPU-only machines, or when speed matters more than depth. Lower quality on long or complex sources. ~2.5GB.",
        "note": "Smallest/fastest local option via Ollama (~2.5GB). Best for weaker or CPU-only machines, or when speed matters more than depth. Run  ollama pull phi4-mini  first.",
    },
    "ollama": {
        "label": "Ollama (any local model)",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "needs_key": False,
        "min_interval": 0.0,   # local, parallel-safe, no pacing needed
        "tip": "Advanced: type the name of any model you've pulled with Ollama (e.g. qwen3:14b, llama3.1) in the Model box.",
        "note": "Free & fully private. Requires Ollama installed and a pulled model. Type any pulled model name in the Model box.",
    },
    "openai": {
        "label": "OpenAI (API key)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "needs_key": True,
        "min_interval": 0.0,
        "tip": "Cloud, paid. Fast and high quality, runs on OpenAI's servers (your text is sent to them). Needs an API key.",
        "note": "Paste an OpenAI API key. ~cents to a couple dollars for 200 docs.",
    },
    "gemini": {
        "label": "Google Gemini (API key)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "needs_key": True,
        "min_interval": 1.0,
        "tip": "Cloud. Has a free tier (rate-limited) plus paid. Runs on Google's servers (your text is sent to them). Needs an API key.",
        "note": "Free tier available (rate-limited). Uses Gemini's OpenAI-compatible endpoint.",
    },
}


def _load_user_providers():
    """Merge user-defined providers from models.json over the built-ins.

    Lets people add any OpenAI-compatible endpoint (LM Studio, OpenRouter, a
    self-hosted gateway, etc.) without editing code. A missing or broken file is
    ignored so the app always starts.
    """
    import os
    path = os.path.join(os.path.dirname(__file__), "models.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for pid, cfg in (data.get("providers", {}) or {}).items():
        if not isinstance(cfg, dict) or "base_url" not in cfg:
            continue
        PROVIDERS[pid] = {
            "label": cfg.get("label", pid),
            "base_url": cfg["base_url"],
            "model": cfg.get("model", "local-model"),
            "needs_key": bool(cfg.get("needs_key", False)),
            "min_interval": float(cfg.get("min_interval", 0.0)),
            "note": cfg.get("note", ""),
        }


_load_user_providers()


class Throttle:
    """Enforces a minimum interval between calls, thread-safe."""

    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


class LLMProvider:
    """A configured, OpenAI-compatible chat client."""

    def __init__(self, provider_id="local-qwen8b", base_url=None, model=None,
                 api_key=None, min_interval=None):
        preset = PROVIDERS.get(provider_id, PROVIDERS["local-qwen8b"])
        self.provider_id = provider_id
        self.base_url = (base_url or preset["base_url"]).rstrip("/")
        self.model = model or preset["model"]
        self.api_key = api_key or "unused"
        interval = preset["min_interval"] if min_interval is None else min_interval
        self.throttle = Throttle(interval)

    def chat(self, system, user, max_retries=4, timeout=180):
        """One chat completion. Returns the assistant text. Retries with backoff."""
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "unused":
            headers["Authorization"] = f"Bearer {self.api_key}"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        payload = {"model": self.model, "messages": messages, "stream": False}

        # Local models (Ollama, port 11434) can be much slower than cloud, especially
        # a 14B reasoning model spilling into system RAM on an 8GB GPU and emitting
        # long <think> traces. Give them a generous ceiling so a slow-but-valid
        # response isn't killed as a timeout. Only bump the default; respect an
        # explicit shorter timeout (e.g. the quick connection test).
        if timeout == 180 and ("11434" in self.base_url or "localhost:11434" in url):
            timeout = 900

        last_err = None
        for attempt in range(max_retries):
            self.throttle.wait()
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    return _strip_dashes(_strip_think(content))
                # 429/5xx are transient (esp. Copilot 502 under load) — back off
                if r.status_code in (429, 500, 502, 503, 504):
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    # "too-many-messages" is a cumulative session ceiling, not a
                    # transient blip: hammering the same oversized call won't help.
                    # Fail fast so the caller's recovery path (smaller batches /
                    # local stitch) can take over instead of burning ~60s on
                    # identical retries.
                    if "too-many-messages" in r.text:
                        raise RuntimeError(last_err)
                    time.sleep(min(2 ** attempt * 2, 30))
                    continue
                # other codes are likely fatal (bad key, bad model) — surface them
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(min(2 ** attempt * 2, 30))
        raise RuntimeError(f"LLM call failed after {max_retries} attempts. {last_err}")

    def chat_json(self, system, user, **kw):
        """Chat that expects a JSON object back. Strips fences, parses safely."""
        raw = self.chat(system, user, **kw)
        return _parse_json(raw)


class RoutingProvider:
    """Routes pipeline calls to one of two underlying providers by role.

    Phase 1 of Sonario's multi-model design. Long jobs do two very different
    kinds of LLM work:

      - FAST role: cheap, repetitive, high-volume calls - per-document analyze
        notes, per-chunk summaries, JSON classify/prompt steps. These run dozens
        to hundreds of times per job, so a small fast model is ideal.
      - SYNTH role: the final, quality-sensitive calls that run once - the report
        synthesis, the final summary combine, and user-facing Q&A answers.

    The pipeline calls `provider.fast.chat(...)` or `provider.synth.chat(...)`.
    For backward compatibility this object also behaves like a single provider:
    `.chat`, `.chat_json`, `.provider_id`, `.base_url`, `.model` all forward to
    the SYNTH provider, so any code (or fallback cloud provider) that doesn't
    care about roles keeps working unchanged.

    When only one provider is configured (e.g. a cloud fallback), `fast` and
    `synth` are the SAME object, so routing is a no-op and behaviour is identical
    to before this change.
    """

    def __init__(self, synth, fast=None):
        self.synth = synth
        self.fast = fast if fast is not None else synth

    # --- backward-compatible single-provider surface (forwards to synth) ---
    def chat(self, system, user, **kw):
        return self.synth.chat(system, user, **kw)

    def chat_json(self, system, user, **kw):
        return self.synth.chat_json(system, user, **kw)

    @property
    def provider_id(self):
        return getattr(self.synth, "provider_id", "")

    @property
    def base_url(self):
        return getattr(self.synth, "base_url", "")

    @property
    def model(self):
        return getattr(self.synth, "model", "")


def as_router(provider):
    """Return a RoutingProvider regardless of input.

    Accepts either a plain LLMProvider (wraps it so fast==synth) or an existing
    RoutingProvider (returns it as-is). Lets pipeline code freely use `.fast` /
    `.synth` without caring how the provider was built.
    """
    if isinstance(provider, RoutingProvider):
        return provider
    return RoutingProvider(synth=provider)


def _strip_think(text):
    """Remove reasoning-model 'thinking' blocks from output.

    Reasoning/distill models (e.g. DeepSeek-R1 distills, Qwen3 in thinking mode)
    emit their chain-of-thought wrapped in <think>...</think> before the real
    answer. That scratch reasoning must not leak into reports, summaries, or the
    JSON the classify/prompts steps parse. This runs at the single point all model
    output passes through, so every provider benefits and the JSON paths stay clean.

    Handles the normal closed-tag case, and the degenerate case where the model
    was cut off mid-thought (an open <think> with no close) by dropping everything
    up to the last </think>, or the whole thing if it never closed.
    """
    if not text or not isinstance(text, str):
        return text
    import re as _r
    # Remove all well-formed <think>...</think> blocks (case-insensitive, multiline).
    text = _r.sub(r"(?is)<think>.*?</think>", "", text)
    # If an unmatched </think> remains (open tag stripped/absent), keep only what
    # follows the final close tag — that's the actual answer.
    if "</think>" in text.lower():
        idx = text.lower().rfind("</think>")
        text = text[idx + len("</think>"):]
    # If an unclosed <think> remains (truncated mid-reasoning), drop from it on.
    low = text.lower()
    if "<think>" in low:
        text = text[:low.find("<think>")]
    return text.strip()


def _strip_dashes(text):
    """Remove em/en dashes from EVERY model response, app-wide. The user wants
    them gone everywhere, so this runs at the single point all model output
    passes through. Converts the common ' — ' clause break to a comma, and any
    other em/en dash to a plain hyphen, then tidies spacing."""
    if not text or not isinstance(text, str):
        return text
    import re as _r
    # " — " or " – " used as a clause break -> ", "
    text = _r.sub(r"\s*[\u2014\u2013]\s*", lambda m: ", " if m.group(0).strip() != m.group(0) else "-", text)
    # any remaining em/en dash (no surrounding spaces, e.g. mid-word) -> hyphen
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    # also normalize the horizontal bar and minus sign just in case
    text = text.replace("\u2015", "-").replace("\u2212", "-")
    # tidy: " ," -> ",", ",," -> ",", and collapsed double spaces
    text = _r.sub(r"\s+,", ",", text)
    text = _r.sub(r",{2,}", ",", text)
    text = _r.sub(r"[ \t]{2,}", " ", text)
    return text


def _parse_json(text):
    """Best-effort extraction of a JSON object from a model reply."""
    t = text.strip()
    if t.startswith("```"):
        # strip ```json ... ``` fences
        t = t.split("```", 2)
        t = t[1] if len(t) > 1 else text
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip().strip("`").strip()
    # find the outermost braces if there's preamble
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def check_provider(provider):
    """Ping a provider with a tiny call. Returns (ok, message)."""
    try:
        reply = provider.chat("You are a test.", "Reply with the single word OK.",
                              max_retries=1, timeout=30)
        return True, reply.strip()[:60]
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        base = getattr(provider, "base_url", "") or ""
        # Local models via Ollama (port 11434). This is the default provider, so
        # make the common first-run failures readable instead of a raw stack trace.
        if "11434" in base or "localhost:11434" in low or "127.0.0.1:11434" in low:
            if ("refused" in low or "10061" in low or "max retries" in low
                    or "failed to establish" in low or "newconnectionerror" in low
                    or "connection" in low):
                return False, ("Ollama isn't running. Install it from ollama.com, "
                               "then run ollama_setup.bat (or  ollama pull qwen3:8b  ). "
                               "Ollama starts on its own after install (see BUILD.md).")
            if ("404" in low or "not found" in low or "no such model" in low
                    or "try pulling" in low):
                mdl = getattr(provider, "model", "") or "the model"
                return False, (f"Ollama is running but the model isn't downloaded yet. "
                               f"Run  ollama pull {mdl}  and try again.")
        return False, msg[:200]
