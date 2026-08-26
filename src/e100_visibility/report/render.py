"""Renders the final human-readable text report: one block per query x
provider pair in the exact format from the brief, followed by an aggregate
summary section.
"""

from __future__ import annotations

from ..config import BrandConfig, MarketConfig
from ..models import Observation
from .aggregate import Aggregate, ProviderTrend

_SENTIMENT_RU = {
    "positive": "позитивная",
    "neutral": "нейтральная",
    "negative": "негативная",
}

_SOV_DIRECTION_RU = {
    "up": "рост",
    "down": "падение",
    "flat": "без изменений",
    "n/a": "нет истории для сравнения",
}


def _yes_no(value: bool) -> str:
    return "Да" if value else "Нет"


def _present_absent(value: bool) -> str:
    return "есть" if value else "нет"


def _observation_block(observation: Observation) -> str:
    lines = ["---", f"Запрос: {observation.query}", f"Платформа: {observation.provider}"]

    if not observation.fetch_ok:
        lines.append(f"Ошибка: {observation.fetch_error}")
        lines.append("---")
        return "\n".join(lines)

    analysis = observation.analysis
    if analysis is None:
        lines.append("Ошибка: анализ ответа не был выполнен.")
        lines.append("---")
        return "\n".join(lines)

    lines.append(f"Упоминание E100: {_yes_no(analysis.mentioned)}")
    if analysis.mentioned:
        lines.append(f"Позиция: {analysis.position} из {analysis.total_brands}")
    elif analysis.total_brands:
        lines.append(f"Позиция: — из {analysis.total_brands} (E100 не встречается)")
    else:
        lines.append("Позиция: — (в ответе не удалось распознать ни одного бренда)")

    if analysis.error:
        lines.append(f"Контекст: {analysis.context or '(нет данных)'} [примечание: {analysis.error}]")
    else:
        lines.append(f"Контекст: {analysis.context or '(нет данных)'}")

    lines.append(f"Тональность: {_SENTIMENT_RU.get(analysis.sentiment, analysis.sentiment)}")

    competitors_above = ", ".join(analysis.competitors_above) if analysis.competitors_above else "—"
    lines.append(f"Кто упомянут выше E100 (если применимо): {competitors_above}")
    lines.append(f"Ссылка на e100.eu в источниках: {_present_absent(analysis.has_source_link)}")
    lines.append("---")
    return "\n".join(lines)


def _avg_position_direction(trend) -> str:
    if trend.direction == "n/a":
        return "нет истории для сравнения"
    if trend.direction == "flat":
        return "без изменений"
    return "позиция улучшилась" if trend.delta < 0 else "позиция ухудшилась"


def _format_trend_line(label: str, trend: ProviderTrend) -> list[str]:
    sov = trend.share_of_voice
    pos = trend.avg_position
    lines = [f"  {label}:"]
    if sov.direction == "n/a" and pos.direction == "n/a":
        lines.append("    история отсутствует")
        return lines
    if sov.current is not None and sov.previous is not None:
        lines.append(
            f"    Share of Voice: {sov.previous:.0f}% -> {sov.current:.0f}% "
            f"({_SOV_DIRECTION_RU[sov.direction]}, {sov.delta:+.1f} п.п.)"
        )
    if pos.current is not None and pos.previous is not None:
        lines.append(
            f"    Средняя позиция: {pos.previous:.1f} -> {pos.current:.1f} "
            f"({_avg_position_direction(pos)}, {pos.delta:+.1f})"
        )
    return lines


def _format_sov(stats) -> str:
    if stats.share_of_voice_pct is None:
        return f"  {stats.provider}: нет успешных запросов"
    return (
        f"  {stats.provider}: {stats.share_of_voice_pct:.1f}% "
        f"(упомянут в {stats.mentioned_count} из {stats.successful_queries} успешных запросов)"
    )


def _format_avg_position(stats) -> str:
    if stats.avg_position is None:
        return f"  {stats.provider}: нет упоминаний для расчёта"
    return f"  {stats.provider}: {stats.avg_position:.1f}"


def render_summary(aggregate: Aggregate) -> str:
    lines = ["=" * 70, "ИТОГИ", "=" * 70, ""]

    lines.append("Доля упоминаний E100 (Share of Voice):")
    for stats in aggregate.per_provider:
        lines.append(_format_sov(stats))
    lines.append(_format_sov(aggregate.overall).replace(aggregate.overall.provider, "В среднем по всем провайдерам", 1))
    lines.append("")

    lines.append("Средняя позиция E100 (только среди ответов с упоминанием):")
    for stats in aggregate.per_provider:
        lines.append(_format_avg_position(stats))
    lines.append(_format_avg_position(aggregate.overall).replace(aggregate.overall.provider, "В среднем", 1))
    lines.append("")

    lines.append("Топ конкурентов по частоте упоминаний:")
    if aggregate.top_competitors:
        for rank, competitor in enumerate(aggregate.top_competitors, start=1):
            pos = f"{competitor.avg_position:.1f}" if competitor.avg_position is not None else "н/д"
            lines.append(f"  {rank}. {competitor.name} — {competitor.frequency} упоминаний, средняя позиция {pos}")
    else:
        lines.append("  Конкуренты не распознаны ни в одном ответе.")
    lines.append("")

    lines.append(f"Запросы, где E100 отсутствует полностью ({len(aggregate.absent_queries)}):")
    if aggregate.absent_queries:
        for query in aggregate.absent_queries:
            lines.append(f"  - {query}")
    else:
        lines.append("  (нет — E100 упомянут хотя бы одним провайдером в каждом запросе)")
    lines.append("")

    lines.append("Изменение относительно предыдущего прогона:")
    if aggregate.trend_overall is None:
        lines.append("  История отсутствует — это первый прогон для данного рынка.")
    else:
        lines.extend(_format_trend_line("В среднем по всем провайдерам", aggregate.trend_overall))
        for trend in aggregate.trend_per_provider:
            lines.extend(_format_trend_line(trend.provider, trend))
    lines.append("")

    lines.append("Наблюдения и рекомендации:")
    if aggregate.recommendations:
        for i, rec in enumerate(aggregate.recommendations, start=1):
            lines.append(f"  {i}. {rec}")
    else:
        lines.append("  Недостаточно данных для рекомендаций.")
    lines.append("")

    if aggregate.errors:
        lines.append(f"Ошибки провайдеров в этом прогоне ({len(aggregate.errors)}):")
        for error in aggregate.errors:
            lines.append(f"  - [{error.provider}] {error.query}: {error.message}")
        lines.append("")

    return "\n".join(lines)


def render_report(
    *,
    brand: BrandConfig,
    market: MarketConfig,
    generated_at: str,
    observations: list[Observation],
    aggregate: Aggregate,
) -> str:
    header = [
        f"Отчёт о видимости бренда {brand.name} в ответах LLM-ассистентов",
        f"Рынок: {market.label or market.country} ({market.language}/{market.country})",
        f"Сформирован: {generated_at}",
        f"Всего наблюдений: {len(observations)}",
        "",
    ]

    blocks = [_observation_block(obs) for obs in observations]

    return "\n".join(header) + "\n" + "\n".join(blocks) + "\n\n" + render_summary(aggregate)
