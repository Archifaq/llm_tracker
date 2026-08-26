"""Provider registry: maps a config ``kind`` string to an adapter class.

To add a new LLM provider: write a class in this package implementing the
``LLMProvider`` protocol (see ``base.py``), then add one line here. Nothing
in the orchestrator, analysis step, or CLI needs to change.
"""

from __future__ import annotations

from typing import Callable

from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider
from .perplexity_provider import PerplexityProvider

_FACTORIES: dict[str, Callable[..., object]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "perplexity": PerplexityProvider,
}


def register_provider(kind: str, factory: Callable[..., object]) -> None:
    """Register an additional provider kind at runtime (e.g. from a plugin)."""
    _FACTORIES[kind] = factory


def build_provider(kind: str, **kwargs) -> object:
    try:
        factory = _FACTORIES[kind]
    except KeyError as exc:
        known = ", ".join(sorted(_FACTORIES)) or "(none registered)"
        raise ValueError(f"unknown provider kind '{kind}'; known kinds: {known}") from exc
    return factory(**kwargs)
