"""Provider adapters: request-body shape and citation extraction.

Mocks the HTTP layer (``post_json``) so no test makes a real network call.
Response fixtures mirror the documented shapes for each API (OpenAI Chat
Completions ``message.annotations[].url_citation``, Gemini ``generateContent``
``groundingMetadata.groundingChunks[].web``), not invented structures.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from e100_visibility.providers.base import ProviderError
from e100_visibility.providers.claude_provider import ClaudeProvider
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

CLAUDE_RESPONSE_WITH_CITATION = {
    "id": "msg_abc123",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5",
    "content": [
        {
            "type": "server_tool_use",
            "id": "srvtoolu_01",
            "name": "web_search",
            "input": {"query": "najlepsze karty paliwowe dla firm w Polsce"},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_01",
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://e100.eu/oferta",
                    "title": "E100 - karty paliwowe dla firm",
                    "page_age": "2026-01-01",
                }
            ],
        },
        {
            "type": "text",
            "text": "Najlepszą kartą paliwową dla firm jest E100.",
            "citations": [
                {
                    "type": "web_search_result_location",
                    "url": "https://e100.eu/oferta",
                    "title": "E100 - karty paliwowe dla firm",
                    "cited_text": "E100 oferuje elastyczne limity",
                    "encrypted_index": "abc123",
                }
            ],
        },
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 100, "output_tokens": 50},
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


class ClaudeProviderWebSearchTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"ANTHROPIC_API_KEY_TEST": "test-key"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_request_payload_enables_web_search(self):
        provider = ClaudeProvider(name="claude", model="claude-sonnet-5", api_key_env="ANTHROPIC_API_KEY_TEST")

        with patch("e100_visibility.providers.claude_provider.post_json") as mock_post:
            mock_post.return_value = CLAUDE_RESPONSE_WITH_CITATION
            provider.ask("query", language="pl", country="PL")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["payload"]["tools"], [{"type": "web_search_20260209", "name": "web_search"}])
        self.assertEqual(kwargs["payload"]["model"], "claude-sonnet-5")
        self.assertEqual(kwargs["payload"]["max_tokens"], 1024)
        self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(kwargs["headers"]["x-api-key"], "test-key")

    def test_extracts_text_and_citations(self):
        provider = ClaudeProvider(name="claude", model="claude-sonnet-5", api_key_env="ANTHROPIC_API_KEY_TEST")

        with patch("e100_visibility.providers.claude_provider.post_json") as mock_post:
            mock_post.return_value = CLAUDE_RESPONSE_WITH_CITATION
            response = provider.ask("query", language="pl", country="PL")

        self.assertIn("E100", response.answer_text)
        self.assertEqual(response.citations, ["https://e100.eu/oferta"])

    def test_missing_citations_yields_no_citations(self):
        provider = ClaudeProvider(name="claude", model="claude-sonnet-5", api_key_env="ANTHROPIC_API_KEY_TEST")
        response_without_citations = {
            "content": [{"type": "text", "text": "Brak informacji."}],
        }

        with patch("e100_visibility.providers.claude_provider.post_json") as mock_post:
            mock_post.return_value = response_without_citations
            response = provider.ask("query", language="pl", country="PL")

        self.assertEqual(response.citations, [])
        self.assertEqual(response.answer_text, "Brak informacji.")

    def test_missing_api_key_raises_provider_error(self):
        provider = ClaudeProvider(name="claude", model="claude-sonnet-5", api_key_env="DOES_NOT_EXIST_KEY")

        with self.assertRaises(ProviderError):
            provider.ask("query", language="pl", country="PL")

    def test_error_in_response_body_raises_provider_error(self):
        provider = ClaudeProvider(name="claude", model="claude-sonnet-5", api_key_env="ANTHROPIC_API_KEY_TEST")
        error_response = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad request"}}

        with patch("e100_visibility.providers.claude_provider.post_json") as mock_post:
            mock_post.return_value = error_response
            with self.assertRaises(ProviderError) as ctx:
                provider.ask("query", language="pl", country="PL")

        self.assertIn("bad request", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
