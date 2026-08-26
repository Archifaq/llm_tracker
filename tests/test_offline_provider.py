import unittest

from e100_visibility.providers.offline_provider import _ANSWER_TEMPLATES, OfflineDemoProvider


class OfflineDemoProviderTests(unittest.TestCase):
    def test_same_provider_and_query_is_deterministic(self):
        provider = OfflineDemoProvider(name="demo-a", model="offline-demo")
        first = provider.ask("Jakie są najlepsze karty paliwowe?", language="pl", country="PL")
        second = provider.ask("Jakie są najlepsze karty paliwowe?", language="pl", country="PL")
        self.assertEqual(first.answer_text, second.answer_text)
        self.assertEqual(first.citations, second.citations)

    def test_answer_is_always_one_of_the_known_templates(self):
        provider = OfflineDemoProvider(name="demo-a", model="offline-demo")
        known_texts = {text for text, _ in _ANSWER_TEMPLATES}
        for query in ["q1", "q2", "q3", "q4", "q5"]:
            response = provider.ask(query, language="pl", country="PL")
            self.assertIn(response.answer_text, known_texts)

    def test_different_provider_names_can_diverge_on_the_same_query(self):
        query = "Jakie są najlepsze karty paliwowe dla firm w Polsce?"
        a = OfflineDemoProvider(name="demo-assistant-a", model="offline-demo").ask(
            query, language="pl", country="PL"
        )
        b = OfflineDemoProvider(name="demo-assistant-b", model="offline-demo").ask(
            query, language="pl", country="PL"
        )
        # Not asserting they always differ (a hash collision is legitimate) --
        # just that the provider name is actually part of the selection, by
        # checking the real demo pair used in config.demo.toml diverges.
        self.assertNotEqual(a.answer_text, b.answer_text)

    def test_never_makes_a_network_call(self):
        # OfflineDemoProvider has no api_key requirement and no HTTP import
        # in its call path -- this is a smoke check that construction and
        # ask() succeed with a bogus/absent api_key_env.
        provider = OfflineDemoProvider(name="demo-a", model="offline-demo", api_key_env="DOES_NOT_EXIST")
        response = provider.ask("any query", language="pl", country="PL")
        self.assertTrue(response.answer_text)


if __name__ == "__main__":
    unittest.main()
