"""Provider adapters: request-body shape and citation extraction.

Mocks the HTTP layer (``post_json``) so no test makes a real network call.
Response fixtures mirror the documented shapes for each API (OpenAI Chat
Completions ``message.annotations[].url_citation``, Gemini ``generateContent``
``groundingMetadata.groundingChunks[].web``), not invented structures.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from e100_visibility.providers.gemini_provider import GeminiProvider
from e100_visibility.providers.openai_provider import OpenAIProvider

OPENAI_RESPONSE_WITH_CITATION = {
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "model": "gpt-5-search-api",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Najlepszą kartą paliwową dla firm jest E100 [1].",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": "https://e100.eu/oferta",
                            "title": "E100 - karty paliwowe dla firm",
                            "start_index": 30,
                            "end_index": 47,
                        },
                    }
                ],
            },
            "finish_reason": "stop",
        }
    ],
}

GEMINI_RESPONSE_WITH_GROUNDING = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"text": "Najlepszą kartą paliwową dla firm jest E100."}],
            },
            "groundingMetadata": {
                "groundingChunks": [
                    {"web": {"uri": "https://vertexaisearch.cloud.google.com/redirect/abc", "title": "e100.eu"}}
                ],
                "groundingSupports": [],
            },
        }
    ]
}


class OpenAIProviderWebSearchTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"OPENAI_API_KEY_TEST": "test-key"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_request_payload_enables_web_search(self):
        provider = OpenAIProvider(name="openai", model="gpt-5-search-api", api_key_env="OPENAI_API_KEY_TEST")

        with patch("e100_visibility.providers.openai_provider.post_json") as mock_post:
            mock_post.return_value = OPENAI_RESPONSE_WITH_CITATION
            provider.ask("query", language="pl", country="PL")

        _, kwargs = mock_post.call_args
        self.assertIn("web_search_options", kwargs["payload"])
        self.assertEqual(kwargs["payload"]["web_search_options"], {})
        self.assertEqual(kwargs["payload"]["model"], "gpt-5-search-api")

    def test_extracts_url_citation_from_annotations(self):
        provider = OpenAIProvider(name="openai", model="gpt-5-search-api", api_key_env="OPENAI_API_KEY_TEST")

        with patch("e100_visibility.providers.openai_provider.post_json") as mock_post:
            mock_post.return_value = OPENAI_RESPONSE_WITH_CITATION
            response = provider.ask("query", language="pl", country="PL")

        self.assertEqual(response.citations, ["https://e100.eu/oferta"])
        self.assertIn("E100", response.answer_text)

    def test_missing_annotations_yields_no_citations(self):
        provider = OpenAIProvider(name="openai", model="gpt-5-search-api", api_key_env="OPENAI_API_KEY_TEST")
        response_without_citations = {
            "choices": [{"message": {"role": "assistant", "content": "Brak informacji."}}]
        }

        with patch("e100_visibility.providers.openai_provider.post_json") as mock_post:
            mock_post.return_value = response_without_citations
            response = provider.ask("query", language="pl", country="PL")

        self.assertEqual(response.citations, [])


class GeminiProviderWebSearchTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"GEMINI_API_KEY_TEST": "test-key"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_request_payload_enables_google_search_tool(self):
        provider = GeminiProvider(name="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY_TEST")

        with patch("e100_visibility.providers.gemini_provider.post_json") as mock_post:
            mock_post.return_value = GEMINI_RESPONSE_WITH_GROUNDING
            provider.ask("query", language="pl", country="PL")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["payload"]["tools"], [{"google_search": {}}])

    def test_extracts_grounding_chunk_uri(self):
        provider = GeminiProvider(name="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY_TEST")

        with patch("e100_visibility.providers.gemini_provider.post_json") as mock_post:
            mock_post.return_value = GEMINI_RESPONSE_WITH_GROUNDING
            response = provider.ask("query", language="pl", country="PL")

        self.assertEqual(response.citations, ["https://vertexaisearch.cloud.google.com/redirect/abc"])
        self.assertIn("E100", response.answer_text)

    def test_missing_grounding_metadata_yields_no_citations(self):
        provider = GeminiProvider(name="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY_TEST")
        response_without_grounding = {
            "candidates": [{"content": {"role": "model", "parts": [{"text": "Brak informacji."}]}}]
        }

        with patch("e100_visibility.providers.gemini_provider.post_json") as mock_post:
            mock_post.return_value = response_without_grounding
            response = provider.ask("query", language="pl", country="PL")

        self.assertEqual(response.citations, [])


if __name__ == "__main__":
    unittest.main()
