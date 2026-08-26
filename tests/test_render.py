import unittest

from e100_visibility.config import BrandConfig, MarketConfig
from e100_visibility.report.aggregate import build_aggregate
from e100_visibility.report.render import render_report
from tests.test_aggregate import _sample_observations

BRAND = BrandConfig(name="E100", domain="e100.eu", aliases=("E100", "e100.eu"))
MARKET = MarketConfig(language="pl", country="PL", label="Poland")


class RenderReportTests(unittest.TestCase):
    def test_report_contains_one_block_per_observation_and_a_summary(self):
        observations = _sample_observations()
        aggregate = build_aggregate(brand_name=BRAND.name, current_observations=observations)

        report = render_report(
            brand=BRAND, market=MARKET, generated_at="2026-08-26T12:00:00+00:00",
            observations=observations, aggregate=aggregate,
        )

        self.assertEqual(report.count("Запрос:"), len(observations))
        self.assertIn("Ошибка: HTTP 429: rate limited", report)
        self.assertIn("ИТОГИ", report)
        self.assertIn("Доля упоминаний E100", report)
        self.assertIn("Топ конкурентов", report)
        self.assertIn("Запросы, где E100 отсутствует полностью", report)
        self.assertIn("q3", report)  # the absent query is listed
        self.assertIn("Наблюдения и рекомендации", report)

    def test_mentioned_observation_shows_position_and_sentiment_in_russian(self):
        observations = _sample_observations()
        aggregate = build_aggregate(brand_name=BRAND.name, current_observations=observations)
        report = render_report(
            brand=BRAND, market=MARKET, generated_at="t", observations=observations, aggregate=aggregate,
        )
        self.assertIn("Позиция: 1 из 3", report)
        self.assertIn("Тональность: нейтральная", report)


if __name__ == "__main__":
    unittest.main()
