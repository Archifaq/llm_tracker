import unittest

from e100_visibility.analysis.analyzer import analyze, analyze_with_llm
from e100_visibility.config import (
    AnalysisConfig,
    AppConfig,
    BrandConfig,
    MarketConfig,
    ReportConfig,
    StorageConfig,
)
from e100_visibility.providers.base import ProviderError, ProviderResponse

BRAND = BrandConfig(name="E100", domain="e100.eu", aliases=("E100", "e100.eu"))


class _CannedProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply_text: str):
        self.reply_text = reply_text

    def ask(self, query, *, language, country):
        return ProviderResponse(provider=self.name, model=self.model, query=query, answer_text=self.reply_text)


class _FailingProvider:
    name = "fake"
    model = "fake-model"

    def ask(self, query, *, language, country):
        raise ProviderError(self.name, "simulated timeout", retryable=True)


class AnalyzeWithLlmTests(unittest.TestCase):
    def test_parses_valid_json_reply(self):
        reply = """Oto wynik:
{
  "mentioned": true,
  "position": 2,
  "total_brands": 3,
  "brands_in_order": ["DKV", "E100", "Shell"],
  "context": "Wymieniona jako jedna z kilku opcji.",
  "context_category": "one_of_several",
  "sentiment": "neutral",
  "has_source_link": false,
  "competitors_above": ["DKV"]
}"""
        provider = _CannedProvider(reply)
        result = analyze_with_llm(
            provider, brand=BRAND, query="q", answer_text="a", platform="test", language="pl", country="PL"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.position, 2)
        self.assertEqual(result.brands_in_order, ("DKV", "E100", "Shell"))
        self.assertEqual(result.method, "llm")

    def test_malformed_json_reply_is_reported_as_error(self):
        provider = _CannedProvider("this is not json at all")
        result = analyze_with_llm(
            provider, brand=BRAND, query="q", answer_text="a", platform="test", language="pl", country="PL"
        )
        self.assertFalse(result.ok)
        self.assertIn("did not return JSON", result.error)

    def test_provider_error_is_reported_as_error(self):
        result = analyze_with_llm(
            _FailingProvider(), brand=BRAND, query="q", answer_text="a", platform="test", language="pl", country="PL"
        )
        self.assertFalse(result.ok)
        self.assertIn("simulated timeout", result.error)

    def test_invalid_enum_values_are_normalised(self):
        reply = '{"mentioned": true, "position": 1, "total_brands": 1, "brands_in_order": ["E100"], ' \
                '"context": "x", "context_category": "bogus", "sentiment": "ecstatic", ' \
                '"has_source_link": false, "competitors_above": []}'
        result = analyze_with_llm(
            _CannedProvider(reply), brand=BRAND, query="q", answer_text="a", platform="test", language="pl", country="PL"
        )
        self.assertEqual(result.context_category, "not_mentioned")
        self.assertEqual(result.sentiment, "neutral")


def _config(method: str, provider: str | None = None) -> AppConfig:
    return AppConfig(
        market=MarketConfig(language="pl", country="PL"),
        brand=BRAND,
        competitors=(),
        providers=(),
        analysis=AnalysisConfig(method=method, provider=provider),
        storage=StorageConfig(),
        report=ReportConfig(),
        queries=("q1",),
    )


class AnalyzeDispatchTests(unittest.TestCase):
    def test_heuristic_method_never_calls_a_provider(self):
        config = _config("heuristic")
        result = analyze(
            config=config,
            analyzer_provider=None,
            query="q",
            answer_text="E100 to dobra karta paliwowa.",
            citations=(),
            platform="test",
        )
        self.assertEqual(result.method, "heuristic")
        self.assertTrue(result.mentioned)

    def test_llm_method_falls_back_to_heuristic_on_failure(self):
        config = _config("llm", provider="fake")
        result = analyze(
            config=config,
            analyzer_provider=_FailingProvider(),
            query="q",
            answer_text="E100 to dobra karta paliwowa.",
            citations=(),
            platform="test",
        )
        self.assertEqual(result.method, "heuristic")
        self.assertTrue(result.mentioned)
        self.assertIsNotNone(result.error)
        self.assertIn("llm analyzer failed", result.error)


if __name__ == "__main__":
    unittest.main()
