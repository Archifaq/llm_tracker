from __future__ import annotations

import os

from .base import ProviderError, ProviderResponse
from ._http import post_json

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class ClaudeProvider:
    """Adapter for Anthropic's Messages API (Claude models).

    Always enables the server-side ``web_search`` tool so the model grounds
    its answer in live results and attaches citations to the text blocks
    that used them (otherwise Claude answers from training data alone and
    ``has_source_link`` in the analysis step is never true). Uses
    ``web_search_20260209`` -- the current dynamic-filtering variant for
    Sonnet 5/Opus 5/4.6+ -- not the older ``web_search_20250305`` basic
    variant kept only for pre-4.6 models.
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
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": query}],
            "tools": [{"type": "web_search_20260209", "name": "web_search"}],
        }
        data = post_json(
            self.name,
            API_URL,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

        if "error" in data:
            raise ProviderError(self.name, str(data["error"]))
        try:
            content_blocks = data["content"]
            answer_text = "".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {data}") from exc

        citations = _extract_web_search_citations(content_blocks)

        return ProviderResponse(
            provider=self.name,
            model=data.get("model", self.model),
            query=query,
            answer_text=answer_text,
            citations=citations,
            raw=data,
        )


def _extract_web_search_citations(content_blocks: list) -> list[str]:
    """Best-effort extraction of URLs from the ``citations`` array Claude
    attaches to individual text blocks when the web_search tool was used."""
    urls = []
    for block in content_blocks:
        if block.get("type") != "text":
            continue
        for citation in block.get("citations", []) or []:
            url = citation.get("url")
            if url:
                urls.append(url)
    return urls
