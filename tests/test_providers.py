import unittest
from unittest.mock import Mock, patch
import providers

class Tests(unittest.TestCase):
    def test_models(self):
        self.assertEqual(providers.PROVIDERS["local-qwen8b"]["model"], "qwen3.5:9b")
        self.assertEqual(providers.PROVIDERS["local-smart"]["fast_model"], "qwen3.5:4b")
    def test_groq_is_pinned(self):
        p=providers.LLMProvider("groq", base_url="https://bad", model="old", api_key="x")
        self.assertEqual(p.model, providers.GROQ_MODEL); self.assertEqual(p.base_url, providers.GROQ_BASE_URL)
    def test_duration(self):
        self.assertEqual(providers._reset_seconds("1m2s"), 62)
    def test_payload(self):
        response=Mock(status_code=200, headers={}); response.json.return_value={"choices":[{"message":{"content":"OK"}}],"usage":{"total_tokens":9}}
        p=providers.LLMProvider("groq", api_key="x")
        with patch.object(providers.requests,"post",return_value=response):
            self.assertEqual(p.chat("s","u",max_retries=1,max_tokens=16),"OK")
if __name__ == "__main__": unittest.main()
