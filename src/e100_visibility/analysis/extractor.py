"""Deterministic, local extraction of E100's mention/position from an LLM
answer -- no extra API call, no non-determinism, fully unit-testable.

Limitation (documented, not hidden): a competitor is only recognised if it
appears in the ``competitors`` config list. Unlisted competitors are simply
invisible to this method; use ``analysis.method = "llm"`` (see analyzer.py)
for open-vocabulary recognition at the cost of one extra LLM call per
query x provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import BrandConfig, CompetitorConfig
from .schema import (
    CONTEXT_BEST,
    CONTEXT_CAVEAT,
    CONTEXT_IN_PASSING,
    CONTEXT_NOT_MENTIONED,
    CONTEXT_ONE_OF_SEVERAL,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
    AnalysisResult,
)

_MIN_ANSWER_LENGTH = 5

# Keyword cues are intentionally multilingual-ish (Polish first, since it's
# the first market) but simple substring checks so the config's brand name
# and this module never need to agree on a specific language.
_POSITIVE_WORDS = (
    "najlepsz", "najlepiej", "polec", "topow", "top ", "lider", "wiodąc",
    "najbardziej opłacaln", "najkorzystniej", "rekomend", "wyróżnia się",
    "best", "recommended", "top choice", "leading",
)
_CAVEAT_WORDS = (
    "niestety", "jednak", "wadą", "minus", "ograniczon", "brak", "gorsz",
    "mniej znan", "nie oferuje", "problem", "trudno znaleźć", "mało informacji",
    "however", "unfortunately", "downside", "drawback", "limited",
)

_URL_PATTERN_TEMPLATE = r"https?://\S*{domain}\S*"
_NUMBERED_LINE = re.compile(r"^\s*(\d{1,2})[.)]\s+(.*)$")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


@dataclass(frozen=True)
class _Entity:
    name: str
    pattern: re.Pattern[str]


def _alias_pattern(aliases: tuple[str, ...]) -> re.Pattern[str]:
    escaped = "|".join(re.escape(alias) for alias in aliases)
    return re.compile(rf"(?<!\w)(?:{escaped})(?!\w)", re.IGNORECASE)


def _build_entities(brand: BrandConfig, competitors: tuple[CompetitorConfig, ...]) -> list[_Entity]:
    brand_aliases = tuple(brand.aliases) + (brand.domain,)
    entities = [_Entity(brand.name, _alias_pattern(brand_aliases))]
    entities.extend(_Entity(c.name, _alias_pattern(c.aliases)) for c in competitors)
    return entities


def _first_occurrence(text: str, entity: _Entity) -> int | None:
    match = entity.pattern.search(text)
    return match.start() if match else None


def _numbered_list_ranks(text: str, entities: list[_Entity]) -> dict[str, int]:
    """If the answer contains an explicit numbered list, map each entity
    found in it to its list rank. Returns {} if fewer than two entities are
    covered, in which case first-occurrence order is used instead.
    """
    ranks: dict[str, int] = {}
    for line in text.splitlines():
        match = _NUMBERED_LINE.match(line)
        if not match:
            continue
        rank = int(match.group(1))
        line_body = match.group(2)
        for entity in entities:
            if entity.name in ranks:
                continue
            if entity.pattern.search(line_body):
                ranks[entity.name] = rank
    return ranks if len(ranks) >= 2 else {}


def _mention_sentence(text: str, index: int) -> str:
    for sentence in _SENTENCE_SPLIT.split(text):
        if sentence.strip() == "":
            continue
        start = text.find(sentence)
        if start <= index < start + len(sentence):
            return sentence.strip()
    return text[max(0, index - 80) : index + 80].strip()


def _classify(sentence: str, position: int, total: int) -> tuple[str, str, str]:
    lowered = sentence.lower()
    has_caveat = any(word in lowered for word in _CAVEAT_WORDS)
    has_positive = any(word in lowered for word in _POSITIVE_WORDS)

    if has_caveat:
        return (
            CONTEXT_CAVEAT,
            SENTIMENT_NEGATIVE,
            "Бренд упомянут с оговоркой или недостатком.",
        )
    if has_positive and position == 1:
        return (
            CONTEXT_BEST,
            SENTIMENT_POSITIVE,
            "Бренд рекомендован как лучший или ведущий вариант.",
        )
    if total > 1:
        return (
            CONTEXT_ONE_OF_SEVERAL,
            SENTIMENT_NEUTRAL,
            "Бренд упомянут как один из нескольких равнозначных вариантов.",
        )
    return (
        CONTEXT_IN_PASSING,
        SENTIMENT_NEUTRAL,
        "Бренд упомянут вскользь без отдельной оценки.",
    )


def extract_heuristic(
    *,
    answer_text: str,
    citations: tuple[str, ...],
    brand: BrandConfig,
    competitors: tuple[CompetitorConfig, ...],
) -> AnalysisResult:
    if not answer_text or len(answer_text.strip()) < _MIN_ANSWER_LENGTH:
        return AnalysisResult(
            mentioned=False,
            position=None,
            total_brands=0,
            brands_in_order=(),
            context="Ответ пуст или слишком короткий для анализа.",
            context_category=CONTEXT_NOT_MENTIONED,
            sentiment=SENTIMENT_NEUTRAL,
            has_source_link=False,
            competitors_above=(),
            method="heuristic",
        )

    entities = _build_entities(brand, competitors)
    occurrences = {e.name: _first_occurrence(answer_text, e) for e in entities}
    found = [e for e in entities if occurrences[e.name] is not None]

    domain_url_pattern = re.compile(_URL_PATTERN_TEMPLATE.format(domain=re.escape(brand.domain)), re.IGNORECASE)
    has_source_link = any(brand.domain.lower() in c.lower() for c in citations) or bool(
        domain_url_pattern.search(answer_text)
    )

    if not found:
        return AnalysisResult(
            mentioned=False,
            position=None,
            total_brands=0,
            brands_in_order=(),
            context=f"Бренд {brand.name} не упомянут в ответе.",
            context_category=CONTEXT_NOT_MENTIONED,
            sentiment=SENTIMENT_NEUTRAL,
            has_source_link=has_source_link,
            competitors_above=(),
            method="heuristic",
        )

    ranks = _numbered_list_ranks(answer_text, found)
    if ranks:
        order = sorted(found, key=lambda e: ranks.get(e.name, max(ranks.values()) + 1))
    else:
        order = sorted(found, key=lambda e: occurrences[e.name])

    names_in_order = tuple(e.name for e in order)

    if brand.name not in names_in_order:
        # Only competitors were recognised -- e.g. the brand's aliases don't
        # cover how the model referred to it. Surface the competitors that
        # did get named so the report can still say who leads.
        return AnalysisResult(
            mentioned=False,
            position=None,
            total_brands=len(order),
            brands_in_order=names_in_order,
            context=f"Бренд {brand.name} не упомянут в ответе.",
            context_category=CONTEXT_NOT_MENTIONED,
            sentiment=SENTIMENT_NEUTRAL,
            has_source_link=has_source_link,
            competitors_above=names_in_order,
            method="heuristic",
        )

    position = names_in_order.index(brand.name) + 1
    competitors_above = names_in_order[: position - 1]

    sentence = _mention_sentence(answer_text, occurrences[brand.name])
    category, sentiment, context = _classify(sentence, position, len(order))

    return AnalysisResult(
        mentioned=True,
        position=position,
        total_brands=len(order),
        brands_in_order=names_in_order,
        context=context,
        context_category=category,
        sentiment=sentiment,
        has_source_link=has_source_link,
        competitors_above=competitors_above,
        method="heuristic",
    )
