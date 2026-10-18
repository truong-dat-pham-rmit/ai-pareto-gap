"""Exercise the beginner CLI with real analysis/report code and synthetic API data."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import tempfile
from unittest import TestCase, main
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pareto_beginner_cli", ROOT / "run.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
TEST_KEY = "synthetic-test-key-must-never-be-saved"


def api_model(slug, creator, released, score, cost):
    return {
        "id": "synthetic-id-" + slug,
        "slug": slug,
        "name": "Synthetic configuration " + slug,
        "release_date": released,
        "model_creator": {"id": "synthetic-creator-" + creator, "name": creator},
        "evaluations": {"artificial_analysis_intelligence_index": score},
        "artificial_analysis_intelligence_index_cost": {
            "total_cost": 9999,
            "cost_per_task": {"total_cost": cost},
        },
        "pricing": {"price_1m_input_tokens": 777, "price_1m_output_tokens": 888},
    }


def api_payload():
    return {
        "requested_tier": "free",
        "tier": "free",
        "intelligence_index_version": 4.4,
        "metadata": {
            "pages_fetched": 1,
            "fetched_at_utc": "2026-10-18T01:23:45+00:00",
            "endpoint": "https://artificialanalysis.ai/api/v2/language/models/free",
        },
        "data": [
            api_model("us-small", "OpenAI", "2026-01-03", 35, .02),
            api_model("us-large", "OpenAI", "2026-06-01", 52, 1),
            api_model("cn-small", "DeepSeek", "2026-02-03", 34, .015),
            api_model("cn-large", "DeepSeek", "2026-09-01", 47, .3),
        ],
    }


class BeginnerRunnerTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".test-run-", dir=ROOT)
        self.folder = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def invoke(self, arguments, *, payload=None, key=TEST_KEY, public=False):
        arguments = list(arguments)
        if not public and not any(mode in arguments for mode in ("--demo", "--input")):
            arguments.insert(0, "--live")
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"AA_API_KEY": key}), \
             patch.object(CLI, "fetch_models", return_value=payload or api_payload()) as fetch, \
             patch.object(CLI.webbrowser, "open") as browser, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            status = CLI.main(["--no-open", "--output-dir", str(self.folder / "results"), *arguments])
        browser.assert_not_called()
        return status, stdout.getvalue(), stderr.getvalue(), fetch

    def reports(self):
        return sorted((self.folder / "results").glob("*/report.html"))

    def test_live_download_reaches_real_math_and_report_without_saving_key(self):
        status, stdout, stderr, fetch = self.invoke(["--as-of", "2026-10-18"])
        self.assertEqual(status, 0, stderr)
        self.assertEqual(fetch.call_args.args[0], TEST_KEY)
        self.assertEqual(fetch.call_args.kwargs["tier"], "free")
        report = self.reports()[0]
        output = report.parent
        expected_files = {"api-response.json", "models.json", "provenance.json", "staircase.json", "slopes.json", "summary.txt", "report.html"}
        self.assertTrue(expected_files.issubset({path.name for path in output.iterdir()}))
        records = json.loads((output / "models.json").read_text(encoding="utf-8"))
        self.assertEqual([row["cost_per_task"] for row in records], [.02, 1, .015, .3])
        self.assertEqual([row["country"] for row in records], ["us", "us", "cn", "cn"])
        self.assertTrue(all(row["estimated"] is None for row in records))
        for filename in ("staircase.json", "slopes.json"):
            results = json.loads((output / filename).read_text(encoding="utf-8"))
            self.assertEqual(results["metadata"]["snapshot_date"], "2026-10-18")
            self.assertEqual(results["metadata"]["intelligence_index_version"], "4.4")
            self.assertTrue(all(row["score_policy"] == "api_published" for row in results["scenarios"]))
        slopes = json.loads((output / "slopes.json").read_text(encoding="utf-8"))
        selected = next(row for row in slopes["scenarios"] if row["floor"] == 30 and row["budget_min"] == .01 and row["budget_max"] == 10)
        expected_us = (13.5 * math.log(50) + 22 * math.log(10)) / math.log(1000)
        expected_cn = (10.5 * math.log(20) + 17 * math.log(10 / .3)) / math.log(1000)
        self.assertAlmostEqual(selected["series"][-1]["slope_G"], expected_us - expected_cn)
        self.assertIn("estimate status unavailable", report.read_text(encoding="utf-8"))
        for path in output.iterdir():
            if path.is_file():
                self.assertNotIn(TEST_KEY.encode(), path.read_bytes(), path.name)
        self.assertNotIn(TEST_KEY, stdout + stderr)

    def test_missing_country_saves_coverage_report_and_returns_two(self):
        payload = api_payload()
        payload["data"] = payload["data"][:2]
        status, stdout, stderr, _ = self.invoke(["--as-of", "2026-10-18"], payload=payload)
        self.assertEqual(status, 2, stderr)
        self.assertIn("one country lacks", stdout)
        report = self.reports()[0]
        content = report.read_text(encoding="utf-8")
        self.assertIn("Data coverage and country assignment", content)
        self.assertIn("Missing", content)
        slopes = json.loads((report.parent / "slopes.json").read_text(encoding="utf-8"))
        self.assertIsNone(slopes["scenarios"][0]["series"][-1]["slope_G"])

    def test_saved_api_response_replays_without_network_or_key(self):
        cached = self.folder / "cached-api.json"
        cached.write_text(json.dumps(api_payload()), encoding="utf-8")
        status, stdout, stderr, fetch = self.invoke(["--input", str(cached), "--as-of", "2026-10-18"], key="")
        self.assertEqual(status, 0, stderr)
        fetch.assert_not_called()
        provenance = json.loads((self.reports()[0].parent / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["snapshot_date"], "2026-10-18")
        self.assertEqual(provenance["intelligence_index_version"], "4.4")
        self.assertEqual(provenance["country_audit"]["country_sources"]["registry"], 4)
        self.assertNotIn("Paste your AA API key", stdout)

    def test_cached_missing_or_invalid_fetch_date_needs_explicit_cutoff(self):
        for stamp in (None, "not-a-date"):
            with self.subTest(stamp=stamp):
                payload = api_payload()
                payload["metadata"]["fetched_at_utc"] = stamp
                cached = self.folder / "undated-api.json"
                cached.write_text(json.dumps(payload), encoding="utf-8")
                status, _, stderr, fetch = self.invoke(["--input", str(cached)], key="")
                self.assertEqual(status, 2)
                self.assertIn("Could not finish", stderr)
                fetch.assert_not_called()
                status, _, stderr, fetch = self.invoke(["--input", str(cached), "--as-of", "2026-10-18"], key="")
                self.assertEqual(status, 0, stderr)
                fetch.assert_not_called()
                provenance = json.loads((self.reports()[-1].parent / "provenance.json").read_text(encoding="utf-8"))
                self.assertEqual(provenance["snapshot_date"], "2026-10-18")

    def test_noninteractive_without_key_explains_setup_without_prompting(self):
        with patch.object(CLI.sys.stdin, "isatty", return_value=False), patch.object(CLI.getpass, "getpass") as prompt:
            status, stdout, stderr, fetch = self.invoke([], key="")
        self.assertEqual(status, 2)
        fetch.assert_not_called()
        prompt.assert_not_called()
        self.assertIn("API key is required", stdout)
        self.assertIn("No API key found", stderr)
        self.assertIn("AA_API_KEY", stderr)
        self.assertFalse(self.reports())

    def test_demo_runs_real_analysis_offline_and_is_clearly_synthetic(self):
        status, stdout, stderr, fetch = self.invoke(["--demo"], key="")
        self.assertEqual(status, 0, stderr)
        fetch.assert_not_called()
        self.assertIn("SYNTHETIC DEMONSTRATION", stdout)
        report = self.reports()[0]
        self.assertIn("all model observations and results in this report are fictional", report.read_text(encoding="utf-8"))
        provenance = json.loads((report.parent / "provenance.json").read_text(encoding="utf-8"))
        self.assertTrue(provenance["synthetic"])
        self.assertEqual(provenance["intelligence_index_version"], "synthetic")
        self.assertFalse((report.parent / "api-response.json").exists())

    def test_normalized_replay_reuses_saved_snapshot_metadata(self):
        status, _, stderr, _ = self.invoke(["--as-of", "2026-10-18"])
        self.assertEqual(status, 0, stderr)
        original = self.reports()[0].parent
        status, stdout, stderr, fetch = self.invoke(["--input", str(original / "models.json")], key="")
        self.assertEqual(status, 0, stderr)
        fetch.assert_not_called()
        replay = self.reports()[-1].parent
        provenance = json.loads((replay / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["snapshot_date"], "2026-10-18")
        self.assertEqual(provenance["intelligence_index_version"], "4.4")
        self.assertEqual((replay / "slopes.json").read_bytes(), (original / "slopes.json").read_bytes())
        self.assertIn("Reading local input", stdout)

    def test_default_downloads_public_aggregates_without_account_and_recomputes_gap(self):
        payload = json.loads((ROOT / "reports/monthly-comparison.json").read_text(encoding="utf-8"))
        for scenario in payload["scenarios"]:
            for row in scenario["series"]:
                row["slope_G"] = 123456
        with patch.object(CLI, "fetch_public_feed", return_value=payload) as fetch_public, \
             patch.object(CLI.getpass, "getpass") as prompt:
            status, stdout, stderr, fetch_api = self.invoke([], key="", public=True)
        self.assertEqual(status, 0, stderr)
        fetch_public.assert_called_once()
        fetch_api.assert_not_called()
        prompt.assert_not_called()
        report = self.reports()[0]
        provenance = json.loads((report.parent / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["snapshot_date"], "2026-10-07")
        self.assertFalse((report.parent / "models.json").exists())
        self.assertFalse((report.parent / "api-response.json").exists())
        self.assertIn("2026-10-07", report.read_text(encoding="utf-8"))
        self.assertNotIn("Paste your AA API key", stdout)
        result_files = [json.loads(path.read_text(encoding="utf-8")) for path in report.parent.glob("*.json")]
        recomputed = [value for value in result_files if isinstance(value, dict) and "scenarios" in value
                      and value.get("metadata", {}).get("gap_calculation")]
        self.assertTrue(recomputed, "A locally recomputed aggregate result must be saved")
        primary = next(row for row in recomputed[0]["scenarios"] if row["score_policy"] == "measured" and row["floor"] == 30 and row["budget_min"] == .01 and row["budget_max"] == 10)
        self.assertAlmostEqual(primary["series"][-1]["slope_G"], 4.311, places=3)

    def test_default_network_failure_uses_labeled_bundled_snapshot_without_asking_for_key(self):
        from public_feed import FeedError

        with patch.object(CLI, "fetch_public_feed", side_effect=FeedError("Public feed unavailable")), \
             patch.object(CLI.getpass, "getpass") as prompt:
            status, stdout, stderr, fetch_api = self.invoke([], key="", public=True)
        self.assertEqual(status, 0, stderr)
        fetch_api.assert_not_called()
        prompt.assert_not_called()
        self.assertIn("2026-10-07", self.reports()[0].read_text(encoding="utf-8"))
        self.assertRegex((stdout + stderr).lower(), r"bundled|fallback|cached")

    def test_offline_public_snapshot_and_cached_aggregate_replay_need_no_network(self):
        with patch.object(CLI, "fetch_public_feed") as fetch_public:
            status, _, stderr, fetch_api = self.invoke(["--offline"], key="", public=True)
        self.assertEqual(status, 0, stderr)
        fetch_public.assert_not_called()
        fetch_api.assert_not_called()
        saved = self.reports()[0].parent / "published-results.json"
        self.assertTrue(saved.exists())
        with patch.object(CLI, "fetch_public_feed") as fetch_public:
            status, _, stderr, fetch_api = self.invoke(["--input", str(saved)], key="", public=True)
        self.assertEqual(status, 0, stderr)
        fetch_public.assert_not_called()
        fetch_api.assert_not_called()
        latest = self.reports()[-1].parent
        self.assertEqual((latest / "published-results.json").read_bytes(), saved.read_bytes())


if __name__ == "__main__":
    main()
