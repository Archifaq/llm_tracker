"""The structured data every analysis method (heuristic or LLM) produces.

This is the one shape the storage and reporting stages consume, regardless
of which analyzer produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CONTEXT_BEST = "best"
CONTEXT_ONE_OF_SEVERAL = "one_of_several"
CONTEXT_CAVEAT = "caveat"
CONTEXT_IN_PASSING = "in_passing"
CONTEXT_NOT_MENTIONED = "not_mentioned"

SENTIMENT_POSITIVE = "positive"
SENTIMENT_NEUTRAL = "neutral"
SENTIMENT_NEGATIVE = "negative"


@dataclass(frozen=True)
class AnalysisResult:
    mentioned: bool
    position: int | None
    total_brands: int
    brands_in_order: tuple[str, ...]
    context: str
    context_category: str
    sentiment: str
    has_source_link: bool
    competitors_above: tuple[str, ...] = field(default_factory=tuple)
    method: str = "heuristic"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
