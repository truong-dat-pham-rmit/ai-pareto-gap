"""Synthetic correctness checks for the analytical frontier and lag methods."""

import math
import unittest

from analyze_frontiers import (
    analyze, area_score, country_area_summary, frontier_relation, lag_bracket,
    normalize_records, pareto_frontier, release_event_lag, release_event_series,
)


def model(slug, score, cost, country="us", release="2025-01-01", **extra):
    return {"slug": slug, "name": slug, "country": country, "intelligence": score,
            "cost_per_task": cost, "release_date": release, "estimated": False, **extra}


def frontier(*models):
    return pareto_frontier(normalize_records(models))


class AreaTests(unittest.TestCase):
    def test_known_analytic_example(self):
        us = frontier(model("u", 60, 10))
        cn = frontier(model("c", 55, 1, "cn"))
        self.assertAlmostEqual(area_score(us, 1, 100, 40), 10)
        self.assertAlmostEqual(area_score(cn, 1, 100, 40), 15)
        self.assertEqual(frontier_relation(us, cn, 1, 100, 40), "crossing")

    def test_exact_multiple_steps_and_boundary(self):
        models = frontier(model("cheap", 40, 1), model("strong", 60, 10), model("at_end", 100, 100))
        self.assertAlmostEqual(area_score(models, 1, 100, 20), 30)
        self.assertAlmostEqual(area_score(models, 0.1, 100, 20), 20)

    def test_dominated_invariance(self):
        basic = frontier(model("a", 40, 1), model("b", 60, 10))
        augmented = frontier(model("a", 40, 1), model("b", 60, 10), model("dominated", 30, 5))
        self.assertEqual(area_score(basic, .01, 100, 20), area_score(augmented, .01, 100, 20))
        self.assertEqual([m["slug"] for m in augmented], ["a", "b"])

    def test_lower_cost_monotonicity(self):
        expensive = frontier(model("a", 50, 10))
        cheap = frontier(model("a", 50, 1))
        self.assertGreater(area_score(cheap, .01, 100, 20), area_score(expensive, .01, 100, 20))

    def test_missing_is_not_below_floor(self):
        self.assertIsNone(country_area_summary([], [], .01, 10, 30)["area"])
        models = normalize_records([model("a", 20, 1)])
        summary = country_area_summary(models, pareto_frontier(models), .01, 10, 30)
        self.assertEqual(summary["area"], 0)
        self.assertEqual(summary["status"], "below_floor")

    def test_clipping_can_remove_raw_advantage(self):
        us = frontier(model("u", 20, 1))
        cn = frontier(model("c", 10, 1, "cn"))
        self.assertEqual(frontier_relation(us, cn, .01, 10), "us_dominates")
        self.assertEqual(frontier_relation(us, cn, .01, 10, 30), "equal")


class LagTests(unittest.TestCase):
    def test_release_event_bracket_and_same_day_grouping(self):
        models = normalize_records([
            model("a", 10, 1, release="2026-08-31"),
            model("b", 15, 1, release="2026-09-02"),
            model("c", 20, 1, release="2026-09-02"),
        ])
        events = release_event_series(models, lambda rows: max(row["_score"] for row in rows))
        self.assertEqual(len(events), 2)
        lag = release_event_lag("2026-10-07", 15, events)
        self.assertEqual(lag["status"], "between_release_events")
        self.assertEqual((lag["lag_min_days"], lag["lag_max_days"]), (35, 37))

    def test_release_event_exact_match_extends_to_next_change_or_snapshot(self):
        events = [{"date": "2026-08-31", "value": 10}, {"date": "2026-09-02", "value": 20}]
        lag = release_event_lag("2026-10-07", 10, events)
        self.assertEqual(lag["equivalent_us_date_end"], "2026-09-01")
        self.assertEqual((lag["lag_min_days"], lag["lag_max_days"]), (36, 37))
        lag = release_event_lag("2026-10-07", 20, events)
        self.assertEqual(lag["lag_min_days"], 0)

    def test_june_july_bracket(self):
        lag = lag_bracket("2026-10", 15, [{"month": "2026-06", "area": 10}, {"month": "2026-07", "area": 20}])
        self.assertEqual(lag["status"], "between_months")
        self.assertEqual((lag["lag_min_months"], lag["lag_max_months"]), (3, 4))

    def test_exact_plateau(self):
        history = [{"month": "2026-04", "area": 5}] + [{"month": f"2026-{m:02d}", "area": 10} for m in (5, 6, 7)]
        history.append({"month": "2026-08", "area": 20})
        lag = lag_bracket("2026-10", 10, history)
        self.assertEqual(lag["status"], "plateau_match")
        self.assertEqual((lag["lag_min_months"], lag["lag_max_months"]), (3, 5))

    def test_missing_zero_ahead_and_left_censoring(self):
        history = [{"month": "2026-06", "area": 10}, {"month": "2026-07", "area": 20}]
        self.assertEqual(lag_bracket("2026-10", None, history)["status"], "missing_china")
        self.assertEqual(lag_bracket("2026-10", 0, history)["status"], "no_above_floor_coverage")
        self.assertEqual(lag_bracket("2026-10", 30, history)["status"], "ahead_of_observed_us")
        self.assertEqual(lag_bracket("2026-10", 10, [{"month": "2026-06", "area": None}])["status"], "missing_us")
        lag = lag_bracket("2026-10", 5, history)
        self.assertEqual(lag["status"], "before_observation_window")
        self.assertEqual(lag["lag_min_months"], 4)
        self.assertTrue(lag["lower_bound_is_strict"])

    def test_nonmonotonic_history_is_rejected(self):
        lag = lag_bracket("2026-10", 15, [{"month": "2026-06", "area": 20}, {"month": "2026-07", "area": 10}])
        self.assertEqual(lag["status"], "nonmonotonic_us_series")


class AnalysisTests(unittest.TestCase):
    def test_peaks_independent_of_cost_and_policy_filters(self):
        records = [
            model("us-priced", 40, 1),
            model("us-no-price", 60, None),
            model("us-estimate", 70, .1, estimated=True),
            model("cn", 35, .1, "cn", deprecated=True),
            model("future", 100, .01, release="2026-10-08"),
            model("undated", 100, .01, release=None),
            model("zero-cost", 100, 0),
            model("nonfinite", math.inf, .1),
        ]
        result = analyze(records)
        self.assertEqual(len(result["scenarios"]), 24)
        self.assertEqual(len(result["scenarios"][0]["series"]), 22)
        peaks = result["peak_series"]["measured"][-1]
        self.assertEqual(peaks["countries"]["us"]["score"], 100)  # Zero-cost model remains valid for peak capability.
        measured = next(s for s in result["scenarios"] if s["id"] == "measured_b0.01-10_f30")
        estimated = next(s for s in result["scenarios"] if s["id"] == "including_estimated_b0.01-10_f30")
        self.assertAlmostEqual(measured["latest"]["countries"]["us"]["area"], 10 / 3)
        self.assertGreater(estimated["latest"]["countries"]["us"]["area"], measured["latest"]["countries"]["us"]["area"])
        self.assertEqual(measured["latest"]["countries"]["cn"]["deprecated_costed_model_count"], 1)
        self.assertTrue(measured["latest"]["partial"])
        self.assertEqual(measured["latest"]["cutoff_date"], "2026-10-07")

    def test_missing_early_months_and_cohort_monotonicity(self):
        result = analyze([model("u", 40, 1, release="2025-03-02"), model("c", 30, 1, "cn", "2025-04-01")])
        scenario = result["scenarios"][0]
        self.assertIsNone(scenario["series"][0]["countries"]["us"]["area"])
        values = [point["countries"]["us"]["area"] for point in scenario["series"] if point["countries"]["us"]["area"] is not None]
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":
    unittest.main()
