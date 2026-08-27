"""Explicit JSON serialization for the web dashboard export.

Written by hand rather than via ``dataclasses.asdict`` for two reasons:
these dataclasses use ``tuple`` fields (not JSON-native) and the brand's
public repo must never leak the raw LLM answer text or raw API payload --
an automatic/generic serializer would happily include whatever fields
exist on ``Observation``, including ``answer_text`` and ``raw``. Listing
fields explicitly here is the enforcement point for that privacy rule.
"""

from __future__ import annotations

from ..models import Observation
from .aggregate import Aggregate, CompetitorStat, ErrorEntry, ProviderStats, ProviderTrend, TrendMetric


def observation_to_dict(observation: Observation) -> dict:
    """Only the derived/extracted fields that already appear in the text
    report -- never ``answer_text`` or ``raw`` (the full LLM answer / raw
    API response), since this feeds a public repo.
    """
    analysis = observation.analysis
    return {
        "query": observation.query,
        "provider": observation.provider,
        "fetch_error": observation.fetch_error,
        "mentioned": analysis.mentioned if analysis else None,
        "position": analysis.position if analysis else None,
        "total_brands": analysis.total_brands if analysis else None,
        "context": analysis.context if analysis else None,
        "context_category": analysis.context_category if analysis else None,
        "sentiment": analysis.sentiment if analysis else None,
        "competitors_above": list(analysis.competitors_above) if analysis else [],
        "has_source_link": analysis.has_source_link if analysis else None,
        "analysis_error": analysis.error if analysis else None,
    }


def _provider_stats_to_dict(stats: ProviderStats) -> dict:
    return {
        "provider": stats.provider,
        "total_queries": stats.total_queries,
        "successful_queries": stats.successful_queries,
        "mentioned_count": stats.mentioned_count,
        "share_of_voice_pct": stats.share_of_voice_pct,
        "avg_position": stats.avg_position,
    }


def _competitor_stat_to_dict(stat: CompetitorStat) -> dict:
    return {"name": stat.name, "frequency": stat.frequency, "avg_position": stat.avg_position}


def _trend_metric_to_dict(metric: TrendMetric) -> dict:
    return {
        "current": metric.current,
        "previous": metric.previous,
        "delta": metric.delta,
        "direction": metric.direction,
    }


def _provider_trend_to_dict(trend: ProviderTrend) -> dict:
    return {
        "provider": trend.provider,
        "share_of_voice": _trend_metric_to_dict(trend.share_of_voice),
        "avg_position": _trend_metric_to_dict(trend.avg_position),
    }


def _error_entry_to_dict(error: ErrorEntry) -> dict:
    return {"provider": error.provider, "query": error.query, "message": error.message}


def aggregate_to_dict(aggregate: Aggregate) -> dict:
    return {
        "brand_name": aggregate.brand_name,
        "per_provider": [_provider_stats_to_dict(s) for s in aggregate.per_provider],
        "overall": _provider_stats_to_dict(aggregate.overall),
        "top_competitors": [_competitor_stat_to_dict(c) for c in aggregate.top_competitors],
        "absent_queries": list(aggregate.absent_queries),
        "errors": [_error_entry_to_dict(e) for e in aggregate.errors],
        "trend_overall": _provider_trend_to_dict(aggregate.trend_overall) if aggregate.trend_overall else None,
        "trend_per_provider": [_provider_trend_to_dict(t) for t in aggregate.trend_per_provider],
        "recommendations": list(aggregate.recommendations),
    }


def run_to_dict(
    *,
    run_id: int,
    timestamp: str,
    language: str,
    country: str,
    label: str,
    aggregate: Aggregate,
    observations: list[Observation],
) -> dict:
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "market": {"language": language, "country": country, "label": label},
        "aggregate": aggregate_to_dict(aggregate),
        "observations": [observation_to_dict(o) for o in observations],
    }
