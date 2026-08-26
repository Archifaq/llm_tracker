"""Turns a flat list of observations into the numbers the final report needs:
per-provider and overall share of voice / average position, top competitors,
fully-absent queries, run-over-run trend, and a handful of rule-based
observations. Deliberately no LLM call here -- aggregation must be
reproducible from the stored history alone.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from ..models import Observation

_TREND_EPSILON = 0.01


@dataclass(frozen=True)
class ProviderStats:
    provider: str
    total_queries: int
    successful_queries: int
    mentioned_count: int
    share_of_voice_pct: float | None
    avg_position: float | None


@dataclass(frozen=True)
class CompetitorStat:
    name: str
    frequency: int
    avg_position: float | None


@dataclass(frozen=True)
class TrendMetric:
    current: float | None
    previous: float | None
    delta: float | None
    direction: str  # "up" | "down" | "flat" | "n/a"


@dataclass(frozen=True)
class ProviderTrend:
    provider: str
    share_of_voice: TrendMetric
    avg_position: TrendMetric


@dataclass(frozen=True)
class ErrorEntry:
    provider: str
    query: str
    message: str


@dataclass(frozen=True)
class Aggregate:
    brand_name: str
    per_provider: tuple[ProviderStats, ...]
    overall: ProviderStats
    top_competitors: tuple[CompetitorStat, ...]
    absent_queries: tuple[str, ...]
    errors: tuple[ErrorEntry, ...]
    trend_overall: ProviderTrend | None
    trend_per_provider: tuple[ProviderTrend, ...]
    recommendations: tuple[str, ...]


def _group_by_provider(observations: list[Observation]) -> dict[str, list[Observation]]:
    groups: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[obs.provider].append(obs)
    return dict(groups)


def _stats_for(provider: str, observations: list[Observation]) -> ProviderStats:
    successful = [o for o in observations if o.fetch_ok and o.analysis is not None]
    mentioned = [o for o in successful if o.analysis.mentioned]
    share = (len(mentioned) / len(successful) * 100.0) if successful else None
    avg_pos = mean(o.analysis.position for o in mentioned) if mentioned else None
    return ProviderStats(
        provider=provider,
        total_queries=len(observations),
        successful_queries=len(successful),
        mentioned_count=len(mentioned),
        share_of_voice_pct=share,
        avg_position=avg_pos,
    )


def _top_competitors(observations: list[Observation], brand_name: str, limit: int = 5) -> tuple[CompetitorStat, ...]:
    positions_by_name: dict[str, list[int]] = defaultdict(list)
    for obs in observations:
        if not (obs.fetch_ok and obs.analysis is not None):
            continue
        for index, name in enumerate(obs.analysis.brands_in_order, start=1):
            if name == brand_name:
                continue
            positions_by_name[name].append(index)

    stats = [
        CompetitorStat(name=name, frequency=len(positions), avg_position=mean(positions))
        for name, positions in positions_by_name.items()
    ]
    stats.sort(key=lambda s: (-s.frequency, s.avg_position if s.avg_position is not None else float("inf")))
    return tuple(stats[:limit])


def _absent_queries(observations: list[Observation]) -> tuple[str, ...]:
    by_query: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.fetch_ok and obs.analysis is not None:
            by_query[obs.query].append(obs)

    absent = []
    for query, obs_list in by_query.items():
        if obs_list and not any(o.analysis.mentioned for o in obs_list):
            absent.append(query)
    return tuple(absent)


def _errors(observations: list[Observation]) -> tuple[ErrorEntry, ...]:
    entries = []
    for obs in observations:
        if obs.fetch_error is not None:
            entries.append(ErrorEntry(obs.provider, obs.query, obs.fetch_error))
        elif obs.analysis is not None and obs.analysis.error is not None:
            entries.append(ErrorEntry(obs.provider, obs.query, obs.analysis.error))
    return tuple(entries)


def _trend_metric(current: float | None, previous: float | None) -> TrendMetric:
    if current is None or previous is None:
        return TrendMetric(current, previous, None, "n/a")
    delta = current - previous
    if delta > _TREND_EPSILON:
        direction = "up"
    elif delta < -_TREND_EPSILON:
        direction = "down"
    else:
        direction = "flat"
    return TrendMetric(current, previous, delta, direction)


def _provider_trend(current: ProviderStats, previous: ProviderStats | None) -> ProviderTrend:
    prev_sov = previous.share_of_voice_pct if previous else None
    prev_pos = previous.avg_position if previous else None
    return ProviderTrend(
        provider=current.provider,
        share_of_voice=_trend_metric(current.share_of_voice_pct, prev_sov),
        avg_position=_trend_metric(current.avg_position, prev_pos),
    )


def _recommendations(
    overall: ProviderStats,
    top_competitors: tuple[CompetitorStat, ...],
    absent_queries: tuple[str, ...],
    mentioned_observations: list[Observation],
) -> tuple[str, ...]:
    candidates: list[str] = []

    if overall.share_of_voice_pct is not None:
        if overall.share_of_voice_pct < 30:
            candidates.append(
                f"Доля запросов с упоминанием E100 низкая ({overall.share_of_voice_pct:.0f}%) — "
                "стоит усилить присутствие бренда в контенте по запросам, где он не появляется."
            )
        elif overall.share_of_voice_pct > 70:
            candidates.append(
                f"E100 упоминается в большинстве ответов ({overall.share_of_voice_pct:.0f}%) — "
                "следующий шаг — бороться за более высокую позицию, а не за сам факт упоминания."
            )

    if top_competitors and top_competitors[0].frequency > overall.mentioned_count:
        leader = top_competitors[0]
        candidates.append(
            f"Конкурент {leader.name} упоминается чаще бренда ({leader.frequency} против "
            f"{overall.mentioned_count} упоминаний E100) — стоит изучить, какие запросы он закрывает лучше."
        )

    if mentioned_observations:
        with_link = sum(1 for o in mentioned_observations if o.analysis.has_source_link)
        link_rate = with_link / len(mentioned_observations) * 100.0
        if link_rate < 20:
            candidates.append(
                f"Только {link_rate:.0f}% ответов с упоминанием E100 ссылаются на e100.eu как источник — "
                "стоит инвестировать в цитируемый контент (сравнения, гайды), чтобы чаще попадать в источники ассистентов."
            )

    if absent_queries:
        candidates.append(
            f"{len(absent_queries)} из проверенных запросов не содержат упоминания E100 ни у одного провайдера "
            "— см. список ниже, это приоритетные темы для контентной работы."
        )

    return tuple(candidates[:3])


def build_aggregate(
    *,
    brand_name: str,
    current_observations: list[Observation],
    previous_observations: list[Observation] | None = None,
) -> Aggregate:
    current_by_provider = _group_by_provider(current_observations)
    per_provider = tuple(
        _stats_for(provider, obs_list) for provider, obs_list in sorted(current_by_provider.items())
    )
    overall = _stats_for("overall", current_observations)

    top_competitors = _top_competitors(current_observations, brand_name)
    absent_queries = _absent_queries(current_observations)
    errors = _errors(current_observations)
    mentioned_observations = [
        o for o in current_observations if o.fetch_ok and o.analysis is not None and o.analysis.mentioned
    ]
    recommendations = _recommendations(overall, top_competitors, absent_queries, mentioned_observations)

    trend_overall = None
    trend_per_provider: tuple[ProviderTrend, ...] = ()
    if previous_observations is not None:
        previous_by_provider = _group_by_provider(previous_observations)
        previous_stats_by_provider = {
            provider: _stats_for(provider, obs_list) for provider, obs_list in previous_by_provider.items()
        }
        previous_overall = _stats_for("overall", previous_observations)
        trend_overall = _provider_trend(overall, previous_overall)
        trend_per_provider = tuple(
            _provider_trend(stats, previous_stats_by_provider.get(stats.provider))
            for stats in per_provider
        )

    return Aggregate(
        brand_name=brand_name,
        per_provider=per_provider,
        overall=overall,
        top_competitors=top_competitors,
        absent_queries=absent_queries,
        errors=errors,
        trend_overall=trend_overall,
        trend_per_provider=trend_per_provider,
        recommendations=recommendations,
    )
