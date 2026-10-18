"""Dynamic snapshots and explicit score provenance for local/API analyses."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from analyze_frontiers import analyze, eligible_score_models, normalize_records
from analyze_slopes import analyze_slopes, summary_text


ROOT = Path(__file__).resolve().parents[1]


def model(slug="us", country="us", **extra):
    return {"slug": slug, "country": country, "release_date": "2027-02-01",
            "intelligence": 42, "cost_per_task": .1, "estimated": False, **extra}


class DynamicSnapshotTests(unittest.TestCase):
    def test_date_version_and_policy_propagate_in_both_analyses(self):
        records = [model(), model("cn", "cn", intelligence=40)]
        for function in (analyze, analyze_slopes):
            with self.subTest(function=function.__name__):
                result = function(records, snapshot=date(2027, 3, 12),
                                  first_month="2027-01", index_version="5.1-test",
                                  policies=("api_published",))
                self.assertEqual(result["metadata"]["snapshot_date"], "2027-03-12")
                self.assertEqual(result["metadata"]["intelligence_index_version"], "5.1-test")
                self.assertEqual(len(result["scenarios"]), 12)
                self.assertTrue(all(s["score_policy"] == "api_published" for s in result["scenarios"]))
                rows = result["scenarios"][0]["series"]
                self.assertEqual([r["month"] for r in rows], ["2027-01", "2027-02", "2027-03"])
                self.assertEqual(rows[-1]["cutoff_date"], "2027-03-12")
                self.assertTrue(rows[-1]["partial"])
                if function is analyze:
                    self.assertEqual(result["settings"]["primary_score_policy"], "api_published")
                    self.assertIn("api_published", result["snapshot_country_counts"]["us"]["by_policy"])

    def test_unknown_estimate_status_stays_unknown_and_is_not_measured(self):
        records = [model("measured"), model("estimated", estimated=True),
                   model("unknown", estimated=None), model("string", estimated="false")]
        omitted = model("omitted")
        del omitted["estimated"]
        records.append(omitted)
        normalized = normalize_records(records)
        self.assertEqual([r["estimated"] for r in normalized], [False, True, None, None, None])
        measured = eligible_score_models(normalized, "us", "2027-03-12", "measured")
        self.assertEqual([r["slug"] for r in measured], ["measured"])
        for policy in ("including_estimated", "api_published"):
            self.assertEqual(len(eligible_score_models(normalized, "us", "2027-03-12", policy)), 5)
        result = analyze(records, snapshot=date(2027, 3, 12), first_month="2027-02",
                         policies=("api_published",))
        self.assertEqual(result["snapshot_country_counts"]["us"]["unknown_estimate_status_records"], 3)
        latest = result["scenarios"][0]["latest"]["countries"]["us"]
        self.assertEqual(latest["estimated_costed_model_count"], 1)
        self.assertEqual(latest["unknown_estimate_status_costed_model_count"], 3)

    def test_missing_country_and_cost_are_safe_in_analysis_and_summary(self):
        for records in ([], [model()], [model("cn", "cn")],
                        [model(cost_per_task=None), model("cn", "cn", cost_per_task=None)]):
            with self.subTest(records=records):
                kwargs = {"snapshot": date(2027, 3, 12), "first_month": "2027-01",
                          "index_version": "5.1-test", "policies": ("api_published",)}
                baseline = analyze(records, **kwargs)
                slopes = analyze_slopes(records, **kwargs)
                self.assertIsNone(baseline["scenarios"][0]["latest"]["gap_us_minus_cn"])
                self.assertIsNone(slopes["scenarios"][0]["series"][-1]["slope_G"])
                text = summary_text(slopes)
                self.assertIn("N/A", text)
                self.assertIn("2027-03-12", text)
                self.assertIn("5.1-test", text)
                for stale in ("October", "Oct7", "v4.3.2", "9.357972", "113 US"):
                    self.assertNotIn(stale, text)

    def test_invalid_policies_and_observation_windows_are_rejected(self):
        for function in (analyze, analyze_slopes):
            for policies in ((), ("unknown",), ("measured", "measured"), "measured"):
                with self.subTest(function=function.__name__, policies=policies):
                    with self.assertRaises(ValueError):
                        function([], policies=policies)
            with self.assertRaises(ValueError):
                function([], snapshot=date(2027, 1, 1), first_month="2027-02")
            with self.assertRaises(ValueError):
                function([], first_month="2026-13")

    def test_cli_accepts_dynamic_metadata_and_utf8_bom(self):
        with tempfile.TemporaryDirectory(prefix=".test-dynamic-", dir=ROOT) as directory:
            folder = Path(directory)
            input_file = folder / "models.json"
            input_file.write_text(json.dumps([model(), model("cn", "cn")]), encoding="utf-8-sig")
            for script in ("analyze_frontiers.py", "analyze_slopes.py"):
                output = folder / f"{script}.json"
                command = [sys.executable, str(ROOT / "scripts" / script), "--input", str(input_file),
                           "--output", str(output), "--snapshot", "2027-03-12", "--first-month", "2027-02",
                           "--index-version", "5.1-test", "--policies", "api_published"]
                if script == "analyze_slopes.py":
                    command.extend(["--summary", str(folder / "summary.txt")])
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(result["metadata"]["snapshot_date"], "2027-03-12")
                self.assertEqual(result["metadata"]["intelligence_index_version"], "5.1-test")


if __name__ == "__main__":
    unittest.main()
