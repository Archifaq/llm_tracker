"""LLM-based analysis of a provider's answer, plus the method dispatcher.

The brief allows either "a call to an analyzer LLM with the given system
prompt" or "equivalent deterministic logic" for this step. Both are
implemented: ``extract_heuristic`` (default, see extractor.py, unit-tested
on fixed examples) and ``analyze_with_llm`` below, selectable per
``[analysis] method`` in the config. The LLM path reuses the same
``LLMProvider`` adapters from stage 1 -- it just sends a different prompt --
so no provider-specific code is needed here.
"""

from __future__ import annotations

import json
import re

from ..config import AppConfig, BrandConfig
from ..providers import LLMProvider, ProviderError
from .extractor import extract_heuristic
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

_VALID_CATEGORIES = {
    CONTEXT_BEST,
    CONTEXT_ONE_OF_SEVERAL,
    CONTEXT_CAVEAT,
    CONTEXT_IN_PASSING,
    CONTEXT_NOT_MENTIONED,
}
_VALID_SENTIMENTS = {SENTIMENT_POSITIVE, SENTIMENT_NEUTRAL, SENTIMENT_NEGATIVE}

_SYSTEM_PROMPT = """\
Ты — аналитик видимости бренда в ответах ИИ-ассистентов (LLM/GEO-аналитика).
Твоя задача — оценить, как и на каком месте упоминается бренд {brand_name}
(сайт {brand_domain}, топливные карты для бизнеса) в ответе языковой модели
на запрос, связанный с топливными картами для компаний.

На входе:
1. QUERY — исходный запрос пользователя.
2. ANSWER — полный текст ответа LLM на этот запрос.
3. PLATFORM — какая модель дала ответ.

Разбери ANSWER и определи:
1. Упоминается ли бренд {brand_name} / {brand_domain} в любом написании
   (в том числе: {alias_list}).
2. Если да — на какой позиции по порядку среди перечисленных
   брендов/провайдеров (1 = назван первым). Если бренды не пронумерованы
   явным списком, определяй порядок по тому, в каком месте текста
   они впервые упомянуты.
3. Общее число упомянутых в ответе брендов/провайдеров и их список по порядку.
4. Контекст упоминания {brand_name}: рекомендован как лучший вариант / один из
   нескольких равнозначных / упомянут с оговоркой или недостатком /
   упомянут вскользь без оценки.
5. Тональность упоминания: позитивная / нейтральная / негативная.
6. Есть ли в ответе прямая ссылка на {brand_domain} среди источников/цитат.
7. Если {brand_name} не упомянут вовсе — какие конкуренты заняли верхние позиции.

Верни результат СТРОГО как один JSON-объект, без markdown-разметки, без
пояснений вокруг, со следующими полями:
{{
  "mentioned": true|false,
  "position": <int|null>,
  "total_brands": <int>,
  "brands_in_order": [<string>, ...],
  "context": "<1-2 предложения на русском>",
  "context_category": "best"|"one_of_several"|"caveat"|"in_passing"|"not_mentioned",
  "sentiment": "positive"|"neutral"|"negative",
  "has_source_link": true|false,
  "competitors_above": [<string>, ...]
}}

QUERY: {query}
PLATFORM: {platform}
ANSWER:
{answer}
"""

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def build_analyzer_prompt(*, brand: BrandConfig, query: str, answer_text: str, platform: str) -> str:
    return _SYSTEM_PROMPT.format(
        brand_name=brand.name,
        brand_domain=brand.domain,
        alias_list=", ".join(brand.aliases),
        query=query,
        platform=platform,
        answer=answer_text or "(pusta odpowiedź)",
    )


def analyze_with_llm(
    provider: LLMProvider,
    *,
    brand: BrandConfig,
    query: str,
    answer_text: str,
    platform: str,
    language: str,
    country: str,
) -> AnalysisResult:
    prompt = build_analyzer_prompt(brand=brand, query=query, answer_text=answer_text, platform=platform)

    try:
        response = provider.ask(prompt, language=language, country=country)
    except ProviderError as exc:
        return _error_result(f"analyzer call failed: {exc.message}")

    match = _JSON_BLOCK.search(response.answer_text)
    if not match:
        return _error_result(f"analyzer did not return JSON: {response.answer_text[:200]!r}")

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return _error_result(f"analyzer returned malformed JSON: {exc}")

    return _result_from_llm_json(data)


def _result_from_llm_json(data: dict) -> AnalysisResult:
    category = data.get("context_category", CONTEXT_NOT_MENTIONED)
    if category not in _VALID_CATEGORIES:
        category = CONTEXT_NOT_MENTIONED
    sentiment = data.get("sentiment", SENTIMENT_NEUTRAL)
    if sentiment not in _VALID_SENTIMENTS:
        sentiment = SENTIMENT_NEUTRAL

    return AnalysisResult(
        mentioned=bool(data.get("mentioned", False)),
        position=data.get("position"),
        total_brands=int(data.get("total_brands", 0) or 0),
        brands_in_order=tuple(data.get("brands_in_order", []) or []),
        context=str(data.get("context", "")),
        context_category=category,
        sentiment=sentiment,
        has_source_link=bool(data.get("has_source_link", False)),
        competitors_above=tuple(data.get("competitors_above", []) or []),
        method="llm",
    )


def _error_result(message: str) -> AnalysisResult:
    return AnalysisResult(
        mentioned=False,
        position=None,
        total_brands=0,
        brands_in_order=(),
        context="",
        context_category=CONTEXT_NOT_MENTIONED,
        sentiment=SENTIMENT_NEUTRAL,
        has_source_link=False,
        competitors_above=(),
        method="llm",
        error=message,
    )


def analyze(
    *,
    config: AppConfig,
    analyzer_provider: LLMProvider | None,
    query: str,
    answer_text: str,
    citations: tuple[str, ...],
    platform: str,
) -> AnalysisResult:
    """Dispatch to the configured analysis method.

    Falls back to the heuristic extractor if ``method = "llm"`` but the LLM
    call/parse fails, so a flaky analyzer call degrades gracefully instead of
    losing the observation.
    """
    if config.analysis.method == "llm" and analyzer_provider is not None:
        result = analyze_with_llm(
            analyzer_provider,
            brand=config.brand,
            query=query,
            answer_text=answer_text,
            platform=platform,
            language=config.market.language,
            country=config.market.country,
        )
        if result.ok:
            return result
        fallback = extract_heuristic(
            answer_text=answer_text,
            citations=citations,
            brand=config.brand,
            competitors=config.competitors,
        )
        return AnalysisResult(**{**fallback.__dict__, "error": f"llm analyzer failed, used heuristic fallback: {result.error}"})

    return extract_heuristic(
        answer_text=answer_text,
        citations=citations,
        brand=config.brand,
        competitors=config.competitors,
    )
