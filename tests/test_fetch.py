import unittest
from unittest.mock import patch

from e100_visibility.config import AppConfig, BrandConfig, MarketConfig, ProviderConfig, AnalysisConfig, StorageConfig, ReportConfig
from e100_visibility.fetch import fetch_all
from e100_visibility.providers.base import ProviderError, ProviderResponse
from e100_visibility.providers.registry import register_provider


class _AlwaysFailsProvider:
    def __init__(self, *, name, model, api_key_env, timeout_seconds=60.0):
        self.name = name
        self.model = model

    def ask(self, query, *, language, country):
        raise ProviderError(self.name, "simulated outage")


class _AlwaysSucceedsProvider:
    def __init__(self, *, name, model, api_key_env, timeout_seconds=60.0):
        self.name = name
        self.model = model

    def ask(self, query, *, language, country):
        return ProviderResponse(provider=self.name, model=self.model, query=query, answer_text=f"answer to: {query}")


def _config(providers):
    return AppConfig(
        market=MarketConfig(language="pl", country="PL"),
        brand=BrandConfig(name="E100", domain="e100.eu", aliases=("E100",)),
        competitors=(),
        providers=providers,
        analysis=AnalysisConfig(),
        storage=StorageConfig(),
        report=ReportConfig(),
        queries=("q1", "q2"),
    )


class FetchAllTests(unittest.TestCase):
    def setUp(self):
        register_provider("test-fails", _AlwaysFailsProvider)
        register_provider("test-succeeds", _AlwaysSucceedsProvider)

    @patch("e100_visibility.fetch.time.sleep")
    def test_one_failing_provider_does_not_block_others(self, mock_sleep):
        config = _config(
            (
                ProviderConfig(name="broken", kind="test-fails", model="m", api_key_env="X"),
                ProviderConfig(name="healthy", kind="test-succeeds", model="m", api_key_env="X"),
            )
        )

        results = fetch_all(config, log=lambda _msg: None)

        by_provider = {}
        for result in results:
            by_provider.setdefault(result.provider, []).append(result)

        self.assertTrue(all(not r.ok for r in by_provider["broken"]))
        self.assertTrue(all(r.ok for r in by_provider["healthy"]))
        self.assertEqual(len(results), 4)  # 2 providers x 2 queries

        # one 4s pause after every query, success or failure, real time never elapses here
        self.assertEqual(mock_sleep.call_count, 4)
        mock_sleep.assert_called_with(4)

    @patch("e100_visibility.fetch.time.sleep")
    def test_unknown_provider_kind_recorded_as_error_not_raised(self, mock_sleep):
        config = _config((ProviderConfig(name="ghost", kind="does-not-exist", model="m", api_key_env="X"),))

        results = fetch_all(config, log=lambda _msg: None)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(not r.ok for r in results))
        # the provider never builds, so the per-query loop (and its sleep) never runs
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
