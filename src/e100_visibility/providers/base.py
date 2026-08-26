"""Common adapter interface every LLM provider must implement.

Adding a new provider means writing one class that implements ``LLMProvider``
and registering it in ``registry.py`` -- the orchestrator and analysis step
never need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Raised by a provider adapter when a single call fails.

    Carries enough context for the orchestrator to record the failure in the
    run history and report without aborting the rest of the pipeline.
    """

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderResponse:
    """Result of asking one provider one query."""

    provider: str
    model: str
    query: str
    answer_text: str
    citations: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    """Adapter contract. Implementations must not raise anything except
    ``ProviderError`` -- network/SDK exceptions must be caught and translated.
    """

    name: str
    model: str

    def ask(self, query: str, *, language: str, country: str) -> ProviderResponse:
        """Send ``query`` (already phrased in the target market's language)
        and return the raw answer. ``language``/``country`` are passed
        through so a provider can set locale hints (e.g. Gemini's
        ``generationConfig``) without the caller needing provider-specific
        knowledge.
        """
        ...
