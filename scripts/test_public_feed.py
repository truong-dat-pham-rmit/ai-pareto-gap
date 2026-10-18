"""Public country aggregates are downloaded without credentials and checked locally."""

from copy import deepcopy
import io
import json
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from public_feed import (
    MAX_FEED_BYTES, PUBLIC_FEED_URL, FeedError, fetch_public_feed, prepare_public_results,
)


ROOT = Path(__file__).resolve().parents[1]


def feed():
    rows = []
    for month, cutoff, us, cn in [
        ("2026-01", "2026-01-31", 1, .5),
        ("2026-02", "2026-02-28", 4, 3),
        ("2026-03", "2026-03-10", 6, 5),
    ]:
        rows.append({
            "month": month, "cutoff_date": cutoff, "partial": False,
            "countries": {
                "us": {"slope_area": us, "staircase_area": us - .2},
                "cn": {"slope_area": cn, "staircase_area": cn - .1},
            },
            "slope_G": 999, "staircase_G": 999,
            "monthly_lag": {"status": "made_up", "lag_min": 100},
        })
    return {
        "metadata": {"snapshot_date": "2026-03-10", "intelligence_index_version": "4.4", "refresh_status": "seed_snapshot"},
        "scenarios": [{"id": "example", "score_policy": "api_published", "floor": 30,
                       "budget_min": .01, "budget_max": 10, "series": rows,
                       "latest_frontiers": {"us": {"models": ["raw observation marker"]}}}],
    }


def response(payload):
    return io.BytesIO(payload if isinstance(payload, bytes) else json.dumps(payload).encode())


class DownloadTests(TestCase):
    def test_fixed_github_url_without_authentication(self):
        payload = feed()
        opener, progress = Mock(return_value=response(payload)), Mock()
        self.assertEqual(fetch_public_feed(opener=opener, progress=progress), payload)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, PUBLIC_FEED_URL)
        self.assertIsNone(request.get_header("X-api-key"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(opener.call_args.kwargs["timeout"], 30)
        progress.assert_called_once()

    def test_network_and_http_errors_are_actionable(self):
        problems = [HTTPError(PUBLIC_FEED_URL, 404, "not found", {}, None),
                    HTTPError(PUBLIC_FEED_URL, 500, "failure", {}, None),
                    TimeoutError(), URLError("connection refused")]
        for problem in problems:
            with self.subTest(problem=type(problem)), self.assertRaises(FeedError) as caught:
                fetch_public_feed(opener=Mock(side_effect=problem))
            self.assertIn("public results", str(caught.exception))

    def test_invalid_json_or_oversized_download_is_rejected(self):
        for content in [b"not json", b"[]", b" " * (MAX_FEED_BYTES + 1)]:
            with self.subTest(size=len(content)), self.assertRaises(FeedError):
                fetch_public_feed(opener=Mock(return_value=response(content)))


class AggregateTests(TestCase):
    def test_recomputes_gaps_and_monthly_crossings_instead_of_trusting_feed_fields(self):
        result = prepare_public_results(feed())
        latest = result["scenarios"][0]["series"][-1]
        self.assertEqual(latest["slope_G"], 1)
        self.assertAlmostEqual(latest["staircase_G"], .9)
        self.assertEqual(latest["monthly_lag"]["status"], "unique_crossing")
        self.assertEqual(latest["monthly_lag"]["equivalent_us_start"], "2026-02")
        self.assertEqual(latest["monthly_lag"]["equivalent_us_end"], "2026-03")
        self.assertEqual((latest["monthly_lag"]["lag_min"], latest["monthly_lag"]["lag_max"]), (0, 1))
        self.assertTrue(latest["partial"])
        self.assertEqual(result["metadata"]["snapshot_date"], "2026-03-10")
        self.assertEqual(result["metadata"]["refresh_status"], "seed_snapshot")
        self.assertTrue(result["metadata"]["aggregate_only"])
        self.assertNotIn("raw observation marker", json.dumps(result))

    def test_missing_country_areas_remain_missing_instead_of_zero(self):
        payload = feed()
        payload["scenarios"][0]["series"][-1]["countries"]["cn"] = {"slope_area": None, "staircase_area": None}
        latest = prepare_public_results(payload)["scenarios"][0]["series"][-1]
        self.assertIsNone(latest["slope_G"])
        self.assertIsNone(latest["staircase_G"])
        self.assertEqual(latest["monthly_lag"]["status"], "missing_china")

    def test_release_events_are_publisher_supplied_and_absent_events_are_not_invented(self):
        payload = feed()
        no_event = prepare_public_results(payload)["scenarios"][0]["series"][-1]
        self.assertEqual(no_event["release_event_lag"], {"status": "not_supplied"})
        self.assertNotIn("first_observed_at_or_above", no_event["release_event_lag"])
        published = {"status": "unique_crossing", "first_observed_at_or_above": "2026-03-04",
                     "elapsed_since_first_observed_at_or_above": 6, "unit": "days"}
        payload["scenarios"][0]["series"][-1]["release_event_lag"] = published
        result = prepare_public_results(payload)
        latest = result["scenarios"][0]["series"][-1]
        self.assertEqual(latest["release_event_lag"], published)
        self.assertEqual(latest["release_event_lag_source"], "publisher")
        self.assertIn("Publisher-supplied", result["metadata"]["release_event_lag_basis"])

    def test_nonfinite_boolean_negative_and_string_areas_are_rejected(self):
        for value in [float("nan"), float("inf"), True, -1, "6"]:
            payload = feed()
            payload["scenarios"][0]["series"][-1]["countries"]["us"]["slope_area"] = value
            with self.subTest(value=value), self.assertRaises(FeedError):
                prepare_public_results(payload)

    def test_version_drift_and_invalid_version_labels_are_rejected(self):
        for target in ("metadata", "scenario", "row"):
            payload = feed()
            container = payload["metadata"] if target == "metadata" else payload["scenarios"][0]
            if target == "row":
                container = container["series"][-1]
            container["intelligence_index_version"] = True if target == "metadata" else "5.1"
            with self.subTest(target=target), self.assertRaises(FeedError):
                prepare_public_results(payload)

    def test_inconsistent_dates_budgets_and_duplicate_scenarios_are_rejected(self):
        bad_feeds = []
        payload = feed()
        payload["metadata"]["snapshot_date"] = "2026-03-11"
        bad_feeds.append(payload)
        payload = feed()
        payload["scenarios"][0]["series"][0]["month"] = "2026-02"
        bad_feeds.append(payload)
        payload = feed()
        payload["scenarios"][0]["budget_min"] = 0
        bad_feeds.append(payload)
        payload = feed()
        payload["scenarios"].append(deepcopy(payload["scenarios"][0]))
        bad_feeds.append(payload)
        for payload in bad_feeds:
            with self.subTest(payload=payload), self.assertRaises(FeedError):
                prepare_public_results(payload)

    def test_original_public_seed_has_24_scenarios_and_preserves_october_7_snapshot(self):
        payload = json.loads((ROOT / "reports/monthly-comparison.json").read_text(encoding="utf-8"))
        result = prepare_public_results(payload)
        self.assertEqual(len(result["scenarios"]), 24)
        self.assertEqual(len(result["scenarios"][0]["series"]), 22)
        self.assertEqual(result["metadata"]["snapshot_date"], "2026-10-07")
        primary = next(row for row in result["scenarios"] if row["score_policy"] == "measured" and row["floor"] == 30 and row["budget_min"] == .01 and row["budget_max"] == 10)
        self.assertAlmostEqual(primary["series"][-1]["slope_G"], 4.311, places=3)

    def test_preparation_does_not_mutate_downloaded_payload(self):
        payload = feed()
        original = deepcopy(payload)
        prepare_public_results(payload)
        self.assertEqual(payload, original)


if __name__ == "__main__":
    main()
