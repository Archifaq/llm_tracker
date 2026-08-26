"""The one record that flows from fetch -> analysis -> storage -> report.

Combines a provider's raw answer (or fetch error) with its analysis result
so both the audit trail (raw answer, raw API payload) and the extracted
structured data live in a single row per query x provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis.schema import AnalysisResult


@dataclass(frozen=True)
class Observation:
    run_id: int
    timestamp: str
    provider: str
    model: str
    query: str
    language: str
    country: str
    answer_text: str | None
    citations: tuple[str, ...] = field(default_factory=tuple)
    raw: dict = field(default_factory=dict)
    fetch_error: str | None = None
    analysis: AnalysisResult | None = None

    @property
    def fetch_ok(self) -> bool:
        return self.fetch_error is None
