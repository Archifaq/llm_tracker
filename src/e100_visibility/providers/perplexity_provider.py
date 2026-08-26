from __future__ import annotations

import os

from .base import ProviderError, ProviderResponse
from ._http import post_json

API_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityProvider:
    """Adapter for Perplexity's OpenAI-compatible Chat Completions API.

    Perplexity's answers are grounded in live web search, so unlike the other
    two providers it reliably returns a ``citations`` list of source URLs.
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

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": query}],
        }
        data = post_json(
            self.name,
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

        if "error" in data:
            raise ProviderError(self.name, str(data["error"]))
        try:
            answer_text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {data}") from exc

        citations = list(data.get("citations", []) or [])

        return ProviderResponse(
            provider=self.name,
            model=data.get("model", self.model),
            query=query,
            answer_text=answer_text,
            citations=citations,
            raw=data,
        )
