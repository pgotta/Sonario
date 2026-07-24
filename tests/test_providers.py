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

    def test_groq_chat_json_enables_json_object_mode(self):
        response = Mock(status_code=200, headers={})
        response.json.return_value = {
            "choices": [{"message": {"content": '{"gist":"ok"}'}}],
            "usage": {"total_tokens": 12},
        }
        with tempfile.TemporaryDirectory() as tmp:
            limiter = providers.GroqRateLimiter(Path(tmp) / "usage.json")
            p = providers.LLMProvider("groq", api_key="x")
            with patch.object(providers, "_GROQ_LIMITER", limiter), \
                    patch.object(providers.requests, "post", return_value=response) as post:
                self.assertEqual(p.chat_json("Return JSON.", "Document", max_retries=1), {"gist": "ok"})
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["reasoning_format"], "hidden")
            self.assertEqual(payload["temperature"], 0.2)
            self.assertGreaterEqual(payload["max_completion_tokens"], 1200)

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
            self.assertEqual(payload["max_completion_tokens"], 16)

    def test_groq_chat_json_retries_with_more_room_after_truncation(self):
        first = Mock(status_code=200, headers={})
        first.json.return_value = {
            "choices": [{"message": {"content": '{"gist":"partial","themes":['},
                         "finish_reason": "length"}],
            "usage": {"completion_tokens": 1200, "total_tokens": 1300},
        }
        second = Mock(status_code=200, headers={})
        second.json.return_value = {
            "choices": [{"message": {"content": '{"gist":"complete","themes":[]}'},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 20, "total_tokens": 120},
        }
        with tempfile.TemporaryDirectory() as tmp:
            limiter = providers.GroqRateLimiter(Path(tmp) / "usage.json")
            p = providers.LLMProvider("groq", api_key="x")
            with patch.object(providers, "_GROQ_LIMITER", limiter), \
                    patch.object(providers.requests, "post", side_effect=[first, second]) as post:
                result = p.chat_json("Return JSON.", "Document", max_retries=1, max_tokens=700,
                                     diagnostic_label="dense.txt")
        self.assertEqual(result["gist"], "complete")
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload["max_completion_tokens"], 1200)
        self.assertEqual(second_payload["max_completion_tokens"], 1800)

    def test_json_is_cleaned_after_parsing(self):
        response = Mock(status_code=200, headers={})
        response.json.return_value = {
            "choices": [{"message": {"content": '{"gist":"one — two"}'},
                         "finish_reason": "stop"}],
            "usage": {"total_tokens": 12},
        }
        with tempfile.TemporaryDirectory() as tmp:
            limiter = providers.GroqRateLimiter(Path(tmp) / "usage.json")
            p = providers.LLMProvider("groq", api_key="x")
            with patch.object(providers, "_GROQ_LIMITER", limiter), \
                    patch.object(providers.requests, "post", return_value=response):
                result = p.chat_json("Return JSON.", "Document", max_retries=1)
        self.assertEqual(result, {"gist": "one, two"})


if __name__ == "__main__":
    unittest.main()
