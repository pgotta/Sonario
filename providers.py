"""
providers.py — one OpenAI-compatible interface for every LLM backend.

Because Ollama and Groq (OpenAI-compatible endpoint) both speak the OpenAI
/v1/chat/completions shape, a single client works for all. Switching provider =
swapping base_url + model + key. No forked code.

The default is Qwen3.5 9B through Ollama. Groq is pinned to Qwen 3.6 27B and
paced below its free-tier token and request limits.
"""

import time
import json
import threading
import os
import re
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import requests


# Built-in provider presets. base_url points at an OpenAI-compatible endpoint.
PROVIDERS = {
    # Legacy IDs are retained so old browser state still selects the right option.
    "local-qwen8b": {
        "label": "Qwen3.5 9B (recommended)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3.5:9b",
        "needs_key": False, "min_interval": 0.0,
        "reasoning_effort": "none", "max_tokens": 2048,
        "tip": "Best overall local choice for an 8GB gaming GPU. Strong summaries, writing, comprehension, and Q&A. About 6.6GB.",
        "note": "Recommended. Qwen3.5 9B is the strongest practical local fit for the reference RTX 5060 Laptop GPU. Run setup_all.bat or ollama pull qwen3.5:9b.",
    },
    "local-smart": {
        "label": "Smart routing (Qwen3.5 4B + 9B)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3.5:9b", "fast_model": "qwen3.5:4b",
        "needs_key": False, "min_interval": 0.0, "routed": True,
        "reasoning_effort": "none", "max_tokens": 2048,
        "tip": "Qwen3.5 4B handles repetitive chunks and 9B writes final output. Faster bulk work, but an 8GB GPU swaps models.",
        "note": "Uses Qwen3.5 4B for bulk work and Qwen3.5 9B for final reports and answers. About 10GB total, so an 8GB GPU swaps them between stages.",
    },
    "local-phi4mini": {
        "label": "Qwen3.5 4B (lightweight)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3.5:4b",
        "needs_key": False, "min_interval": 0.0,
        "reasoning_effort": "none", "max_tokens": 2048,
        "tip": "Fastest built-in local option. Good for quick summaries and extraction; less nuanced than 9B. About 3.4GB.",
        "note": "Small and fast local option. Run ollama pull qwen3.5:4b. Use 9B when depth and subtlety matter.",
    },
    "ollama": {
        "label": "Ollama (any local model)",
        "base_url": "http://localhost:11434/v1", "model": "qwen3.5:9b",
        "needs_key": False, "min_interval": 0.0,
        "tip": "Advanced: use any pulled Ollama model. Models much larger than 9B may spill into RAM on an 8GB GPU.",
        "note": "Free and fully private. Requires Ollama and a pulled model.",
    },
    "groq": {
        "label": "Groq - Qwen 3.6 27B (cloud)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.6-27b",
        "needs_key": True, "min_interval": 0.0,
        "reasoning_effort": "none", "max_tokens": 2048,
        "tip": "Very fast cloud model. Sonario waits for Groq token windows instead of repeatedly returning 429. Your text is sent to Groq.",
        "note": "Free-tier baseline: 8K tokens/minute, 200K/day, and 30 requests/minute across the Groq organization. Sonario leaves safety headroom and follows reset headers.",
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
            "tip": cfg.get("tip", ""),
            "fast_model": cfg.get("fast_model"),
            "routed": bool(cfg.get("routed", False)),
            "reasoning_effort": cfg.get("reasoning_effort"),
            "max_tokens": int(cfg.get("max_tokens", 0) or 0),
        }


_load_user_providers()


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "qwen/qwen3.6-27b"


class ProviderDailyLimitError(RuntimeError):
    pass


def _reset_seconds(value):
    if not value:
        return None
    text = str(value).strip().lower().replace(" ", "")
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", text)
    if not m or not any(m.groups()):
        return None
    return float(m.group(1) or 0) * 3600 + float(m.group(2) or 0) * 60 + float(m.group(3) or 0)


class GroqRateLimiter:
    """Shared, conservative pacing for Groq Qwen 3.6 free-tier limits."""
    TPM, TPD, RPM = 7600, 195000, 28
    WINDOW = 60.0
    MAX_REQUEST = 7200

    def __init__(self, usage_path=None):
        self.lock = threading.RLock()
        self.tokens = deque()
        self.requests = deque()
        self.server_remaining = None
        self.server_reset = 0.0
        self.blocked_until = 0.0
        self.usage_path = str(usage_path or os.path.join(os.path.dirname(__file__), "credentials", "groq_usage.json"))
        self.next_reservation = 1
        self.day = ""
        self.daily = 0
        self._load_day()

    @staticmethod
    def estimate(system, user, output_tokens):
        return max(1, math.ceil((len(system or "") + len(user or "")) / 4) + 120 + output_tokens)

    def _today(self):
        return datetime.now(timezone.utc).date().isoformat()

    def _load_day(self):
        self.day, self.daily = self._today(), 0
        try:
            data = json.loads(Path(self.usage_path).read_text(encoding="utf-8"))
            if data.get("date") == self.day:
                self.daily = max(0, int(data.get("used", 0)))
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.usage_path), exist_ok=True)
            Path(self.usage_path).write_text(json.dumps({"date": self.day, "used": self.daily}), encoding="utf-8")
        except OSError:
            pass

    def _refresh(self):
        if self.day != self._today():
            self.day, self.daily = self._today(), 0
            self._save()

    def _trim(self, now):
        while self.tokens and now - self.tokens[0][0] >= self.WINDOW:
            self.tokens.popleft()
        while self.requests and now - self.requests[0] >= self.WINDOW:
            self.requests.popleft()
        if self.server_reset <= now:
            self.server_remaining, self.server_reset = None, 0.0

    def acquire(self, amount, on_wait=None):
        amount = int(amount)
        if amount > self.MAX_REQUEST:
            raise RuntimeError("This Groq request is too large for the free-tier minute budget; Sonario should have split it automatically.")
        waited = False
        while True:
            with self.lock:
                self._refresh()
                if self.daily + amount > self.TPD:
                    raise ProviderDailyLimitError("Groq's Qwen 3.6 daily quota is exhausted. Completed Analyze Collection documents are cached. Continue after reset or use a local Ollama model.")
                now = time.time(); self._trim(now); wait = 0.0
                used = sum(row[1] for row in self.tokens)
                if used + amount > self.TPM and self.tokens:
                    need = used + amount - self.TPM
                    for stamp, spent, _reservation_id in self.tokens:
                        need -= spent
                        if need <= 0:
                            wait = max(wait, stamp + self.WINDOW - now); break
                if len(self.requests) >= self.RPM:
                    wait = max(wait, self.requests[0] + self.WINDOW - now)
                if self.blocked_until > now:
                    wait = max(wait, self.blocked_until - now)
                if self.server_remaining is not None and amount > self.server_remaining and self.server_reset > now:
                    wait = max(wait, self.server_reset - now)
                if wait <= 0:
                    reservation_id = self.next_reservation
                    self.next_reservation += 1
                    self.tokens.append([now, amount, reservation_id])
                    self.requests.append(now)
                    self.daily += amount
                    self._save()
                    break
            waited = True
            if on_wait: on_wait(max(1, math.ceil(wait)))
            time.sleep(min(wait, 1.0))
        if waited and on_wait: on_wait(0)
        return reservation_id, amount

    def settle(self, reservation, actual):
        reservation_id, reserved = reservation
        actual = max(0, int(actual if actual is not None else reserved))
        with self.lock:
            self._refresh()
            for row in self.tokens:
                if row[2] == reservation_id:
                    row[1] = actual
                    break
            self.daily = max(0, self.daily - reserved + actual)
            self._save()

    def refund(self, reservation):
        reservation_id, reserved = reservation
        with self.lock:
            self._refresh()
            for row in list(self.tokens):
                if row[2] == reservation_id:
                    self.tokens.remove(row)
                    break
            self.daily = max(0, self.daily - reserved)
            self._save()

    def headers(self, headers):
        try:
            remaining = int(float(headers.get("x-ratelimit-remaining-tokens")))
            reset = _reset_seconds(headers.get("x-ratelimit-reset-tokens"))
        except (TypeError, ValueError):
            return
        if reset:
            with self.lock:
                self.server_remaining = max(0, remaining); self.server_reset = time.time() + reset + .25

    def backoff(self, seconds):
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.time() + max(.25, seconds))


_GROQ_LIMITER = GroqRateLimiter()


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
    """A configured OpenAI-compatible chat client."""

    def __init__(self, provider_id="local-qwen8b", base_url=None, model=None,
                 api_key=None, min_interval=None, on_wait=None):
        preset = PROVIDERS.get(provider_id, PROVIDERS["local-qwen8b"])
        self.provider_id = provider_id
        if provider_id == "groq":
            self.base_url, self.model = GROQ_BASE_URL, GROQ_MODEL
        else:
            self.base_url = (base_url or preset["base_url"]).rstrip("/")
            self.model = model or preset["model"]
        self.api_key = api_key or "unused"
        self.throttle = Throttle(preset["min_interval"] if min_interval is None else min_interval)
        self.reasoning_effort = preset.get("reasoning_effort")
        self.default_max_tokens = int(preset.get("max_tokens", 0) or 0)
        self.on_wait = on_wait

    def chat(self, system, user, max_retries=4, timeout=180, max_tokens=None):
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "unused":
            headers["Authorization"] = f"Bearer {self.api_key}"
        output = self.default_max_tokens if max_tokens is None else int(max_tokens)
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": user})
        payload = {"model": self.model, "messages": messages, "stream": False}
        if output: payload["max_tokens"] = output
        if self.reasoning_effort: payload["reasoning_effort"] = self.reasoning_effort
        if "11434" in self.base_url and timeout == 180: timeout = 900
        is_groq = self.provider_id == "groq"
        estimate = _GROQ_LIMITER.estimate(system, user, output or 2048) if is_groq else 0
        last = None
        for attempt in range(max_retries):
            self.throttle.wait(); reserved = None
            if is_groq: reserved = _GROQ_LIMITER.acquire(estimate, self.on_wait)
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except requests.RequestException as exc:
                if reserved: _GROQ_LIMITER.refund(reserved)
                last = str(exc)
                if attempt + 1 < max_retries:
                    delay = min(2 ** attempt * 2, 30)
                    if is_groq: _GROQ_LIMITER.backoff(delay)
                    else: time.sleep(delay)
                    continue
                break
            if is_groq: _GROQ_LIMITER.headers(r.headers)
            if r.status_code == 200:
                data = r.json()
                if reserved: _GROQ_LIMITER.settle(reserved, (data.get("usage") or {}).get("total_tokens"))
                return _strip_dashes(_strip_think(data["choices"][0]["message"]["content"]))
            if reserved: _GROQ_LIMITER.refund(reserved)
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            low = r.text.lower()
            if r.status_code == 429 and is_groq:
                if any(x in low for x in ("tokens per day", "requests per day", "daily token", "tpd", "rpd")):
                    raise ProviderDailyLimitError("Groq's organization-wide Qwen 3.6 daily quota has been reached. Continue after reset or switch to local Ollama.")
                delay = _reset_seconds(r.headers.get("retry-after")) or _reset_seconds(r.headers.get("x-ratelimit-reset-tokens")) or min(2 ** attempt * 2, 30)
                _GROQ_LIMITER.backoff(delay); continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt + 1 < max_retries:
                time.sleep(min(2 ** attempt * 2, 30)); continue
            if r.status_code == 404 and is_groq:
                raise RuntimeError(f"Groq could not find Sonario's current cloud model ({GROQ_MODEL}). Update Sonario if Groq changed its lineup.")
            raise RuntimeError(last)
        raise RuntimeError(f"LLM call failed after {max_retries} attempts. {last}")

    def chat_json(self, system, user, **kw):
        return _parse_json(self.chat(system, user, **kw))


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
                               "then run ollama_setup.bat (or  ollama pull qwen3.5:9b  ). "
                               "Ollama starts on its own after install (see BUILD.md).")
            if ("404" in low or "not found" in low or "no such model" in low
                    or "try pulling" in low):
                mdl = getattr(provider, "model", "") or "the model"
                return False, (f"Ollama is running but the model isn't downloaded yet. "
                               f"Run  ollama pull {mdl}  and try again.")
        return False, msg[:200]
