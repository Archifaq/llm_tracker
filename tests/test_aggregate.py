import unittest

from e100_visibility.analysis.schema import AnalysisResult
from e100_visibility.models import Observation
from e100_visibility.report.aggregate import build_aggregate

BRAND = "E100"


def _obs(provider, query, *, mentioned=None, position=None, total=None, order=(), fetch_error=None, has_link=False):
    if fetch_error is not None:
        return Observation(
            run_id=1, timestamp="t", provider=provider, model="m", query=query,
            language="pl", country="PL", answer_text=None, fetch_error=fetch_error, analysis=None,
        )
    analysis = AnalysisResult(
        mentioned=mentioned,
        position=position,
        total_brands=total,
        brands_in_order=order,
        context="ctx",
        context_category="one_of_several" if mentioned else "not_mentioned",
        sentiment="neutral",
        has_source_link=has_link,
        competitors_above=order[: position - 1] if mentioned else order,
    )
    return Observation(
        run_id=1, timestamp="t", provider=provider, model="m", query=query,
        language="pl", country="PL", answer_text="text", analysis=analysis,
    )


def _sample_observations():
    return [
        _obs("openai", "q1", mentioned=True, position=1, total=3, order=("E100", "DKV", "Shell")),
        _obs("openai", "q2", mentioned=False, position=None, total=2, order=("DKV", "Shell")),
        _obs("openai", "q3", fetch_error="HTTP 429: rate limited"),
        _obs("gemini", "q1", mentioned=True, position=2, total=2, order=("DKV", "E100")),
        _obs("gemini", "q2", mentioned=True, position=1, total=1, order=("E100",)),
        _obs("gemini", "q3", mentioned=False, position=None, total=1, order=("Shell",)),
    ]


class BuildAggregateTests(unittest.TestCase):
    def test_overall_share_of_voice_and_avg_position(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())

        self.assertEqual(aggregate.overall.successful_queries, 5)
        self.assertEqual(aggregate.overall.mentioned_count, 3)
        self.assertAlmostEqual(aggregate.overall.share_of_voice_pct, 60.0)
        self.assertAlmostEqual(aggregate.overall.avg_position, (1 + 2 + 1) / 3)

    def test_per_provider_stats(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        by_provider = {s.provider: s for s in aggregate.per_provider}

        self.assertEqual(by_provider["openai"].successful_queries, 2)  # q3 errored out
        self.assertEqual(by_provider["openai"].mentioned_count, 1)
        self.assertEqual(by_provider["gemini"].successful_queries, 3)
        self.assertEqual(by_provider["gemini"].mentioned_count, 2)

    def test_top_competitors_ranked_by_frequency_then_position(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        names = [c.name for c in aggregate.top_competitors]

        self.assertEqual(names[:2], ["DKV", "Shell"])
        dkv = next(c for c in aggregate.top_competitors if c.name == "DKV")
        self.assertEqual(dkv.frequency, 3)
        self.assertAlmostEqual(dkv.avg_position, (2 + 1 + 1) / 3)

    def test_absent_queries_only_when_no_provider_mentions_it(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        # q1: mentioned by both. q2: mentioned by gemini only -> not absent. q3: mentioned by neither -> absent.
        self.assertEqual(aggregate.absent_queries, ("q3",))

    def test_errors_collected_from_fetch_failures(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        self.assertEqual(len(aggregate.errors), 1)
        self.assertEqual(aggregate.errors[0].provider, "openai")
        self.assertEqual(aggregate.errors[0].query, "q3")

    def test_trend_none_without_previous_run(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        self.assertIsNone(aggregate.trend_overall)

    def test_trend_computed_against_previous_run(self):
        previous = [
            _obs("openai", "q1", mentioned=False, position=None, total=1, order=("DKV",)),
            _obs("gemini", "q1", mentioned=True, position=3, total=3, order=("DKV", "Shell", "E100")),
        ]
        aggregate = build_aggregate(
            brand_name=BRAND, current_observations=_sample_observations(), previous_observations=previous
        )
        self.assertIsNotNone(aggregate.trend_overall)
        self.assertEqual(aggregate.trend_overall.share_of_voice.direction, "up")  # 0% -> 60%
        self.assertEqual(aggregate.trend_overall.avg_position.direction, "down")  # 3.0 -> 1.33 (improved)

    def test_recommendations_capped_at_three(self):
        aggregate = build_aggregate(brand_name=BRAND, current_observations=_sample_observations())
        self.assertLessEqual(len(aggregate.recommendations), 3)


if __name__ == "__main__":
    unittest.main()
