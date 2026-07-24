import unittest

import pipeline


class FakeProvider:
    def __init__(self, compact):
        self.compact = compact
        self.calls = []

    def chat_json(self, system, user, **kwargs):
        self.calls.append(("json", kwargs))
        return None

    def chat(self, system, user, **kwargs):
        self.calls.append(("text", kwargs))
        return self.compact


class PipelineFallbackTests(unittest.TestCase):
    def test_compact_format_recovers_failed_json(self):
        compact = (
            "GIST: A concise summary.\n"
            "THEMES: family | boundaries\n"
            "VALENCE: mixed\n"
            "ENERGY: NONE\n"
            "FRICTION: conflict | pressure\n"
            "IDEAS: reflection\n"
            "ACTIONS: set a boundary\n"
            "PEOPLE: parent"
        )
        provider = FakeProvider(compact)
        note = pipeline.map_document(provider, "A sufficiently long document for analysis.",
                                     diagnostic_label="sample.txt")
        self.assertEqual(note["gist"], "A concise summary.")
        self.assertEqual(note["themes"], ["family", "boundaries"])
        self.assertEqual(note["_fallback"], "compact")
        self.assertEqual(provider.calls[0][1]["max_tokens"], 1200)

    def test_local_fallback_never_discards_document(self):
        provider = FakeProvider("unparseable response")
        note = pipeline.map_document(
            provider,
            "Boundaries matter. Family pressure appears repeatedly in these notes.",
            diagnostic_label="sample.txt",
        )
        self.assertTrue(note["gist"])
        self.assertEqual(note["_fallback"], "local")
        self.assertIn("family", note["themes"])


if __name__ == "__main__":
    unittest.main()
