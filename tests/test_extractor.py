import unittest

from e100_visibility.analysis.extractor import extract_heuristic
from e100_visibility.analysis.schema import (
    CONTEXT_BEST,
    CONTEXT_CAVEAT,
    CONTEXT_NOT_MENTIONED,
    CONTEXT_ONE_OF_SEVERAL,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
)
from e100_visibility.config import BrandConfig, CompetitorConfig

BRAND = BrandConfig(name="E100", domain="e100.eu", aliases=("E100", "e100.eu", "Е100", "E 100", "E-100"))
COMPETITORS = (
    CompetitorConfig(name="DKV", aliases=("DKV",)),
    CompetitorConfig(name="Shell", aliases=("Shell", "Karta Shell")),
    CompetitorConfig(name="UTA", aliases=("UTA",)),
)


def run(answer_text, citations=()):
    return extract_heuristic(answer_text=answer_text, citations=citations, brand=BRAND, competitors=COMPETITORS)


class ExtractHeuristicTests(unittest.TestCase):
    def test_brand_not_mentioned_at_all(self):
        result = run(
            "Najlepsze karty paliwowe dla firm to DKV oraz Shell. Obie oferują "
            "szeroką sieć stacji w Europie i aplikację mobilną."
        )
        self.assertFalse(result.mentioned)
        self.assertIsNone(result.position)
        self.assertEqual(result.context_category, CONTEXT_NOT_MENTIONED)
        self.assertEqual(result.brands_in_order, ("DKV", "Shell"))

    def test_brand_mentioned_only_as_bare_domain(self):
        result = run(
            "Wśród dostawców kart flotowych w Polsce można wymienić DKV oraz e100.eu, "
            "które różnią się zasięgiem sieci akceptacji."
        )
        self.assertTrue(result.mentioned)
        self.assertEqual(result.position, 2)
        self.assertEqual(result.competitors_above, ("DKV",))

    def test_empty_answer_does_not_crash(self):
        result = run("")
        self.assertFalse(result.mentioned)
        self.assertEqual(result.total_brands, 0)
        self.assertEqual(result.brands_in_order, ())
        self.assertEqual(result.context_category, CONTEXT_NOT_MENTIONED)

    def test_truncated_answer_below_min_length(self):
        result = run("E10")
        self.assertFalse(result.mentioned)
        self.assertEqual(result.context_category, CONTEXT_NOT_MENTIONED)

    def test_brand_named_first_and_praised_is_best(self):
        result = run(
            "1. E100 - najlepsza karta paliwowa dla małych firm transportowych.\n"
            "2. DKV - dobra alternatywa z szeroką siecią stacji.\n"
            "3. Shell - również warta rozważenia."
        )
        self.assertTrue(result.mentioned)
        self.assertEqual(result.position, 1)
        self.assertEqual(result.total_brands, 3)
        self.assertEqual(result.context_category, CONTEXT_BEST)
        self.assertEqual(result.sentiment, SENTIMENT_POSITIVE)
        self.assertEqual(result.competitors_above, ())

    def test_explicit_numbered_list_overrides_text_order(self):
        # E100 appears earlier in the prose, but the numbered ranking puts DKV first.
        text = (
            "Rozważając E100 i inne opcje, oto ranking:\n"
            "1. DKV - lider rynku kart paliwowych.\n"
            "2. E100 - dobra opcja dla mniejszych flot.\n"
        )
        result = run(text)
        self.assertEqual(result.position, 2)
        self.assertEqual(result.competitors_above, ("DKV",))

    def test_brand_mentioned_with_caveat_is_negative(self):
        result = run(
            "E100 to jedna z opcji, jednak niestety ma ograniczoną sieć akceptacji w porównaniu do Shell."
        )
        self.assertTrue(result.mentioned)
        self.assertEqual(result.context_category, CONTEXT_CAVEAT)
        self.assertEqual(result.sentiment, SENTIMENT_NEGATIVE)

    def test_brand_one_of_several_without_strong_sentiment(self):
        result = run("Do popularnych kart paliwowych dla firm należą DKV, Shell, UTA oraz E100.")
        self.assertTrue(result.mentioned)
        self.assertEqual(result.context_category, CONTEXT_ONE_OF_SEVERAL)
        self.assertEqual(result.sentiment, SENTIMENT_NEUTRAL)
        self.assertEqual(result.total_brands, 4)

    def test_source_link_detected_from_citations(self):
        result = run("Więcej informacji o kartach paliwowych.", citations=("https://e100.eu/oferta",))
        self.assertTrue(result.has_source_link)

    def test_source_link_detected_from_answer_text_url(self):
        result = run("Sprawdź szczegóły na https://e100.eu/karty-paliwowe.")
        self.assertTrue(result.has_source_link)

    def test_no_source_link_when_absent(self):
        result = run("E100 to dobra karta paliwowa dla firm.")
        self.assertFalse(result.has_source_link)

    def test_alias_does_not_false_match_longer_word(self):
        # "E1000" must not be picked up as a mention of "E100".
        result = run("Model urządzenia E1000 nie ma nic wspólnego z kartami paliwowymi.")
        self.assertFalse(result.mentioned)

    def test_cyrillic_alias_variant_recognised(self):
        result = run("Карта Е100 подходит для малого бизнеса.")
        self.assertTrue(result.mentioned)
        self.assertEqual(result.position, 1)


if __name__ == "__main__":
    unittest.main()
