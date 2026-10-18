"""Log-linear interpolation sensitivity for the fixed-snapshot AA comparison.

Join consecutive nondominated observations in (log cost, raw intelligence).
These lines are hypothetical operating points, not additional AA observations.
Run with Python 3; uses only the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path

from analyze_frontiers import (
    BUDGETS, COUNTRIES, FIRST_MONTH, FLOORS, POLICIES, SNAPSHOT, TOLERANCE, VALID_POLICIES,
    area_score, eligible_cost_models, eligible_score_models, model_view,
    month_cutoffs, month_index, normalize_records, pareto_frontier,
    release_event_series, validate_policies,
)


def interpolated_score(frontier, budget):
    """No lower extrapolation; the best option remains usable above its cost."""
    if not frontier or budget < frontier[0]["_cost"]:
        return None
    for left, right in zip(frontier, frontier[1:]):
        if budget <= right["_cost"]:
            weight = math.log(budget / left["_cost"]) / math.log(right["_cost"] / left["_cost"])
            return left["_score"] + weight * (right["_score"] - left["_score"])
    return frontier[-1]["_score"]


def positive_linear_integral(width, left, right):
    """Exact integral of max(linear function, 0) over a log-budget interval."""
    if left >= 0 and right >= 0:
        return width * (left + right) / 2
    if left <= 0 and right <= 0:
        return 0.0
    positive_height = max(left, right)
    return width * positive_height ** 2 / (2 * abs(right - left))


def slope_segments(frontier, budget_min, budget_max, floor):
    if not 0 < budget_min < budget_max:
        raise ValueError("Budget bounds must satisfy 0 < minimum < maximum")
    bounds = sorted({budget_min, budget_max} | {
        model["_cost"] for model in frontier if budget_min < model["_cost"] < budget_max
    })
    normalizer = math.log(budget_max / budget_min)
    segments = []
    for left, right in zip(bounds, bounds[1:]):
        low_score = interpolated_score(frontier, left)
        high_score = interpolated_score(frontier, right) if low_score is not None else None
        # The interval below the cheapest point contributes zero, even if its
        # right endpoint is the cheapest model. An isolated endpoint has no area.
        value = 0.0 if low_score is None else positive_linear_integral(
            math.log(right / left), low_score - floor, high_score - floor
        ) / normalizer
        segments.append({
            "budget_from": left, "budget_to": right,
            "intelligence_from": low_score, "intelligence_to": high_score,
            "area_contribution": value,
        })
    return segments


def slope_area_score(frontier, budget_min, budget_max, floor):
    return math.fsum(s["area_contribution"] for s in slope_segments(frontier, budget_min, budget_max, floor))


def decline_audit(history):
    valid = [row for row in history if row["value"] is not None]
    return [
        {"from": left["at"], "to": right["at"], "before": left["value"],
         "after": right["value"], "change": right["value"] - left["value"]}
        for left, right in zip(valid, valid[1:])
        if right["value"] < left["value"] - TOLERANCE
    ]


def target_crossings(target_at, target_value, history, unit):
    """Locate target-specific crossings without assuming monotonic history.

    A unique below-to-above monthly transition gives a month bracket. Multiple
    crossings, matches, and left censoring retain explicit statuses. A target
    above the current US value is ahead, even if a prior curve was above it.
    No interpolation in calendar time and no running-maximum repair are used.
    """
    if unit not in ("months", "days"):
        raise ValueError("unit must be months or days")
    result = {"target_at": target_at, "target_value": target_value, "unit": unit,
              "lag_min": None, "lag_max": None}
    if target_value is None:
        return {**result, "status": "missing_china"}
    if target_value <= TOLERANCE:
        return {**result, "status": "no_above_floor_coverage"}
    observations = [p for p in history if p["at"] <= target_at]
    valid = [p for p in observations if p["value"] is not None]
    if not valid:
        return {**result, "status": "missing_us"}

    def elapsed(at):
        if unit == "months":
            return month_index(target_at) - month_index(at)
        return (date.fromisoformat(target_at) - date.fromisoformat(at)).days

    def sign(value):
        return 1 if value > target_value + TOLERANCE else -1 if value < target_value - TOLERANCE else 0

    upward, downward = [], []
    for previous, current in zip(valid, valid[1:]):
        if sign(previous["value"]) < 0 and sign(current["value"]) >= 0:
            upward.append({"before": previous["at"], "at_or_above": current["at"],
                           "value_before": previous["value"], "value_after": current["value"]})
        elif sign(previous["value"]) >= 0 and sign(current["value"]) < 0:
            downward.append({"before": previous["at"], "below": current["at"]})
    equals = [p["at"] for p in valid if sign(p["value"]) == 0]
    attained = [p for p in valid if sign(p["value"]) >= 0]
    first_at = attained[0]["at"] if attained else None
    result.update(
        history_has_decreases=bool(decline_audit(valid)),
        missing_observations=sum(p["value"] is None for p in observations),
        upward_crossings=upward, downward_crossings=downward,
        equal_observations=equals, latest_us_value=valid[-1]["value"],
        first_observed_at_or_above=first_at,
        elapsed_since_first_observed_at_or_above=elapsed(first_at) if first_at else None,
        first_attainment_left_censored=bool(attained and attained[0] is valid[0]),
    )
    if sign(valid[-1]["value"]) < 0:
        return {**result, "status": "ahead_of_us_at_cutoff"}
    if downward or len(upward) > 1:
        return {**result, "status": "multiple_crossings"}
    if equals:
        return {**result, "status": "observed_equal_values",
                "equivalent_us_start": equals[0], "equivalent_us_end": equals[-1],
                "lag_min": elapsed(equals[-1]), "lag_max": elapsed(equals[0])}
    if sign(valid[0]["value"]) > 0:
        return {**result, "status": "before_observation_window",
                "lag_min": elapsed(valid[0]["at"]), "lower_bound_is_strict": True}
    crossing = upward[0]
    return {**result, "status": "unique_crossing",
            "equivalent_us_start": crossing["before"], "equivalent_us_end": crossing["at_or_above"],
            "lag_min": elapsed(crossing["at_or_above"]), "lag_max": elapsed(crossing["before"])}


def analyze_slopes(records, snapshot=SNAPSHOT, first_month=FIRST_MONTH,
                   index_version="4.3.2", policies=POLICIES):
    policies = validate_policies(policies)
    records = normalize_records(records)
    cutoffs = list(month_cutoffs(first_month, snapshot))
    if not cutoffs:
        raise ValueError("The first month must not be after the snapshot")
    result = {
        "metadata": {
            "snapshot_date": snapshot.isoformat(), "first_month": first_month,
            "intelligence_index_version": index_version,
            "analysis_type": "release_cohorts_at_fixed_snapshot_scores_and_prices",
            "interpolation": "adjacent_nondominated_points_linear_in_log_cost_and_raw_intelligence",
            "interpolation_status": "hypothetical_sensitivity_not_measured_operating_points",
            "boundary_rule": "zero coverage below cheapest; flat best observed score above final point",
            "floor_rule": "interpolate raw intelligence first, then clip at capability floor",
            "area_units": "average_above_floor_intelligence_index_points",
            "gap_sign": "positive favors US; negative favors China",
            "lag_rule": "target-specific unique crossings; no interpolation in time or monotonic repair",
            "caveats": [
                "Snapshot scores and costs applied retrospectively; not observed historical prices or availability.",
                f"The final cohort ends on {snapshot.isoformat()}. All comparisons use the same snapshot as the staircase baseline.",
                "Measured-only requires an explicit false estimate flag; API-published admits source scores without claiming the omitted estimate status is known.",
                "Interpolated points are assumptions; missing scores/costs remain excluded, not interpolated as records.",
                "Different reasoning efforts remain separate configurations when AA supplies paired scores and costs.",
                "Adding a measured point below a previous interpolated chord can lower smoothed area.",
                "Month ranges are calendar-label bins, not precise elapsed months. Release-date crossings are separate.",
                "Area equivalence is not full Pareto dominance, an economic productivity estimate, or statistical confidence.",
            ],
        },
        "settings": {"floors": list(FLOORS), "budgets": [list(b) for b in BUDGETS], "policies": list(policies)},
        "scenarios": [],
    }
    for policy in policies:
        cohorts = []
        for cutoff in cutoffs:
            frontiers = {country: pareto_frontier(eligible_cost_models(eligible_score_models(
                records, country, cutoff["cutoff_date"], policy
            ))) for country in COUNTRIES}
            cohorts.append((cutoff, frontiers))
        latest_models = {country: eligible_cost_models(eligible_score_models(
            records, country, snapshot, policy
        )) for country in COUNTRIES}
        for budget_min, budget_max in BUDGETS:
            for floor in FLOORS:
                scenario = {"id": f"{policy}_b{budget_min:g}-{budget_max:g}_f{floor:g}",
                            "score_policy": policy, "floor": floor,
                            "budget_min": budget_min, "budget_max": budget_max, "series": []}
                histories = {country: [] for country in COUNTRIES}
                event_histories = {country: [
                    {"at": p["date"], "value": p["value"]} for p in release_event_series(
                        latest_models[country],
                        lambda rows: slope_area_score(pareto_frontier(rows), budget_min, budget_max, floor)
                    )
                ] for country in COUNTRIES}
                for cutoff, frontiers in cohorts:
                    countries = {}
                    for country, frontier in frontiers.items():
                        smooth = slope_area_score(frontier, budget_min, budget_max, floor) if frontier else None
                        step = area_score(frontier, budget_min, budget_max, floor) if frontier else None
                        countries[country] = {"slope_area": smooth, "staircase_area": step,
                                              "interpolation_uplift": smooth - step if smooth is not None else None}
                        histories[country].append({"at": cutoff["month"], "value": smooth})
                        if smooth is not None and smooth < step - TOLERANCE:
                            raise AssertionError("Adjacent interpolation must weakly exceed staircase")
                    us, cn = countries["us"], countries["cn"]
                    comparable = us["slope_area"] is not None and cn["slope_area"] is not None
                    scenario["series"].append({
                        **cutoff, "countries": countries,
                        "slope_G": us["slope_area"] - cn["slope_area"] if comparable else None,
                        "staircase_G": us["staircase_area"] - cn["staircase_area"] if comparable else None,
                        "monthly_lag": target_crossings(cutoff["month"], cn["slope_area"], histories["us"], "months"),
                        "release_event_lag": target_crossings(cutoff["cutoff_date"], cn["slope_area"], event_histories["us"], "days"),
                    })
                scenario["declines"] = {country: {
                    "monthly": decline_audit(histories[country]),
                    "release_events": decline_audit(event_histories[country]),
                } for country in COUNTRIES}
                scenario["latest_frontiers"] = {country: {
                    "models": [model_view(m) for m in cohorts[-1][1][country]],
                    "slope_segments": slope_segments(cohorts[-1][1][country], budget_min, budget_max, floor),
                } for country in COUNTRIES}
                result["scenarios"].append(scenario)
    return result


def format_lag(match):
    if match["status"] == "unique_crossing":
        return f"{match['lag_min']}-{match['lag_max']}"
    return {
        "ahead_of_us_at_cutoff": "China ahead", "no_above_floor_coverage": "N/A: no coverage",
        "multiple_crossings": "ambiguous", "missing_china": "missing China", "missing_us": "missing US",
    }.get(match["status"], match["status"])


def summary_text(result):
    """Describe any supported snapshot without reusing frozen empirical claims."""
    scenarios = result["scenarios"]
    preferred_policy = next((policy for policy in ("measured", "api_published")
                             if any(s["score_policy"] == policy for s in scenarios)),
                            scenarios[0]["score_policy"])
    primary = next((s for s in scenarios if s["score_policy"] == preferred_policy
                    and (s["budget_min"], s["budget_max"], s["floor"]) == (.01, 10, 30)),
                   scenarios[0])
    latest = primary["series"][-1]
    latest_lag = latest["monthly_lag"]
    latest_event = latest["release_event_lag"]

    def number(value):
        return f"{value:.6f}" if value is not None else "N/A"

    version = result["metadata"].get("intelligence_index_version") or "not supplied"
    lines = [
        "ARTIFICIAL ANALYSIS: LOG-LINEAR INTERPOLATION SENSITIVITY",
        f"Source snapshot: {result['metadata']['snapshot_date']}; Intelligence Index version: {version}.",
        "Source: https://artificialanalysis.ai/models/",
        "Methodology: https://artificialanalysis.ai/methodology/intelligence-benchmarking",
        "",
        "MAIN RESULT",
        f"Score policy: {primary['score_policy']}.",
        f"At floor {primary['floor']:g} and USD {primary['budget_min']:g}-{primary['budget_max']:g}/task,",
        f"latest staircase G = {number(latest['staircase_G'])}; log-linear G = {number(latest['slope_G'])}.",
        f"US monthly comparison: {latest_lag.get('equivalent_us_start', '--')} to {latest_lag.get('equivalent_us_end', '--')};",
        f"lag calendar-month bins: {format_lag(latest_lag)}.",
        f"Release crossing status: {latest_event['status']}; first observed at or above",
        f"target: {latest_event.get('first_observed_at_or_above', '--')},",
        f"elapsed days: {latest_event.get('elapsed_since_first_observed_at_or_above', '--')}.",
        "",
        "METHOD",
        "Join consecutive nondominated eligible observations with straight lines in",
        "(log cost, raw intelligence). This assumes unmeasured operating points.",
        "For c0 <= b <= c1: I(b) = I0 + (I1-I0)*ln(b/c0)/ln(c1/c0).",
        "Integrate max(I(b)-floor,0) over log budget, then divide by ln(Bmax/Bmin).",
        "G = A_US - A_China; positive favors US, negative favors China.",
        "Interpolate raw scores BEFORE floor clipping. No capability extrapolation",
        "below the cheapest observation; retain the strongest option above its cost.",
        "Include outside-budget anchors when their segment crosses the budget window.",
        "Cost = average USD per Intelligence Index task, not USD per million tokens.",
        "",
        "Interpretation: same snapshot prices and scores applied to cumulative release",
        "cohorts. This is not reconstructed historical prices or API availability.",
        f"Final cohort ends on {latest['cutoff_date']}; partial month: {latest['partial']}.",
        "Missing/nonpositive task costs are excluded. Missing areas are N/A, not zero.",
        "Measured-only requires explicit false estimate flags; API-published does not",
        "infer whether a score with an omitted estimate flag was measured or estimated.",
        "China/US use the normalized developer-country field. Different efforts remain",
        "separate configurations when the source supplies separate observations.",
        "Peak-only capability comparisons are unchanged by interpolation.",
        "",
        "MONTHLY TABLES: PRIMARY USD 0.01-10/TASK BUDGET",
        "G units: average above-floor Intelligence Index points, not percentages.",
        "Month lags use calendar-label bins; crossing dates are actual release dates.",
        "They do not imply exact equality between the two countries' entire frontiers.",
    ]
    for scenario in scenarios:
        if scenario["score_policy"] != preferred_policy or (scenario["budget_min"], scenario["budget_max"]) != (.01, 10):
            continue
        lines += ["", f"Capability floor {scenario['floor']:g}",
                  "Month     US slope  CN slope    Step G   Slope G   US month bracket   Lag bins       First US crossing"]
        for row in scenario["series"]:
            lag, event = row["monthly_lag"], row["release_event_lag"]
            bracket = f"{lag['equivalent_us_start']}/{lag['equivalent_us_end']}" if lag["status"] == "unique_crossing" else "--"
            crossing = (f"{event['first_observed_at_or_above']} ({event['elapsed_since_first_observed_at_or_above']} days prior)"
                        if event["status"] == "unique_crossing" else "--")
            lines.append(
                f"{row['month']} {number(row['countries']['us']['slope_area']):>9} {number(row['countries']['cn']['slope_area']):>9} "
                f"{number(row['staircase_G']):>9} {number(row['slope_G']):>9}  {bracket:17}  {format_lag(lag):15} {crossing}"
            )
    lines += ["", "LATEST FLOOR-30 BUDGET SENSITIVITY", "Budget/task      Step G   Slope G   Month lag bins    First US crossing"]
    for scenario in scenarios:
        if scenario["score_policy"] == preferred_policy and scenario["floor"] == 30:
            row = scenario["series"][-1]
            lines.append(f"${scenario['budget_min']:g}-${scenario['budget_max']:g}"
                         f"         {number(row['staircase_G']):>9} {number(row['slope_G']):>9}   "
                         f"{format_lag(row['monthly_lag']):16}  {row['release_event_lag'].get('first_observed_at_or_above', '--')}")
    lines += [
        "", "INTERPOLATION AUDIT",
        "The smoothed frontier can fall after a new observation bends an old chord",
        "downward. This is a change in the interpolation estimate, not lost measured",
        "capability. Decline audits for this input are retained in the result JSON.",
        "Each lag is checked for target-specific recrossings. No running maximum is",
        "silently imposed and no linear interpolation in time creates a false date.",
        "A transient earlier US crossing is not presented as a positive Chinese lag",
        "when China is ahead at the cutoff. A near-zero gap after floor clipping",
        "does not establish capability parity. No above-floor Chinese coverage yields",
        "no month lag.",
        "Smoothing can widen or narrow G; it is an explicit modeling assumption.",
        "",
        "FILES AND REPRODUCTION",
        "scripts/analyze_frontiers.py: observed staircase baseline and shared filters.",
        "scripts/analyze_slopes.py: exact log-linear integration and crossing checks.",
        f"{len(scenarios)} scenarios; {len(primary['series'])} monthly cohorts per scenario.",
        "Result JSON retains country areas, gaps, target crossings, decline audits",
        "and frontier segments. Preserve the input and snapshot metadata to reproduce.",
        "python -m unittest discover -s scripts -p \"test_analyze*.py\"",
        "Optional chart: python scripts/plot_slopes.py (requires matplotlib).",
        "",
        "Artificial Analysis supplies observations; interpolation and gap metrics are",
        "derived here. The smoothing scenarios are not measured AA model offerings.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/models-2026-10-07.json"))
    parser.add_argument("--output", type=Path, default=Path("analysis/slope-results.json"))
    parser.add_argument("--summary", type=Path, default=Path("analysis/slope-summary.txt"))
    parser.add_argument("--snapshot", type=date.fromisoformat, default=SNAPSHOT,
                        help="Snapshot cutoff date, YYYY-MM-DD")
    parser.add_argument("--first-month", default=FIRST_MONTH, help="First release cohort, YYYY-MM")
    parser.add_argument("--index-version", default="4.3.2", help="Compatible Intelligence Index version")
    parser.add_argument("--policies", nargs="+", choices=VALID_POLICIES, default=POLICIES)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    records = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Input must contain a JSON list of normalized models")
    result = analyze_slopes(records, snapshot=args.snapshot, first_month=args.first_month,
                            index_version=args.index_version, policies=args.policies)
    result["metadata"].update(input_file=str(args.input), input_sha256=hashlib.sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(summary_text(result), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": str(args.summary), "scenarios": len(result["scenarios"])}))


if __name__ == "__main__":
    main()
