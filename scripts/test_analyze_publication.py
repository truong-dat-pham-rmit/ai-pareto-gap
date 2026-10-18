"""Publication checks for source-data exclusion and aggregate consistency."""

import json
import unittest
from pathlib import Path

from analyze_frontiers import analyze
from analyze_slopes import analyze_slopes
from export_report import export_aggregates


ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def test_export_does_not_copy_source_records_or_local_metadata(self):
        models = [
            {"slug": "PRIVATE_SOURCE_MARKER", "name": "PRIVATE_SOURCE_MARKER", "country": "us",
             "release_date": "2026-03-01", "intelligence": 40, "cost_per_task": .1, "estimated": False},
            {"slug": "cn", "country": "cn", "release_date": "2026-03-01",
             "intelligence": 38, "cost_per_task": .1, "estimated": False},
        ]
        baseline, slopes = analyze(models), analyze_slopes(models)
        slopes["metadata"].update(input_sha256="test-hash", input_file="PRIVATE_SOURCE_MARKER")
        report = export_aggregates(slopes, baseline)
        serialized = json.dumps(report)
        for forbidden in ("PRIVATE_SOURCE_MARKER", "latest_frontiers", "cost_per_task", "frontier_model"):
            self.assertNotIn(forbidden, serialized)

    def test_published_aggregate_gaps_match_country_areas(self):
        report = json.loads((ROOT / "reports/monthly-comparison.json").read_text(encoding="utf-8"))
        for scenario in report["scenarios"]:
            for row in scenario["series"]:
                us, cn = row["countries"]["us"], row["countries"]["cn"]
                if us["slope_area"] is None or cn["slope_area"] is None:
                    self.assertIsNone(row["slope_G"])
                else:
                    self.assertAlmostEqual(row["slope_G"], us["slope_area"] - cn["slope_area"])
                    self.assertAlmostEqual(row["staircase_G"], us["staircase_area"] - cn["staircase_area"])

    def test_demo_uses_identifiably_synthetic_records(self):
        rows = json.loads((ROOT / "examples/models-synthetic.json").read_text(encoding="utf-8"))
        self.assertTrue(rows)
        self.assertTrue(all(row["name"].startswith("Synthetic ") for row in rows))


if __name__ == "__main__":
    unittest.main()
