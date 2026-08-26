import tempfile
import unittest
from pathlib import Path

from e100_visibility.cli import main
from e100_visibility.providers.base import ProviderResponse
from e100_visibility.providers.registry import register_provider

CONFIG_TEMPLATE = """
queries = ["Jakie są najlepsze karty paliwowe dla firm?", "Ranking kart paliwowych 2026"]

[market]
language = "pl"
country = "PL"
label = "Poland"

[brand]
name = "E100"
domain = "e100.eu"
aliases = ["E100", "e100.eu"]

[[competitors]]
name = "DKV"
aliases = ["DKV"]

[[providers]]
name = "fake"
kind = "test-cli-fake"
model = "fake-model"
api_key_env = "FAKE_API_KEY"

[storage]
path = "{storage_path}"

[report]
output_dir = "{output_dir}"
"""


class _FakeProvider:
    def __init__(self, *, name, model, api_key_env, timeout_seconds=60.0):
        self.name = name
        self.model = model

    def ask(self, query, *, language, country):
        return ProviderResponse(
            provider=self.name,
            model=self.model,
            query=query,
            answer_text="E100 to najlepsza karta paliwowa dla firm. DKV jest drugą opcją.",
        )


class CliRunTests(unittest.TestCase):
    def setUp(self):
        register_provider("test-cli-fake", _FakeProvider)
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.config_path = self.tmp_path / "config.toml"
        self.storage_path = self.tmp_path / "history.sqlite3"
        self.output_dir = self.tmp_path / "output"
        self.config_path.write_text(
            CONFIG_TEMPLATE.format(storage_path=self.storage_path, output_dir=self.output_dir)
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_run_produces_report_file_and_history(self):
        exit_code = main(["run", "--config", str(self.config_path)])
        self.assertEqual(exit_code, 0)

        self.assertTrue(self.storage_path.exists())
        report_files = list(self.output_dir.glob("report_run*.txt"))
        self.assertEqual(len(report_files), 1)

        report_text = report_files[0].read_text()
        self.assertIn("Упоминание E100: Да", report_text)
        self.assertIn("Позиция: 1 из 2", report_text)
        self.assertIn("История отсутствует", report_text)

    def test_second_run_shows_trend_against_first(self):
        main(["run", "--config", str(self.config_path)])
        exit_code = main(["run", "--config", str(self.config_path)])
        self.assertEqual(exit_code, 0)

        report_files = sorted(self.output_dir.glob("report_run*.txt"))
        self.assertEqual(len(report_files), 2)
        second_report = report_files[-1].read_text()
        self.assertNotIn("История отсутствует", second_report)
        self.assertIn("Share of Voice:", second_report)

    def test_report_subcommand_rerenders_stored_run(self):
        main(["run", "--config", str(self.config_path)])
        exit_code = main(["report", "--config", str(self.config_path), "--run-id", "1"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
