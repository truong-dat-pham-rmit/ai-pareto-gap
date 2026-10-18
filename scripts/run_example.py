"""Run a self-contained, explicitly synthetic demonstration of both methods."""

import argparse
import json
from pathlib import Path

from analyze_frontiers import (
    area_score, eligible_cost_models, eligible_score_models,
    month_cutoffs, normalize_records, pareto_frontier,
)
from analyze_slopes import slope_area_score, target_crossings


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/synthetic-example.json")
    args = parser.parse_args()
    models = normalize_records(json.loads((ROOT / "examples/models-synthetic.json").read_text(encoding="utf-8")))
    result = {
        "metadata": {
            "source": "Invented synthetic models; not Artificial Analysis observations",
            "purpose": "Demonstrate the metric and interpolation assumptions",
            "snapshot_date": "2026-10-07", "analysis_type": "synthetic_release_cohorts",
        },
        "scenarios": [],
    }
    print("SYNTHETIC EXAMPLE: invented models, not empirical country findings.")
    print("Budget: $0.01-$10/task. Positive G favors the synthetic US cohort.")
    for floor in (20, 30, 40):
        scenario = {"floor": floor, "score_policy": "measured", "budget_min": .01, "budget_max": 10, "series": []}
        us_history = []
        for cutoff in month_cutoffs("2026-03"):
            countries = {}
            for country in ("us", "cn"):
                curve = pareto_frontier(eligible_cost_models(eligible_score_models(models, country, cutoff["cutoff_date"])))
                countries[country] = {
                    "staircase_area": area_score(curve, .01, 10, floor) if curve else None,
                    "slope_area": slope_area_score(curve, .01, 10, floor) if curve else None,
                }
            us, cn = countries["us"], countries["cn"]
            us_history.append({"at": cutoff["month"], "value": us["slope_area"]})
            row = {**cutoff, "countries": countries,
                   "staircase_G": us["staircase_area"] - cn["staircase_area"],
                   "slope_G": us["slope_area"] - cn["slope_area"],
                   "monthly_lag": target_crossings(cutoff["month"], cn["slope_area"], us_history, "months")}
            scenario["series"].append(row)
            if floor == 30:
                print(f"{cutoff['month']}  staircase G {row['staircase_G']:+.3f}  log-linear G {row['slope_G']:+.3f}")
        result["scenarios"].append(scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
