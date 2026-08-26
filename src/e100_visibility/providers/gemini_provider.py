from __future__ import annotations

import os
import urllib.parse

from .base import ProviderError, ProviderResponse
from ._http import post_json

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    """Adapter for Google's Gemini API (generateContent).

    Always enables the ``google_search`` tool so the model grounds its
    answer in live search results and returns ``groundingChunks`` (without
    it, Gemini answers from training data alone and ``has_source_link`` in
    the analysis step is never true). Works as a normal tool call on an
    existing model -- no dedicated search model needed, unlike OpenAI's
    Chat Completions API. The Gemini API rejects mixing a search tool with
    non-search tools in the same request; since this adapter only ever
    sends this one tool, that restriction doesn't apply here.
    """

    def __init__(self, *, name: str, model: str, api_key_env: str, timeout_seconds: float = 60.0) -> None:
        self.name = name
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def ask(self, query: str, *, language: str, country: str) -> ProviderResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ProviderError(self.name, f"environment variable {self.api_key_env} is not set")

        url = API_URL_TEMPLATE.format(model=urllib.parse.quote(self.model))
        payload = {
            "contents": [{"parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
        data = post_json(
            self.name,
            url,
            headers={"x-goog-api-key": api_key},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

        if "error" in data:
            raise ProviderError(self.name, str(data["error"]))
        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            answer_text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {data}") from exc

        citations = _extract_grounding_citations(candidate)

        return ProviderResponse(
            provider=self.name,
            model=self.model,
            query=query,
            answer_text=answer_text,
            citations=citations,
            raw=data,
        )


def _extract_grounding_citations(candidate: dict) -> list[str]:
    """Best-effort extraction of grounding/source URLs when Gemini's search
    grounding is enabled for the configured model."""
    metadata = candidate.get("groundingMetadata", {}) or {}
    chunks = metadata.get("groundingChunks", []) or []
    urls = []
    for chunk in chunks:
        uri = chunk.get("web", {}).get("uri")
        if uri:
            urls.append(uri)
    return urls
