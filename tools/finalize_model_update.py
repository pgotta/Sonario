from pathlib import Path

root = Path(__file__).resolve().parents[1]


def rw(name):
    return (root / name).read_text(encoding="utf-8")


def ww(name, text):
    (root / name).write_text(text, encoding="utf-8")


def one(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# Make simultaneous Groq requests settle the correct token reservation and keep
# custom models.json provider fields intact.
p = rw("providers.py")
p = one(p, '''        PROVIDERS[pid] = {
            "label": cfg.get("label", pid),
            "base_url": cfg["base_url"],
            "model": cfg.get("model", "local-model"),
            "needs_key": bool(cfg.get("needs_key", False)),
            "min_interval": float(cfg.get("min_interval", 0.0)),
            "note": cfg.get("note", ""),
        }
''', '''        PROVIDERS[pid] = {
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
''', "user providers")
p = p.replace(
    "    def __init__(self):\n        self.lock = threading.RLock()",
    "    def __init__(self, usage_path=None):\n        self.lock = threading.RLock()",
    1,
)
p = p.replace(
    '        self.usage_path = os.path.join(os.path.dirname(__file__), "credentials", "groq_usage.json")',
    '        self.usage_path = str(usage_path or os.path.join(os.path.dirname(__file__), "credentials", "groq_usage.json"))\n        self.next_reservation = 1',
    1,
)
p = one(p, '''                used = sum(x[1] for x in self.tokens)
                if used + amount > self.TPM and self.tokens:
                    need = used + amount - self.TPM
                    for stamp, spent in self.tokens:
                        need -= spent
                        if need <= 0:
                            wait = max(wait, stamp + self.WINDOW - now); break
''', '''                used = sum(row[1] for row in self.tokens)
                if used + amount > self.TPM and self.tokens:
                    need = used + amount - self.TPM
                    for stamp, spent, _reservation_id in self.tokens:
                        need -= spent
                        if need <= 0:
                            wait = max(wait, stamp + self.WINDOW - now); break
''', "token loop")
p = one(p, '''                if wait <= 0:
                    self.tokens.append([now, amount]); self.requests.append(now)
                    self.daily += amount; self._save(); break
''', '''                if wait <= 0:
                    reservation_id = self.next_reservation
                    self.next_reservation += 1
                    self.tokens.append([now, amount, reservation_id])
                    self.requests.append(now)
                    self.daily += amount
                    self._save()
                    break
''', "acquire append")
p = p.replace(
    "        return amount\n\n    def settle(self, reserved, actual):",
    "        return reservation_id, amount\n\n    def settle(self, reservation, actual):",
    1,
)
p = one(p, '''        actual = max(0, int(actual if actual is not None else reserved))
        with self.lock:
            self._refresh()
            if self.tokens:
                self.tokens[-1][1] = actual
            self.daily = max(0, self.daily - reserved + actual); self._save()

    def refund(self, reserved):
        with self.lock:
            self._refresh(); self.daily = max(0, self.daily - reserved); self._save()
''', '''        reservation_id, reserved = reservation
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
''', "settle refund")
ww("providers.py", p)


# Give every task a realistic output allowance so the limiter does not reserve
# 2,048 tokens for tiny JSON/chunk calls. Daily exhaustion must not be mistaken
# for a failed chapter or section and retried repeatedly.
q = rw("pipeline.py")
q = one(q, r'''                f"Chapter title: {title}\n\nChapter text:\n\"\"\"\n{snippet}\n\"\"\""))
        except Exception:
''', r'''                f"Chapter title: {title}\n\nChapter text:\n\"\"\"\n{snippet}\n\"\"\"",
                max_tokens=900))
        except ProviderDailyLimitError:
            raise
        except Exception:
''', "chapter")
q = one(q, r'''                          f"Section notes, in order:\n\n{joined}")
    except Exception:
''', r'''                          f"Section notes, in order:\n\n{joined}",
                          max_tokens=1600)
    except ProviderDailyLimitError:
        raise
    except Exception:
''', "combine first")
q = one(
    q,
    "partials.append(fast.chat(CHUNK_SYSTEM, batch))\n        except Exception:",
    "partials.append(fast.chat(CHUNK_SYSTEM, batch, max_tokens=700))\n        except ProviderDailyLimitError:\n            raise\n        except Exception:",
    "combine batches",
)
q = one(q, r'''                          f"Section notes, in order:\n\n{small}")
    except Exception:
''', r'''                          f"Section notes, in order:\n\n{small}",
                          max_tokens=1600)
    except ProviderDailyLimitError:
        raise
    except Exception:
''', "combine final")
q = one(
    q,
    'full = synth.chat(SUMMARY_SYSTEM, f"Source:\\n\\"\\"\\"\\n{text}\\n\\"\\"\\"")',
    'full = synth.chat(SUMMARY_SYSTEM, f"Source:\\n\\"\\"\\"\\n{text}\\n\\"\\"\\"", max_tokens=1600)',
    "short summary",
)
q = one(
    q,
    '                                               f"\\"\\"\\"\\n{ch}\\n\\"\\"\\"")',
    '                                               f"\\"\\"\\"\\n{ch}\\n\\"\\"\\"", max_tokens=700)',
    "chunk summary",
)
q = one(q, r'''        return _clean_summary(synth.chat(DETAILED_SUMMARY_SYSTEM,
                                         f"Source material:\n\"\"\"\n{source}\n\"\"\""))
''', r'''        return _clean_summary(synth.chat(
            DETAILED_SUMMARY_SYSTEM,
            f"Source material:\n\"\"\"\n{source}\n\"\"\"",
            max_tokens=2600))
''', "detailed one")
q = one(q, r'''                f"\"\"\"\n{batch}\n\"\"\"")
            parts.append(_clean_summary(piece))
''', r'''                f"\"\"\"\n{batch}\n\"\"\"",
                max_tokens=2600)
            parts.append(_clean_summary(piece))
''', "detailed batch")
ww("pipeline.py", q)


# Correct model sizes and remove the old one-pass Scout wording.
b = rw("BUILD.md")
b = b.replace("One strong model (~5 GB)", "One strong model (~6.6 GB)")
b = b.replace("smallest/fastest (~2.5 GB)", "smallest/fastest (~3.4 GB)")
b = b.replace(
    "Groq is a cloud engine that summarizes with **Qwen 3.6 27B** in seconds and\nhandles long videos or whole books in one pass, thanks to its 128k-token context.",
    "Groq is a fast cloud engine using **Qwen 3.6 27B**. Sonario splits long videos, books, and document collections into rate-safe calls, then combines the results.",
)
b = b.replace(
    "- Groq has a generous free tier with per-minute rate limits. Sonario queues calls below the minute limits and follows Groq's reset headers. If the organization-wide daily quota is exhausted, switch to a local model or continue after reset.",
    "- Groq's free-tier baseline is 8K tokens/minute, 200K tokens/day, and 30 requests/minute across the whole organization. Sonario uses slightly lower working limits, follows Groq's reset headers, and shows a wait countdown. If the daily quota is exhausted, switch to a local model or continue after reset.",
)
ww("BUILD.md", b)

r = rw("README.md")
r = r.replace(
    "needs ~8 GB total for the\ntwo models.",
    "downloads about 10 GB total. Both models cannot remain fully loaded together on the\n8 GB reference GPU.",
)
r = r.replace(
    "> **Qwen3.5 9B (the default).** One strong local model that does every step at full\n> quality.",
    "> **Qwen3.5 9B (the default).** About 6.6 GB. One strong local model that does every step at full\n> quality.",
)
r = r.replace(
    "> **Qwen3.5 4B (lightweight).** The smallest, fastest local model.",
    "> **Qwen3.5 4B (lightweight).** About 3.4 GB. The smallest, fastest local model.",
)
r = r.replace(
    "Sonario mobile app. Runs much faster than local inference. Sonario splits long sources into rate-safe calls, with no local GPU load.",
    "Sonario mobile app. It runs much faster than local inference and Sonario splits long sources into rate-safe calls. There is no local GPU load.",
)
r = r.replace(
    "- **Local default (smart routing: qwen3.5:4b + qwen3.5:9b)** downloads about 10 GB total.",
    "- **Optional smart routing (qwen3.5:4b + qwen3.5:9b)** downloads about 10 GB total.",
)
r = r.replace(
    "A GPU with more VRAM (12 GB+) would hold\nboth at once and run much faster.",
    "A GPU with 16 GB or more VRAM is a safer target for keeping both loaded together.",
)
ww("README.md", r)

ig = rw(".gitignore")
if "credentials/groq_usage.json" not in ig:
    ig = ig.replace(
        "credentials/api_keys.json\n",
        "credentials/api_keys.json\ncredentials/groq_usage.json\n",
    )
ww(".gitignore", ig)


# Tests keep the limiter from regressing to updating the most recent request
# rather than the request that actually completed.
(root / "tests").mkdir(exist_ok=True)
ww("tests/test_providers.py", '''import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import providers


class ProviderTests(unittest.TestCase):
    def test_models(self):
        self.assertEqual(providers.PROVIDERS["local-qwen8b"]["model"], "qwen3.5:9b")
        self.assertEqual(providers.PROVIDERS["local-smart"]["fast_model"], "qwen3.5:4b")

    def test_groq_is_pinned(self):
        p = providers.LLMProvider("groq", base_url="https://bad", model="retired", api_key="x")
        self.assertEqual(p.model, providers.GROQ_MODEL)
        self.assertEqual(p.base_url, providers.GROQ_BASE_URL)

    def test_duration(self):
        self.assertEqual(providers._reset_seconds("1m2s"), 62)

    def test_reservations_settle_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            limiter = providers.GroqRateLimiter(Path(tmp) / "usage.json")
            first = limiter.acquire(100)
            second = limiter.acquire(200)
            limiter.settle(first, 40)
            self.assertEqual([row[1] for row in limiter.tokens], [40, 200])
            limiter.refund(second)
            self.assertEqual([row[1] for row in limiter.tokens], [40])
            self.assertEqual(limiter.daily, 40)

    def test_payload_disables_thinking(self):
        response = Mock(status_code=200, headers={})
        response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 9},
        }
        with tempfile.TemporaryDirectory() as tmp:
            limiter = providers.GroqRateLimiter(Path(tmp) / "usage.json")
            p = providers.LLMProvider("groq", api_key="x")
            with patch.object(providers, "_GROQ_LIMITER", limiter), \
                    patch.object(providers.requests, "post", return_value=response) as post:
                self.assertEqual(p.chat("s", "u", max_retries=1, max_tokens=16), "OK")
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["model"], providers.GROQ_MODEL)
            self.assertEqual(payload["reasoning_effort"], "none")
            self.assertEqual(payload["max_tokens"], 16)


if __name__ == "__main__":
    unittest.main()
''')


# Keep a normal test workflow in the repository after removing the temporary
# packaging and updater workflows.
workflow = root / ".github/workflows/python-tests.yml"
workflow.parent.mkdir(parents=True, exist_ok=True)
workflow.write_text('''name: Python tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --disable-pip-version-check requests
      - run: python -m compileall -q app.py providers.py pipeline.py
      - run: python -m unittest discover -s tests -v
''', encoding="utf-8")

(root / ".github/workflows/package-current.yml").unlink(missing_ok=True)
(root / "credentials/groq_usage.json").unlink(missing_ok=True)
