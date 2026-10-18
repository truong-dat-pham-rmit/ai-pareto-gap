"""Offline report checks for missingness, source safety, and chart semantics."""

import copy
import tempfile
import unittest
from pathlib import Path

from live_report import _crossing_text, _gap_svg, _score_at, write_report


def sample_result():
    row = {
        "month": "2030-02", "cutoff_date": "2030-02-12", "partial": True,
        "countries": {
            "us": {"slope_area": 6, "staircase_area": 4},
            "cn": {"slope_area": 5, "staircase_area": 2},
        },
        "slope_G": 1, "staircase_G": 2,
        "monthly_lag": {"status": "unique_crossing", "equivalent_us_start": "2030-01",
                        "equivalent_us_end": "2030-02", "lag_min": 0, "lag_max": 1},
        "release_event_lag": {"status": "unique_crossing", "first_observed_at_or_above": "2030-02-03",
                              "elapsed_since_first_observed_at_or_above": 9},
    }
    scenario = {
        "id": "api_published_b0.01-10_f30", "score_policy": "api_published",
        "floor": 30, "budget_min": .01, "budget_max": 10, "series": [row],
        "latest_frontiers": {
            "us": {"models": [
                {"name": "Low anchor", "cost_per_task": .001, "intelligence": 20},
                {"name": "High anchor", "cost_per_task": 100, "intelligence": 60},
            ]},
            "cn": {"models": [{"name": "CN configuration", "cost_per_task": .5,
                                 "intelligence": 40, "release_date": "2030-02-01"}]},
        },
    }
    return {"metadata": {"snapshot_date": "2030-02-12", "intelligence_index_version": "8.2"},
            "scenarios": [scenario]}


class LiveReportTests(unittest.TestCase):
    def render(self, result=None, records=None, provenance=None, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "report.html"
            returned = write_report(result or sample_result(), records or [], provenance or {}, path, **kwargs)
            self.assertEqual(returned, path)
            return path.read_text(encoding="utf-8")

    def test_dynamic_dates_version_partial_and_signed_gap(self):
        page = self.render(provenance={"fetched_at_utc": "2030-02-12T17:00:00Z"})
        self.assertIn("2030-02-12T17:00:00Z", page)
        self.assertIn("8.2", page)
        self.assertIn("partial through 2030-02-12", page)
        self.assertIn("+1.000", page)
        self.assertIn("2030-02-03", page)
        self.assertIn("9 elapsed days", page)
        self.assertNotIn("October", page)
        self.assertNotIn("2026-10-07", page)

    def test_missing_country_remains_missing(self):
        result = sample_result()
        row = result["scenarios"][0]["series"][0]
        row["countries"].pop("cn")
        row["slope_G"] = row["staircase_G"] = None
        row["monthly_lag"] = {"status": "missing_china"}
        row["release_event_lag"] = {"status": "missing_china"}
        page = self.render(result=result)
        self.assertIn('<strong class="cn">Missing</strong>', page)
        self.assertIn("Missing Chinese data", page)
        self.assertNotIn('<strong>+0.000</strong>', page)

    def test_untrusted_text_is_escaped_and_credentials_are_omitted(self):
        result = sample_result()
        result["metadata"]["intelligence_index_version"] = '<script>alert("version")</script>'
        result["scenarios"][0]["latest_frontiers"]["cn"]["models"][0]["name"] = '<img src=x onerror="bad()">'
        page = self.render(result=result, provenance={
            "source": '<b>Source</b>', "api_key": "DO_NOT_RENDER_KEY",
            "headers": {"Authorization": "DO_NOT_RENDER_HEADER"},
            "country_audit": {"api_key": "DO_NOT_RENDER_AUDIT_KEY",
                              "country_sources": {"<script>registry</script>": 2}},
        })
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;img", page)
        self.assertIn("&lt;b&gt;Source&lt;/b&gt;", page)
        self.assertNotIn("DO_NOT_RENDER", page)
        self.assertNotIn("Authorization", page)

    def test_html_is_offline_and_interpolation_is_labeled(self):
        page = self.render()
        self.assertNotIn("<script", page)
        self.assertNotIn("<iframe", page)
        self.assertNotIn("<link", page)
        self.assertNotIn("@import", page)
        self.assertIn("hypothetical interpolation", page)
        self.assertIn("logarithmic scale", page)
        self.assertIn("four decimal places", page)
        self.assertIn('href="https://artificialanalysis.ai/models/"', page)
        self.assertIn("Content-Security-Policy", page)

    def test_outside_budget_anchors_still_define_curve(self):
        models = [(.001, 20, {}), (100, 60, {})]
        self.assertAlmostEqual(_score_at(models, .01, True), 28)
        self.assertAlmostEqual(_score_at(models, 10, True), 52)
        page = self.render()
        self.assertIn('<line class="curve us" x1="72.00"', page)
        self.assertIn('x2="934.00"', page)
        self.assertIn("$0.0010", page)
        self.assertIn("$100.0000", page)

    def test_unknown_estimated_status_and_registry_are_visible(self):
        records = [{"country": "us", "intelligence": 40, "cost_per_task": .2,
                    "release_date": "2030-02-01", "estimated": None},
                   {"country": "cn", "intelligence": 38, "cost_per_task": 0,
                    "release_date": None, "estimated": None}]
        page = self.render(records=records, provenance={"country_registry_version": "reviewed-2030"})
        self.assertIn("unknown for 2 supplied", page)
        self.assertIn("reviewed-2030", page)
        self.assertIn("registry as a fallback", page)
        self.assertIn("Missing or nonpositive task cost", page)

    def test_unknown_creator_names_are_visible_and_escaped(self):
        page = self.render(provenance={"country_audit": {
            "unknown_creators": ["New Lab", '<script>bad()</script>', {"api_key": "DO_NOT_RENDER"}],
        }})
        self.assertIn("Unmapped creators:", page)
        self.assertIn("New Lab", page)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", page)
        self.assertIn("may include labs from other countries", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("DO_NOT_RENDER", page)

    def test_api_published_precision_and_zero_exclusion_are_explicit(self):
        page = self.render()
        self.assertIn("API publishes task costs rounded to four decimal places", page)
        self.assertIn("not unrounded source costs", page)
        self.assertIn("Zero-cost entries are excluded", page)
        self.assertNotIn("calculations retain full precision", page)

    def test_chart_can_scroll_without_shrinking_labels_on_small_screens(self):
        page = self.render()
        self.assertIn('class="chart-wrap" role="region"', page)
        self.assertIn('aria-label="Scrollable cost–capability chart" tabindex="0"', page)
        self.assertIn(".chart-wrap svg{min-width:960px}", page)
        self.assertIn("Scroll the chart horizontally", page)

    def test_synthetic_example_cannot_be_mistaken_for_live_result(self):
        page = self.render(provenance={"synthetic": True, "source": "Synthetic example"})
        self.assertIn("SYNTHETIC EXAMPLE", page)
        self.assertIn("fictional demonstration data", page)

    def test_no_single_lag_claim_when_crossings_are_ambiguous(self):
        event = {"status": "multiple_crossings", "first_observed_at_or_above": "2030-01-01"}
        self.assertIn("no single lag estimate", _crossing_text(event))
        self.assertNotIn("2030-01-01", _crossing_text(event))

    def test_invalid_selection_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "No results"):
            self.render(floor=25)
        with self.assertRaisesRegex(ValueError, "minimum"):
            self.render(budget_min=1, budget_max=1)

    def test_floor_sensitivity_uses_same_policy_and_budget(self):
        result = sample_result()
        for value in (20, 40):
            other = copy.deepcopy(result["scenarios"][0])
            other["floor"] = value
            other["series"][0]["slope_G"] = value + .123
            result["scenarios"].append(other)
        page = self.render(result=result)
        self.assertIn("+20.123", page)
        self.assertIn("+40.123", page)

    def test_published_feed_recomputes_gaps_without_model_records(self):
        result = sample_result()
        scenario = result["scenarios"][0]
        scenario.pop("latest_frontiers")
        scenario["series"][0]["slope_G"] = 999
        scenario["series"][0]["staircase_G"] = 888
        page = self.render(result=result, provenance={"published_feed": True,
                            "source": "Published Pareto Gap results", "published_status": "published_snapshot"})
        self.assertIn("+1.000", page)
        self.assertIn("+2.000", page)
        self.assertNotIn("+999.000", page)
        self.assertNotIn("+888.000", page)
        self.assertIn("Weighted gap by release month", page)
        self.assertIn('class="zero"', page)
        self.assertIn("calculated locally", page)
        self.assertNotIn("Latest Pareto configurations", page)
        self.assertNotIn("Input audit", page)
        self.assertNotIn("No usable cost", page)
        self.assertNotIn("unknown for 0 supplied", page)
        self.assertIn("API-published scores", page)

    def test_seed_snapshot_and_download_times_are_clearly_separate(self):
        page = self.render(provenance={"published_feed": True, "published_status": "seed_snapshot",
                          "fetched_at_utc": "2030-02-12T01:00:00Z",
                          "downloaded_at_utc": "2030-03-21T10:00:00Z"})
        self.assertIn("Latest published snapshot: 2030-02-12", page)
        self.assertIn("older example, not a live measurement", page)
        self.assertIn("Downloading it today does not update the measurement date", page)
        self.assertIn("Source data retrieved (UTC): 2030-02-12T01:00:00Z", page)
        self.assertIn("Feed downloaded (UTC): 2030-03-21T10:00:00Z", page)

    def test_bundled_snapshot_is_not_described_as_fresh_download(self):
        page = self.render(provenance={"published_feed": True, "published_status": "seed_snapshot",
                                      "using_bundled_snapshot": True, "downloaded_at_utc": "2030-03-21T10:00:00Z"})
        self.assertIn("Using the bundled snapshot", page)
        self.assertIn("does not establish today&#x27;s gap", page)
        self.assertIn("Bundled snapshot opened (UTC)", page)
        self.assertNotIn("Feed downloaded (UTC)", page)

    def test_feed_coverage_uses_published_counts_and_omits_source_records(self):
        result = sample_result()
        result["scenarios"][0]["latest_frontiers"]["cn"]["models"][0]["name"] = "PRIVATE MODEL DO NOT RENDER"
        provenance = {"published_feed": True, "feed_metadata": {"coverage": {
            "us": {"total_configurations": 123, "measured_scored_configurations": 110,
                   "measured_costed_configurations": 100},
            "cn": {"total_configurations": 89, "scored_configurations": 80,
                   "costed_configurations": 70},
        }, "api_key": "DO_NOT_RENDER_KEY"}}
        page = self.render(result=result, provenance=provenance)
        self.assertIn("Published snapshot coverage", page)
        self.assertIn("<td>123</td><td>89</td>", page)
        self.assertIn("<td>110</td><td>80</td>", page)
        self.assertIn("<td>100</td><td>70</td>", page)
        self.assertNotIn("PRIVATE MODEL", page)
        self.assertNotIn("DO_NOT_RENDER_KEY", page)
        self.assertNotIn("Missing intelligence score", page)
        self.assertIn("not affiliated with or endorsed by Artificial Analysis", page)

    def test_gap_chart_breaks_lines_across_missing_months(self):
        scenario = {"series": [
            {"month": "2030-01", "slope_G": 2, "staircase_G": 1},
            {"month": "2030-02", "slope_G": None, "staircase_G": None},
            {"month": "2030-03", "slope_G": -1, "staircase_G": -2},
        ]}
        svg = _gap_svg(scenario)
        self.assertNotIn('class="gap-line', svg)
        self.assertEqual(svg.count('class="gap-dot'), 4)
        self.assertIn("2030-01", svg)
        self.assertIn("2030-03", svg)
        self.assertIn("-2.000", svg)

    def test_frozen_measured_feed_does_not_get_api_estimate_warning(self):
        result = sample_result()
        result["scenarios"][0]["score_policy"] = "measured"
        page = self.render(result=result, provenance={"published_feed": True, "published_status": "seed_snapshot"})
        self.assertIn("Measured scores", page)
        self.assertNotIn("API does not expose estimated-score status", page)


if __name__ == "__main__":
    unittest.main()
