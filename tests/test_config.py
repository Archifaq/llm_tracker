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

MINIMAL_CONFIG_WITH_QUERIES_FILE = """
queries_file = "queries.txt"

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


class QueriesFileTests(unittest.TestCase):
    def test_loads_queries_from_file_skipping_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "queries.txt").write_text(
                "# comment\n\nQuery A\n   \nQuery B\n# another comment\nQuery C\n"
            )
            path = _write(tmp_dir, MINIMAL_CONFIG_WITH_QUERIES_FILE)
            config = load_config(path)

        self.assertEqual(config.queries, ("Query A", "Query B", "Query C"))

    def test_queries_file_takes_priority_over_inline_queries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "queries.txt").write_text("File query\n")
            content = MINIMAL_CONFIG_WITH_QUERIES_FILE.replace(
                'queries_file = "queries.txt"',
                'queries_file = "queries.txt"\nqueries = ["Inline query"]',
            )
            path = _write(tmp_dir, content)
            config = load_config(path)

        self.assertEqual(config.queries, ("File query",))

    def test_queries_file_path_is_relative_to_the_config_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sub_dir = Path(tmp_dir) / "sub"
            sub_dir.mkdir()
            (sub_dir / "queries.txt").write_text("Nested query\n")
            content = MINIMAL_CONFIG_WITH_QUERIES_FILE.replace(
                'queries_file = "queries.txt"', 'queries_file = "sub/queries.txt"'
            )
            path = _write(tmp_dir, content)
            config = load_config(path)

        self.assertEqual(config.queries, ("Nested query",))

    def test_missing_queries_file_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, MINIMAL_CONFIG_WITH_QUERIES_FILE)  # queries.txt never created
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_empty_queries_file_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "queries.txt").write_text("# only comments\n\n   \n")
            path = _write(tmp_dir, MINIMAL_CONFIG_WITH_QUERIES_FILE)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_neither_queries_nor_queries_file_raises_config_error(self):
        content = MINIMAL_CONFIG.replace('queries = ["query one", "query two"]', "")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write(tmp_dir, content)
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
