"""
providers.py — one OpenAI-compatible interface for every LLM backend.

Because Windows-Copilot-API, Ollama, OpenAI and Gemini (compat endpoint)
all speak the OpenAI /v1/chat/completions shape, a single client works for all.
Switching provider = swapping base_url + model + key. No forked code.

Copilot is the zero-config default. It serializes upstream and tops out at ~1-4
concurrent calls, and the maintainer explicitly asks not to hammer it, so the
map phase calls run STRICTLY SEQUENTIAL and PACED via the throttle here.
"""

import time
import json
import threading

import requests


# Built-in provider presets. base_url points at an OpenAI-compatible endpoint.
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek (free, no key)",
        "base_url": "http://localhost:8001/v1",
        "model": "deepseek-chat",
        "needs_key": False,
        "min_interval": 3.0,   # bridge serializes calls and self-limits ~30/min
        "note": "Free & fast. Requires the DeepSeek-API bridge running locally (run deepseek_setup.bat). Sign in once.",
    },
    "deepseek-expert": {
        "label": "DeepSeek Expert (free, slower, stronger)",
        "base_url": "http://localhost:8001/v1",
        "model": "deepseek-expert",
        "needs_key": False,
        "min_interval": 3.0,   # bridge serializes calls and self-limits ~30/min
        "note": "Free. Same DeepSeek bridge, but uses the stronger Expert model (slower). Sign in once.",
    },
    "copilot": {
        "label": "Windows Copilot (free, no key)",
        "base_url": "http://localhost:8000/v1",
        "model": "copilot",
        "needs_key": False,
        "min_interval": 4.0,   # seconds between calls — respect Copilot's serial limit
        "note": "Free. Requires the Windows-Copilot-API server running locally. Sign in once.",
    },
    "ollama": {
        "label": "Ollama (free, local, private)",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "needs_key": False,
        "min_interval": 0.0,   # local, parallel-safe, no pacing needed
        "note": "Free & fully private. Requires Ollama installed and a pulled model.",
    },
    "openai": {
        "label": "OpenAI (API key)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "needs_key": True,
        "min_interval": 0.0,
        "note": "Paste an OpenAI API key. ~cents to a couple dollars for 200 docs.",
    },
    "gemini": {
        "label": "Google Gemini (free tier or key)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "needs_key": True,
        "min_interval": 1.0,
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

    def __init__(self, provider_id="deepseek", base_url=None, model=None,
                 api_key=None, min_interval=None):
        preset = PROVIDERS.get(provider_id, PROVIDERS["deepseek"])
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

        last_err = None
        for attempt in range(max_retries):
            self.throttle.wait()
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    return _strip_dashes(content)
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
        # Friendlier, actionable guidance for the Windows Copilot bridge.
        if "8000" in base or "localhost:8000" in low or "127.0.0.1:8000" in low:
            if ("refused" in low or "10061" in low or "max retries" in low
                    or "failed to establish" in low or "connection" in low):
                return False, ("Copilot server isn't running. Run copilot_setup.bat "
                               "(it starts the server in the background).")
            if ("401" in low or "403" in low or "auth" in low or "sign" in low
                    or "login" in low or "unauthorized" in low):
                return False, ("Copilot is running but not signed in. Run "
                               "login_copilot.bat to sign in again.")
        # Same idea for the DeepSeek bridge (runs on 8001 to avoid Copilot's 8000).
        if "8001" in base or "localhost:8001" in low or "127.0.0.1:8001" in low:
            if ("refused" in low or "10061" in low or "max retries" in low
                    or "failed to establish" in low or "connection" in low):
                return False, ("DeepSeek server isn't running. Run deepseek_setup.bat "
                               "(it starts the server in the background).")
            if ("401" in low or "403" in low or "auth" in low or "sign" in low
                    or "login" in low or "unauthorized" in low):
                return False, ("DeepSeek is running but not signed in. Run "
                               "login_deepseek.bat to sign in again.")
        return False, msg[:200]
