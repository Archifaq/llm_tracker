"""Offline demo adapter -- for trying the CLI/report interface end-to-end
without any API key or network call, while a real key is being arranged.

Not a mock of a specific real provider: it deterministically picks one of a
few canned Polish answers per (provider name, query) pair, so a demo run
produces a report with realistic variety (some queries mention E100 first,
some not at all, some with a caveat) instead of one repeated line. Same
config + same queries always produce the same "answers", so a demo run is
reproducible and its trend section is meaningful across repeated runs.

Never register this under a name a real config could reach by accident --
it is opt-in via `kind = "offline"` in a config file, never a fallback.
"""

from __future__ import annotations

import hashlib

from .base import ProviderResponse

_ANSWER_TEMPLATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "1. E100 - najlepsza karta paliwowa dla firm, elastyczne limity i szeroka "
        "sieć akceptacji (https://e100.eu/oferta).\n"
        "2. DKV - dobra alternatywa z siecią stacji w całej Europie.\n"
        "3. Shell - również popularna opcja dla mniejszych flot.",
        ("https://e100.eu/oferta",),
    ),
    (
        "Popularne karty paliwowe dla firm w Polsce to DKV, Shell oraz E100. "
        "Wszystkie oferują podobny zakres funkcji, różnią się jednak zasięgiem "
        "sieci stacji i warunkami cenowymi.",
        (),
    ),
    (
        "Do rozważenia są DKV oraz Shell - obie firmy mają ugruntowaną pozycję "
        "na rynku kart flotowych i szeroką sieć akceptacji w całej Europie.",
        (),
    ),
    (
        "E100 jest jedną z opcji, jednak niestety ma ograniczoną sieć akceptacji "
        "w porównaniu do UTA, która dominuje wśród międzynarodowych przewoźników.",
        (),
    ),
)


class OfflineDemoProvider:
    """No network, no API key -- picks a canned answer deterministically."""

    def __init__(self, *, name: str, model: str = "offline-demo", api_key_env: str | None = None, timeout_seconds: float = 60.0) -> None:
        self.name = name
        self.model = model

    def ask(self, query: str, *, language: str, country: str) -> ProviderResponse:
        digest = hashlib.sha256(f"{self.name}:{query}".encode("utf-8")).digest()
        answer_text, citations = _ANSWER_TEMPLATES[digest[0] % len(_ANSWER_TEMPLATES)]

        return ProviderResponse(
            provider=self.name,
            model=self.model,
            query=query,
            answer_text=answer_text,
            citations=citations,
            raw={"offline_demo": True},
        )
