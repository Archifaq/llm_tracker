import json
import unittest

from e100_visibility.analysis.schema import AnalysisResult
from e100_visibility.models import Observation
from e100_visibility.report.aggregate import build_aggregate
from e100_visibility.report.serialize import aggregate_to_dict, observation_to_dict, run_to_dict


def _mentioned_observation():
    analysis = AnalysisResult(
        mentioned=True,
        position=1,
        total_brands=2,
        brands_in_order=("E100", "DKV"),
        context="Bренд рекомендован как лучший.",
        context_category="best",
        sentiment="positive",
        has_source_link=True,
        competitors_above=(),
        method="heuristic",
    )
    return Observation(
        run_id=1, timestamp="t1", provider="openai", model="gpt-5-search-api", query="q1",
        language="pl", country="PL", answer_text="raw model answer, must never be exported",
        citations=("https://e100.eu",), raw={"secret": "raw api payload, must never be exported"},
        analysis=analysis,
    )


def _fetch_error_observation():
    return Observation(
        run_id=1, timestamp="t1", provider="gemini", model="gemini-2.5-flash", query="q2",
        language="pl", country="PL", answer_text=None, fetch_error="HTTP 429: rate limited", analysis=None,
    )


class ObservationToDictTests(unittest.TestCase):
    def test_never_includes_raw_answer_or_raw_payload(self):
        d = observation_to_dict(_mentioned_observation())
        serialized = json.dumps(d)
        self.assertNotIn("must never be exported", serialized)
        self.assertNotIn("answer_text", d)
        self.assertNotIn("raw", d)
        self.assertNotIn("citations", d)  # citation URLs also excluded, not requested by the brief

    def test_includes_the_fields_the_text_report_shows(self):
        d = observation_to_dict(_mentioned_observation())
        self.assertEqual(d["query"], "q1")
        self.assertEqual(d["provider"], "openai")
        self.assertTrue(d["mentioned"])
        self.assertEqual(d["position"], 1)
        self.assertEqual(d["total_brands"], 2)
        self.assertTrue(d["has_source_link"])
        self.assertEqual(d["competitors_above"], [])

    def test_fetch_error_observation_has_null_analysis_fields(self):
        d = observation_to_dict(_fetch_error_observation())
        self.assertEqual(d["fetch_error"], "HTTP 429: rate limited")
        self.assertIsNone(d["mentioned"])
        self.assertIsNone(d["position"])
        self.assertEqual(d["competitors_above"], [])

    def test_round_trips_through_json(self):
        d = observation_to_dict(_mentioned_observation())
        self.assertEqual(json.loads(json.dumps(d)), d)


class AggregateToDictTests(unittest.TestCase):
    def test_round_trips_through_json_with_and_without_trend(self):
        current = [_mentioned_observation(), _fetch_error_observation()]
        aggregate_no_trend = build_aggregate(brand_name="E100", current_observations=current)
        d = aggregate_to_dict(aggregate_no_trend)
        self.assertIsNone(d["trend_overall"])
        self.assertEqual(json.loads(json.dumps(d)), d)

        previous = [_mentioned_observation()]
        aggregate_with_trend = build_aggregate(
            brand_name="E100", current_observations=current, previous_observations=previous
        )
        d2 = aggregate_to_dict(aggregate_with_trend)
        self.assertIsNotNone(d2["trend_overall"])
        self.assertIn("share_of_voice", d2["trend_overall"])
        self.assertIn("avg_position", d2["trend_overall"])
        self.assertEqual(json.loads(json.dumps(d2)), d2)

    def test_errors_and_absent_queries_are_lists_not_tuples_after_round_trip(self):
        current = [_mentioned_observation(), _fetch_error_observation()]
        aggregate = build_aggregate(brand_name="E100", current_observations=current)
        d = aggregate_to_dict(aggregate)
        reloaded = json.loads(json.dumps(d))
        self.assertIsInstance(reloaded["errors"], list)
        self.assertIsInstance(reloaded["absent_queries"], list)
        self.assertIsInstance(reloaded["top_competitors"], list)


class RunToDictTests(unittest.TestCase):
    def test_full_run_round_trips_and_has_expected_shape(self):
        observations = [_mentioned_observation(), _fetch_error_observation()]
        aggregate = build_aggregate(brand_name="E100", current_observations=observations)
        run = run_to_dict(
            run_id=7, timestamp="2026-08-27T06:00:00+00:00", language="pl", country="PL",
            label="Poland", aggregate=aggregate, observations=observations,
        )

        reloaded = json.loads(json.dumps(run))
        self.assertEqual(reloaded, run)
        self.assertEqual(reloaded["run_id"], 7)
        self.assertEqual(reloaded["market"], {"language": "pl", "country": "PL", "label": "Poland"})
        self.assertEqual(len(reloaded["observations"]), 2)
        self.assertIn("aggregate", reloaded)


if __name__ == "__main__":
    unittest.main()
