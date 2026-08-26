import tempfile
import unittest
from pathlib import Path

from e100_visibility.analysis.schema import AnalysisResult
from e100_visibility.models import Observation
from e100_visibility.storage.store import RunStore


def _analysis(**overrides) -> AnalysisResult:
    defaults = dict(
        mentioned=True,
        position=1,
        total_brands=2,
        brands_in_order=("E100", "DKV"),
        context="Wymieniona jako najlepsza.",
        context_category="best",
        sentiment="positive",
        has_source_link=True,
        competitors_above=(),
        method="heuristic",
    )
    defaults.update(overrides)
    return AnalysisResult(**defaults)


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.tmp_dir.name) / "history.sqlite3")

    def tearDown(self):
        self.store.close()
        self.tmp_dir.cleanup()

    def test_round_trips_a_successful_observation(self):
        run_id = self.store.start_run(started_at="2026-08-26T10:00:00+00:00", language="pl", country="PL")
        observation = Observation(
            run_id=run_id,
            timestamp="2026-08-26T10:00:01+00:00",
            provider="openai",
            model="gpt-4o",
            query="Jakie są najlepsze karty paliwowe?",
            language="pl",
            country="PL",
            answer_text="E100 jest najlepsza. DKV jest drugą opcją.",
            citations=("https://e100.eu",),
            raw={"choices": []},
            fetch_error=None,
            analysis=_analysis(),
        )
        self.store.save_observation(observation)

        rows = self.store.observations_for_run(run_id)
        self.assertEqual(len(rows), 1)
        stored = rows[0]
        self.assertEqual(stored.provider, "openai")
        self.assertEqual(stored.citations, ("https://e100.eu",))
        self.assertEqual(stored.analysis.position, 1)
        self.assertEqual(stored.analysis.brands_in_order, ("E100", "DKV"))
        self.assertTrue(stored.analysis.has_source_link)

    def test_round_trips_a_fetch_error_observation(self):
        run_id = self.store.start_run(started_at="2026-08-26T10:00:00+00:00", language="pl", country="PL")
        observation = Observation(
            run_id=run_id,
            timestamp="2026-08-26T10:00:01+00:00",
            provider="perplexity",
            model="sonar",
            query="q",
            language="pl",
            country="PL",
            answer_text=None,
            fetch_error="HTTP 429: rate limited",
            analysis=None,
        )
        self.store.save_observation(observation)

        stored = self.store.observations_for_run(run_id)[0]
        self.assertFalse(stored.fetch_ok)
        self.assertEqual(stored.fetch_error, "HTTP 429: rate limited")
        self.assertIsNone(stored.analysis)

    def test_previous_run_id_finds_the_most_recent_earlier_run_in_same_market(self):
        run1 = self.store.start_run(started_at="2026-08-01T00:00:00+00:00", language="pl", country="PL")
        run2 = self.store.start_run(started_at="2026-08-15T00:00:00+00:00", language="pl", country="PL")
        run3 = self.store.start_run(started_at="2026-08-20T00:00:00+00:00", language="de", country="DE")

        self.assertIsNone(self.store.previous_run_id(language="pl", country="PL", before_run_id=run1))
        self.assertEqual(self.store.previous_run_id(language="pl", country="PL", before_run_id=run2), run1)
        # Different market history must not leak in.
        self.assertIsNone(self.store.previous_run_id(language="de", country="DE", before_run_id=run3))

    def test_observations_are_isolated_per_run(self):
        run1 = self.store.start_run(started_at="t1", language="pl", country="PL")
        run2 = self.store.start_run(started_at="t2", language="pl", country="PL")
        self.store.save_observation(
            Observation(run_id=run1, timestamp="t1", provider="openai", model="m", query="q1",
                        language="pl", country="PL", answer_text="a", analysis=_analysis())
        )
        self.store.save_observation(
            Observation(run_id=run2, timestamp="t2", provider="openai", model="m", query="q2",
                        language="pl", country="PL", answer_text="b", analysis=_analysis())
        )

        self.assertEqual(len(self.store.observations_for_run(run1)), 1)
        self.assertEqual(len(self.store.observations_for_run(run2)), 1)
        self.assertEqual(self.store.observations_for_run(run1)[0].query, "q1")


if __name__ == "__main__":
    unittest.main()
