import tempfile
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
