#!/usr/bin/env python3
from pathlib import Path
import re


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    Path(path).write_text(text, encoding="utf-8")


def once(text, old, new, label):
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one match, found {text.count(old)}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# providers.py
p = read("providers.py")
p = once(p,
'''The default is a local Ollama model (Qwen3 8B). For cloud providers with rate
limits, calls are paced via the throttle here.''',
'''The default is Qwen3.5 9B through Ollama. Groq is pinned to Qwen 3.6 27B and
paced below its free-tier token and request limits.''', "provider doc")
p = once(p, "import time\nimport json\nimport threading\n", '''import time
import json
import threading
import os
import re
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
''', "provider imports")
start = p.index("PROVIDERS = {")
end = p.index("\n\n\ndef _load_user_providers", start)
provider_block = '''PROVIDERS = {
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
}'''
p = p[:start] + provider_block + p[end:]
insert_at = p.index("\n\nclass Throttle:")
limiter_code = r'''

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

    def __init__(self):
        self.lock = threading.RLock()
        self.tokens = deque()
        self.requests = deque()
        self.server_remaining = None
        self.server_reset = 0.0
        self.blocked_until = 0.0
        self.usage_path = os.path.join(os.path.dirname(__file__), "credentials", "groq_usage.json")
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
                used = sum(x[1] for x in self.tokens)
                if used + amount > self.TPM and self.tokens:
                    need = used + amount - self.TPM
                    for stamp, spent in self.tokens:
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
                    self.tokens.append([now, amount]); self.requests.append(now)
                    self.daily += amount; self._save(); break
            waited = True
            if on_wait: on_wait(max(1, math.ceil(wait)))
            time.sleep(min(wait, 1.0))
        if waited and on_wait: on_wait(0)
        return amount

    def settle(self, reserved, actual):
        actual = max(0, int(actual if actual is not None else reserved))
        with self.lock:
            self._refresh()
            if self.tokens:
                self.tokens[-1][1] = actual
            self.daily = max(0, self.daily - reserved + actual); self._save()

    def refund(self, reserved):
        with self.lock:
            self._refresh(); self.daily = max(0, self.daily - reserved); self._save()

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
'''
p = p[:insert_at] + limiter_code + p[insert_at:]
class_start = p.index("class LLMProvider:")
class_end = p.index("\n\nclass RoutingProvider:", class_start)
llm_class = r'''class LLMProvider:
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
'''
p = p[:class_start] + llm_class + p[class_end:]
p = p.replace("ollama pull qwen3:8b", "ollama pull qwen3.5:9b")
write("providers.py", p)

# ---------------------------------------------------------------------------
# app.py: pass a wait callback into providers and hide stale Groq overrides.
a = read("app.py").replace("defaults to a local Ollama model (Qwen3 8B)", "defaults to a local Ollama model (Qwen3.5 9B)")
a = once(a, "def _build_provider(cfg):", '''def _job_rate_wait(seconds):
    prefix = "Groq rate window:"
    message = (f"{prefix} waiting {seconds}s before the next call…" if seconds > 0
               else f"{prefix} ready; continuing.")
    if JOB["log"] and JOB["log"][-1].startswith(prefix): JOB["log"][-1] = message
    else: log(message)


def _build_provider(cfg, on_wait=None):''', "app builder")
a = a.replace("api_key=api_key or None,\n    )", "api_key=api_key or None,\n        on_wait=on_wait,\n    )", 1)
a = a.replace("model=fast_model,\n            api_key=api_key or None,\n        )", "model=fast_model,\n            api_key=api_key or None,\n            on_wait=on_wait,\n        )", 1)
a = a.replace("provider = _build_provider(cfg)\n\n        # ---- resolve", "provider = _build_provider(cfg, on_wait=_job_rate_wait)\n\n        # ---- resolve", 1)
marker = "_sum_lock = threading.Lock()\n"
a = once(a, marker, marker + '''

def _summary_rate_wait(seconds):
    if seconds > 0:
        SUM["stage"] = "rate_wait"; SUM["detail"] = f"Groq rate window: continuing in {seconds}s…"
    elif SUM.get("stage") == "rate_wait":
        SUM["stage"] = SUM.get("phase") or "summarizing"; SUM["detail"] = "Groq rate window ready; continuing…"
''', "summary callback")
pos = a.index("def run_summary(cfg):")
a = a[:pos] + a[pos:].replace("provider = _build_provider(cfg)", "provider = _build_provider(cfg, on_wait=_summary_rate_wait)", 1)
write("app.py", a)

# ---------------------------------------------------------------------------
# pipeline.py: task-specific output budgets and daily-limit handling.
q = read("pipeline.py")
q = once(q, "from extract import walk_folder, extract_text, file_hash\n", "from extract import walk_folder, extract_text, file_hash\nfrom providers import ProviderDailyLimitError\n", "pipeline import")
q = q.replace("note = fast.chat_json(sys_prompt, user)", "note = fast.chat_json(sys_prompt, user, max_tokens=700)")
q = q.replace("user + \"\\n\\nReturn ONLY the JSON object. No other text.\",\n        )", "user + \"\\n\\nReturn ONLY the JSON object. No other text.\",\n            max_tokens=700,\n        )")
q = q.replace("return _clean_summary(synth.chat(system, user))", "return _clean_summary(synth.chat(system, user, max_tokens=1600))")
q = q.replace("data = synth.chat_json(system, user)", "data = synth.chat_json(system, user, max_tokens=1000)")
q = q.replace("except Exception as e:\n            skipped.append({\"file\": rel, \"reason\": f\"map failed: {e}\"})", "except ProviderDailyLimitError:\n            raise\n        except Exception as e:\n            skipped.append({\"file\": rel, \"reason\": f\"map failed: {e}\"})", 1)
q = q.replace("notes.append(f\"[Section {i+1}]\\n{note}\")\n            except Exception:", "notes.append(f\"[Section {i+1}]\\n{note}\")\n            except ProviderDailyLimitError:\n                raise\n            except Exception:", 1)
q = q.replace("batch_notes.append(fast.chat(CHUNK_SYSTEM, b))", "batch_notes.append(fast.chat(CHUNK_SYSTEM, b, max_tokens=700))")
q = q.replace("except Exception:\n                    batch_notes.append(b[:1500])", "except ProviderDailyLimitError:\n                    raise\n                except Exception:\n                    batch_notes.append(b[:1500])", 1)
q = q.replace("fast.chat(BULLETS_SYSTEM, full)", "fast.chat(BULLETS_SYSTEM, full, max_tokens=1100)")
q = q.replace("synth.chat(ASK_SYSTEM, \"\\n\\n\".join(parts))", "synth.chat(ASK_SYSTEM, \"\\n\\n\".join(parts), max_tokens=1400)")
write("pipeline.py", q)

# ---------------------------------------------------------------------------
# Front end and documentation.
h = read("static/index.html")
h = h.replace("const ADV=['groq','ollama'];", "const ADV=['ollama']; // Groq model and endpoint are pinned.")
h = h.replace("synthesizing:'Writing the summary',done:", "synthesizing:'Writing the summary',rate_wait:'Waiting for Groq',done:")
write("static/index.html", h)

r = read("README.md")
for old, new in {
    "Qwen3 8B": "Qwen3.5 9B",
    "qwen3:8b": "qwen3.5:9b",
    "Phi-4-mini": "Qwen3.5 4B",
    "phi4-mini": "qwen3.5:4b",
    "Groq (Llama 4 Scout)": "Groq (Qwen 3.6 27B)",
    "Groq — Llama 4 Scout": "Groq - Qwen 3.6 27B",
    "Groq — Qwen 3.6 27B": "Groq - Qwen 3.6 27B",
}.items(): r = r.replace(old, new)
r = r.replace("Summarizes long videos and whole books in one pass (128k\n> context) in seconds", "Runs much faster than local inference. Sonario splits long sources into rate-safe calls")
r += '''

## Qwen 3.6 cloud pacing

The Groq preset is pinned to `qwen/qwen3.6-27b`; old Scout settings cannot be
restored. Sonario uses non-thinking mode, task-sized output budgets, conservative
limits below Groq's 8K TPM / 200K TPD / 30 RPM free-tier baseline, and live reset
headers. It waits between calls rather than repeatedly returning HTTP 429. Daily
limits are organization-wide; use Qwen3.5 9B locally for quota-free long jobs.
'''
write("README.md", r)

b = read("BUILD.md")
for old, new in {
    "qwen3:8b": "qwen3.5:9b", "phi4-mini": "qwen3.5:4b",
    "Qwen3 8B": "Qwen3.5 9B", "Phi-4-mini": "Qwen3.5 4B",
    "Llama 4 Scout": "Qwen 3.6 27B",
    "meta-llama/llama-4-scout-17b-16e-instruct": "qwen/qwen3.6-27b",
    "~2.5GB": "~3.4GB", "~5GB": "~6.6GB",
}.items(): b = b.replace(old, new)
b = b.replace("Very large jobs may\n  briefly hit those limits; if so, wait a moment and retry, or use a local model.", "Sonario queues calls below the minute limits and follows Groq's reset headers. If the organization-wide daily quota is exhausted, switch to a local model or continue after reset.")
write("BUILD.md", b)

Path("tests").mkdir(exist_ok=True)
write("tests/test_providers.py", '''import unittest\nfrom unittest.mock import Mock, patch\nimport providers\n\nclass Tests(unittest.TestCase):\n    def test_models(self):\n        self.assertEqual(providers.PROVIDERS["local-qwen8b"]["model"], "qwen3.5:9b")\n        self.assertEqual(providers.PROVIDERS["local-smart"]["fast_model"], "qwen3.5:4b")\n    def test_groq_is_pinned(self):\n        p=providers.LLMProvider("groq", base_url="https://bad", model="old", api_key="x")\n        self.assertEqual(p.model, providers.GROQ_MODEL); self.assertEqual(p.base_url, providers.GROQ_BASE_URL)\n    def test_duration(self):\n        self.assertEqual(providers._reset_seconds("1m2s"), 62)\n    def test_payload(self):\n        response=Mock(status_code=200, headers={}); response.json.return_value={"choices":[{"message":{"content":"OK"}}],"usage":{"total_tokens":9}}\n        p=providers.LLMProvider("groq", api_key="x")\n        with patch.object(providers.requests,"post",return_value=response):\n            self.assertEqual(p.chat("s","u",max_retries=1,max_tokens=16),"OK")\nif __name__ == "__main__": unittest.main()\n''')
