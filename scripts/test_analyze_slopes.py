"""Analytical checks for log-cost interpolation and nonmonotonic histories."""

import unittest

from analyze_frontiers import area_score, normalize_records, pareto_frontier
from analyze_slopes import analyze_slopes, interpolated_score, slope_area_score, target_crossings


def model(name, cost, intelligence, **extra):
    return {"slug": name, "name": name, "cost_per_task": cost,
            "intelligence": intelligence, "country": "us", "release_date": "2026-03-01", "estimated": False, **extra}


def frontier(*rows):
    return pareto_frontier(normalize_records(rows))


class InterpolationTests(unittest.TestCase):
    def setUp(self):
        self.rows = (model("a", .1, 40), model("b", 10, 48))
        self.curve = frontier(*self.rows)

    def test_user_example_and_average(self):
        self.assertAlmostEqual(interpolated_score(self.curve, 1), 44)
        self.assertAlmostEqual(slope_area_score(self.curve, .1, 10, 0), 44)

    def test_clip_after_interpolation_not_before(self):
        self.assertAlmostEqual(slope_area_score(self.curve, .1, 10, 44), 1)

    def test_bounds_inside_segment_keep_outside_anchors(self):
        self.assertAlmostEqual(slope_area_score(self.curve, .2, 5, 0), 44)

    def test_floor_crossing_inside_clipped_budget(self):
        self.assertAlmostEqual(slope_area_score(self.curve, 1, 10, 46), .5)

    def test_no_extrapolation_at_either_end(self):
        self.assertIsNone(interpolated_score(self.curve, .01))
        self.assertEqual(interpolated_score(self.curve, 100), 48)
        self.assertEqual(slope_area_score(self.curve, .001, .1, 0), 0)
        self.assertEqual(slope_area_score(self.curve, 10, 100, 0), 48)

    def test_single_observation_is_staircase(self):
        curve = frontier(self.rows[1])
        self.assertAlmostEqual(slope_area_score(curve, .1, 100, 40), 8 / 3)
        self.assertEqual(slope_area_score(curve, .1, 100, 40), area_score(curve, .1, 100, 40))

    def test_duplicate_cost_and_dominated_options(self):
        curve = frontier(*self.rows, model("dominated", 1, 20), model("same_price", 10, 47))
        self.assertEqual(slope_area_score(curve, .01, 100, 20), slope_area_score(self.curve, .01, 100, 20))

    def test_currency_scale_invariance(self):
        scaled = frontier(model("a", 10, 40), model("b", 1000, 48))
        self.assertAlmostEqual(slope_area_score(scaled, 1, 10000, 42), slope_area_score(self.curve, .01, 100, 42))

    def test_smooth_never_below_step_at_fixed_cohort(self):
        for floor in (0, 40, 43, 44, 48, 60):
            self.assertGreaterEqual(slope_area_score(self.curve, .01, 100, floor), area_score(self.curve, .01, 100, floor))

    def test_new_observation_can_lower_assumed_curve(self):
        inserted = frontier(*self.rows, model("middle", 1, 41))
        self.assertAlmostEqual(slope_area_score(inserted, .1, 10, 0), 42.5)
        self.assertLess(slope_area_score(inserted, .1, 10, 0), slope_area_score(self.curve, .1, 10, 0))
        self.assertGreaterEqual(area_score(inserted, .1, 10, 0), area_score(self.curve, .1, 10, 0))

    def test_empty_and_invalid_budget(self):
        self.assertEqual(slope_area_score([], .01, 10, 30), 0)
        with self.assertRaises(ValueError):
            slope_area_score(self.curve, 10, .1, 30)


class CrossingTests(unittest.TestCase):
    @staticmethod
    def history(values):
        return [{"at": f"2026-{i:02d}", "value": value} for i, value in enumerate(values, 1)]

    def test_unrelated_decline_does_not_invalidate_unique_crossing(self):
        answer = target_crossings("2026-04", 10, self.history([1, 3, 2, 12]), "months")
        self.assertEqual(answer["status"], "unique_crossing")
        self.assertTrue(answer["history_has_decreases"])
        self.assertEqual((answer["lag_min"], answer["lag_max"]), (0, 1))

    def test_multiple_crossings_not_single_lag(self):
        answer = target_crossings("2026-04", 10, self.history([1, 12, 5, 14]), "months")
        self.assertEqual(answer["status"], "multiple_crossings")
        self.assertIsNone(answer["lag_min"])

    def test_ahead_at_cutoff_overrides_prior_attainment(self):
        answer = target_crossings("2026-03", 10, self.history([1, 12, 5]), "months")
        self.assertEqual(answer["status"], "ahead_of_us_at_cutoff")
        self.assertIsNone(answer["lag_min"])
        self.assertEqual(answer["first_observed_at_or_above"], "2026-02")

    def test_no_future_leakage(self):
        answer = target_crossings("2026-02", 10, self.history([1, 3, 20]), "months")
        self.assertEqual(answer["status"], "ahead_of_us_at_cutoff")
        self.assertIsNone(answer["first_observed_at_or_above"])

    def test_zero_missing_and_left_censored(self):
        history = self.history([None, 10])
        self.assertEqual(target_crossings("2026-02", 0, history, "months")["status"], "no_above_floor_coverage")
        self.assertEqual(target_crossings("2026-02", None, history, "months")["status"], "missing_china")
        self.assertEqual(target_crossings("2026-01", 5, history, "months")["status"], "missing_us")
        self.assertEqual(target_crossings("2026-02", 5, history, "months")["status"], "before_observation_window")

    def test_day_crossing_and_elapsed_time(self):
        history = [{"at": "2026-09-21", "value": 10}, {"at": "2026-09-22", "value": 14}]
        answer = target_crossings("2026-10-07", 12, history, "days")
        self.assertEqual(answer["first_observed_at_or_above"], "2026-09-22")
        self.assertEqual(answer["elapsed_since_first_observed_at_or_above"], 15)

    def test_equal_values_report_observations(self):
        answer = target_crossings("2026-04", 10, self.history([1, 10, 10, 20]), "months")
        self.assertEqual(answer["status"], "observed_equal_values")
        self.assertEqual(answer["equal_observations"], ["2026-02", "2026-03"])


class DataPolicyTests(unittest.TestCase):
    def test_missing_cost_and_future_and_estimated_policy(self):
        rows = [model("u", 1, 40), model("c", 1, 35, country="cn"),
                model("missing", None, 90), model("estimate", .1, 60, estimated=True),
                model("future", .01, 100, release_date="2026-10-08")]
        result = analyze_slopes(rows)
        primary = next(s for s in result["scenarios"] if s["id"] == "measured_b0.01-10_f30")
        self.assertIsNone(primary["series"][0]["countries"]["us"]["slope_area"])
        self.assertAlmostEqual(primary["series"][-1]["countries"]["us"]["slope_area"], 10 / 3)
        with_estimated = next(s for s in result["scenarios"] if s["id"] == "including_estimated_b0.01-10_f30")
        self.assertGreater(with_estimated["series"][-1]["countries"]["us"]["slope_area"], 10 / 3)


if __name__ == "__main__":
    unittest.main()
