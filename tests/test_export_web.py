import json
import tempfile
import unittest
from pathlib import Path

from e100_visibility.cli import main
from e100_visibility.providers.base import ProviderResponse
from e100_visibility.providers.registry import register_provider

CONFIG_TEMPLATE = """
queries = ["Jakie są najlepsze karty paliwowe dla firm?"]

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
kind = "test-export-fake"
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


class ExportWebTests(unittest.TestCase):
    def setUp(self):
        register_provider("test-export-fake", _FakeProvider)
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.config_path = self.tmp_path / "config.toml"
        self.storage_path = self.tmp_path / "history.sqlite3"
        self.output_dir = self.tmp_path / "output"
        self.web_dir = self.tmp_path / "web"
        self.config_path.write_text(
            CONFIG_TEMPLATE.format(storage_path=self.storage_path, output_dir=self.output_dir)
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_export_after_two_runs_contains_both_with_correct_structure(self):
        exit_code_1 = main(["run", "--config", str(self.config_path)])
        exit_code_2 = main(["run", "--config", str(self.config_path)])
        self.assertEqual(exit_code_1, 0)
        self.assertEqual(exit_code_2, 0)

        exit_code_export = main(["export-web", "--config", str(self.config_path), "--out", str(self.web_dir)])
        self.assertEqual(exit_code_export, 0)

        runs_json_path = self.web_dir / "runs.json"
        self.assertTrue(runs_json_path.exists())
        runs = json.loads(runs_json_path.read_text())

        self.assertEqual(len(runs), 2)
        self.assertEqual([r["run_id"] for r in runs], [1, 2])
        # timestamps must be present and distinguish the two runs' insertion order
        self.assertTrue(all(r["timestamp"] for r in runs))

        first, second = runs
        self.assertEqual(first["market"], {"language": "pl", "country": "PL", "label": "Poland"})
        self.assertIsNone(first["aggregate"]["trend_overall"])  # no history before run 1
        self.assertIsNotNone(second["aggregate"]["trend_overall"])  # run 2 has run 1 as history

        self.assertEqual(len(first["observations"]), 1)
        obs = first["observations"][0]
        self.assertEqual(obs["provider"], "fake")
        self.assertTrue(obs["mentioned"])
        self.assertEqual(obs["position"], 1)
        # never the raw answer text or raw API payload
        self.assertNotIn("answer_text", obs)
        self.assertNotIn("raw", obs)
        serialized = runs_json_path.read_text()
        self.assertNotIn("najlepsza karta paliwowa", serialized)

    def test_export_with_no_runs_writes_empty_array(self):
        exit_code = main(["export-web", "--config", str(self.config_path), "--out", str(self.web_dir)])
        self.assertEqual(exit_code, 0)
        runs = json.loads((self.web_dir / "runs.json").read_text())
        self.assertEqual(runs, [])


if __name__ == "__main__":
    unittest.main()
