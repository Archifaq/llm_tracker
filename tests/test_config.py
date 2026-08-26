import tempfile
import unittest
from pathlib import Path

from e100_visibility.config import ConfigError, load_config

MINIMAL_CONFIG = """
queries = ["query one", "query two"]

[market]
language = "pl"
country = "PL"

[brand]
name = "E100"
domain = "e100.eu"
aliases = ["E100", "e100.eu"]

[[providers]]
name = "openai"
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"
"""


def _write(tmp_dir: str, content: str) -> Path:
    path = Path(tmp_dir) / "config.toml"
    path.write_text(content)
    return path


class LoadConfigTests(unittest.TestCase):
    def test_loads_minimal_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, MINIMAL_CONFIG)
            config = load_config(path)

        self.assertEqual(config.market.language, "pl")
        self.assertEqual(config.brand.domain, "e100.eu")
        self.assertEqual(len(config.providers), 1)
        self.assertEqual(config.providers[0].kind, "openai")  # defaults to name
        self.assertEqual(config.queries, ("query one", "query two"))
        self.assertEqual(config.analysis.method, "heuristic")  # default

    def test_missing_file_raises_config_error(self):
        with self.assertRaises(ConfigError):
            load_config("/nonexistent/config.toml")

    def test_empty_queries_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, MINIMAL_CONFIG.replace('queries = ["query one", "query two"]', "queries = []"))
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_llm_analysis_requires_provider(self):
        broken = MINIMAL_CONFIG + '\n[analysis]\nmethod = "llm"\n'
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, broken)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_disabled_provider_excluded_from_enabled_providers(self):
        with_disabled = MINIMAL_CONFIG + """
[[providers]]
name = "gemini"
model = "gemini-2.5-flash"
api_key_env = "GEMINI_API_KEY"
enabled = false
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, with_disabled)
            config = load_config(path)

        self.assertEqual(len(config.providers), 2)
        self.assertEqual([p.name for p in config.enabled_providers()], ["openai"])


if __name__ == "__main__":
    unittest.main()
