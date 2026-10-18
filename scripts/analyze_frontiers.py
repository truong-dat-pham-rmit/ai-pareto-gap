"""Compare dated US/Chinese model cohorts using exact log-budget frontier areas.

This is a retrospective reconstruction at fixed present-day prices and scores,
not a reconstruction of prices or model availability as observed historically.
Only Python's standard library is required.
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


SNAPSHOT = date(2026, 10, 7)
FIRST_MONTH = "2025-01"
FLOORS = (0.0, 20.0, 30.0, 40.0)
BUDGETS = ((0.01, 10.0), (0.01, 1.0), (0.1, 10.0))
COUNTRIES = ("us", "cn")
POLICIES = ("measured", "including_estimated")
VALID_POLICIES = (*POLICIES, "api_published")
TOLERANCE = 1e-9


def validate_policies(policies):
    """Require named, distinct policies rather than silently inventing a filter."""
    if isinstance(policies, str):
        raise ValueError("Policies must be a sequence of policy names")
    policies = tuple(policies)
    if not policies or len(set(policies)) != len(policies):
        raise ValueError("Supply at least one distinct score policy")
    if any(policy not in VALID_POLICIES for policy in policies):
        raise ValueError(f"Score policies must be chosen from {VALID_POLICIES}")
    return policies


def finite_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def month_index(month):
    year, number = map(int, month.split("-"))
    date(year, number, 1)  # Reject invalid month labels instead of rolling them forward.
    return year * 12 + number - 1


def month_cutoffs(first_month=FIRST_MONTH, snapshot=SNAPSHOT):
    for index in range(month_index(first_month), month_index(snapshot.strftime("%Y-%m")) + 1):
        year, month0 = divmod(index, 12)
        month = month0 + 1
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        yield {
            "month": f"{year:04d}-{month:02d}",
            "cutoff_date": min(month_end, snapshot).isoformat(),
            "partial": snapshot < month_end,
        }


def normalize_records(records):
    normalized = []
    for index, original in enumerate(records):
        record = dict(original)
        record["country"] = str(record.get("country") or "").lower()
        record["slug"] = record.get("slug") or f"row-{index}"
        record["name"] = record.get("name") or record["slug"]
        record["_release"] = parse_date(record.get("release_date"))
        record["_score"] = finite_number(record.get("intelligence"))
        record["_cost"] = finite_number(record.get("cost_per_task"))
        estimate = record.get("estimated")
        record["estimated"] = estimate if isinstance(estimate, bool) else None
        record["deprecated"] = record.get("deprecated") is True
        normalized.append(record)
    return normalized


def eligible_score_models(records, country, cutoff, policy="measured"):
    if policy not in VALID_POLICIES:
        raise ValueError(f"Unknown score policy: {policy}")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    return [
        model for model in records
        if model["country"] == country
        and model["_release"] is not None and model["_release"] <= cutoff
        and model["_score"] is not None
        and (policy != "measured" or model["estimated"] is False)
    ]


def eligible_cost_models(score_models):
    return [model for model in score_models if model["_cost"] is not None and model["_cost"] > 0]


def pareto_frontier(models):
    """One deterministic representative per improving price/score point."""
    ordered = sorted(models, key=lambda model: (model["_cost"], -model["_score"], model["slug"]))
    result = []
    best_score = -math.inf
    for model in ordered:
        if model["_score"] > best_score:
            result.append(model)
            best_score = model["_score"]
    return result


def model_view(model):
    return {
        key: model.get(key) for key in (
            "slug", "name", "country", "creator", "release_date", "intelligence",
            "estimated", "cost_per_task", "blended_price", "deprecated", "source_url",
        )
    }


def frontier_at(frontier, budget):
    best = None
    for model in frontier:
        if model["_cost"] > budget:
            break
        best = model
    return best


def log_budget_segments(frontier, budget_min, budget_max, floor):
    if not 0 < budget_min < budget_max:
        raise ValueError("Budget bounds must satisfy 0 < minimum < maximum")
    boundaries = sorted({budget_min, budget_max} | {
        model["_cost"] for model in frontier if budget_min < model["_cost"] < budget_max
    })
    total_log_width = math.log(budget_max / budget_min)
    segments = []
    for left, right in zip(boundaries, boundaries[1:]):
        model = frontier_at(frontier, left)
        score = model["_score"] if model is not None else None
        utility = max(score - floor, 0.0) if score is not None else 0.0
        weight = math.log(right / left) / total_log_width
        segments.append({
            "budget_from": left,
            "budget_to": right,
            "model_slug": model["slug"] if model is not None else None,
            "intelligence": score,
            "above_floor": utility,
            "log_budget_weight": weight,
            "area_contribution": utility * weight,
        })
    return segments


def area_score(frontier, budget_min, budget_max, floor):
    """Exact normalized integral; callers distinguish missing data from zero."""
    return math.fsum(segment["area_contribution"] for segment in log_budget_segments(
        frontier, budget_min, budget_max, floor
    ))


def frontier_relation(us_frontier, cn_frontier, budget_min=None, budget_max=None, floor=None):
    """Compare all steps and endpoints over the specified closed budget interval."""
    if not us_frontier or not cn_frontier:
        return "unavailable"
    boundaries = {model["_cost"] for model in us_frontier + cn_frontier}
    if budget_min is not None:
        boundaries = {point for point in boundaries if budget_min <= point <= budget_max}
        boundaries.update((budget_min, budget_max))
    signs = set()
    for budget in sorted(boundaries):
        us = frontier_at(us_frontier, budget)
        cn = frontier_at(cn_frontier, budget)
        us_score = us["_score"] if us is not None else -math.inf
        cn_score = cn["_score"] if cn is not None else -math.inf
        if floor is not None:
            us_score = max(us_score - floor, 0.0)
            cn_score = max(cn_score - floor, 0.0)
        if us_score > cn_score:
            signs.add(1)
        elif cn_score > us_score:
            signs.add(-1)
    if signs == {1, -1}:
        return "crossing"
    if signs == {1}:
        return "us_dominates"
    if signs == {-1}:
        return "cn_dominates"
    return "equal"


def peak_summary(score_models):
    if not score_models:
        return {"score": None, "models": [], "eligible_model_count": 0}
    score = max(model["_score"] for model in score_models)
    return {
        "score": score,
        "models": [model_view(model) for model in score_models if model["_score"] == score],
        "eligible_model_count": len(score_models),
    }


def country_area_summary(score_models, frontier, budget_min, budget_max, floor):
    cost_models = eligible_cost_models(score_models)
    summary = {
        "eligible_scored_model_count": len(score_models),
        "eligible_costed_model_count": len(cost_models),
        "deprecated_costed_model_count": sum(model["deprecated"] for model in cost_models),
        "estimated_costed_model_count": sum(model["estimated"] is True for model in cost_models),
        "unknown_estimate_status_costed_model_count": sum(model["estimated"] is None for model in cost_models),
        "frontier_model_count": len(frontier),
    }
    if not score_models:
        summary.update(status="no_eligible_scored_models", area=None)
    elif not cost_models:
        summary.update(status="no_eligible_costed_models", area=None)
    else:
        area = area_score(frontier, budget_min, budget_max, floor)
        affordable = frontier_at(frontier, budget_max)
        if area > 0:
            status = "available"
        elif affordable is None:
            status = "outside_budget"
        elif affordable["_score"] <= floor:
            status = "below_floor"
        else:
            status = "zero_width_above_floor"  # An improvement precisely at the right endpoint.
        summary.update(status=status, area=area)
    return summary


def lag_bracket(target_month, target_area, us_history, tolerance=TOLERANCE):
    """Find monthly US area equivalents without inventing interpolation in time.

    us_history is an iterable of {month, area}; missing observations are omitted
    from matching and retained as a count. Bounds use calendar month labels.
    """
    base = {
        "target_month": target_month, "target_area": target_area,
        "lag_min_months": None, "lag_max_months": None,
        "equivalent_us_month_start": None, "equivalent_us_month_end": None,
    }
    if target_area is None:
        return {**base, "status": "missing_china"}
    if target_area <= tolerance:
        return {**base, "status": "no_above_floor_coverage"}
    all_history = sorted(
        [point for point in us_history if point["month"] <= target_month],
        key=lambda point: point["month"],
    )
    history = [point for point in all_history if finite_number(point.get("area")) is not None]
    base["us_observation_count"] = len(history)
    base["us_missing_month_count"] = len(all_history) - len(history)
    if not history:
        return {**base, "status": "missing_us"}
    if any(right["area"] < left["area"] - tolerance for left, right in zip(history, history[1:])):
        return {**base, "status": "nonmonotonic_us_series"}
    equals = [point for point in history if abs(point["area"] - target_area) <= tolerance]
    if equals:
        start, end = equals[0], equals[-1]
        status = "exact_month" if len(equals) == 1 else "plateau_match"
    elif target_area > history[-1]["area"] + tolerance:
        return {**base, "status": "ahead_of_observed_us", "latest_us_area": history[-1]["area"]}
    elif target_area < history[0]["area"] - tolerance:
        return {
            **base, "status": "before_observation_window",
            "lag_min_months": month_index(target_month) - month_index(history[0]["month"]),
            "lower_bound_is_strict": True,
            "first_observed_us_month": history[0]["month"],
            "first_observed_us_area": history[0]["area"],
        }
    else:
        start = max((point for point in history if point["area"] < target_area), key=lambda p: p["month"])
        end = min((point for point in history if point["area"] > target_area), key=lambda p: p["month"])
        status = "between_months"
    return {
        **base, "status": status,
        "equivalent_us_month_start": start["month"],
        "equivalent_us_month_end": end["month"],
        "lag_min_months": month_index(target_month) - month_index(end["month"]),
        "lag_max_months": month_index(target_month) - month_index(start["month"]),
        "us_area_at_start": start["area"],
        "us_area_at_end": end["area"],
    }


def release_event_series(models, measure):
    """Evaluate whole same-day cohorts together; never sequence configurations."""
    return [
        {"date": event_date.isoformat(), "value": measure([model for model in models if model["_release"] <= event_date])}
        for event_date in sorted({model["_release"] for model in models})
    ]


def release_event_lag(target_date, target_value, events, tolerance=TOLERANCE):
    if isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    base = {
        "target_date": target_date.isoformat(), "target_value": target_value,
        "lag_min_days": None, "lag_max_days": None,
        "equivalent_us_date_start": None, "equivalent_us_date_end": None,
    }
    if target_value is None:
        return {**base, "status": "missing_china"}
    if target_value <= tolerance:
        return {**base, "status": "no_positive_target_value"}
    history = sorted(
        [point for point in events if point["date"] <= target_date.isoformat() and finite_number(point.get("value")) is not None],
        key=lambda point: point["date"],
    )
    base["us_release_event_count"] = len(history)
    if not history:
        return {**base, "status": "missing_us"}
    if any(right["value"] < left["value"] - tolerance for left, right in zip(history, history[1:])):
        return {**base, "status": "nonmonotonic_us_series"}
    equals = [point for point in history if abs(point["value"] - target_value) <= tolerance]
    if equals:
        start = equals[0]
        later_events = [point for point in history if point["date"] > equals[-1]["date"]]
        valid_through = date.fromisoformat(later_events[0]["date"]) - timedelta(days=1) if later_events else target_date
        return {
            **base, "status": "exact_value_interval",
            "equivalent_us_date_start": start["date"],
            "equivalent_us_date_end": valid_through.isoformat(),
            "last_equal_release_event_date": equals[-1]["date"],
            "lag_min_days": (target_date - valid_through).days,
            "lag_max_days": (target_date - date.fromisoformat(start["date"])).days,
            "us_value_at_start": start["value"], "us_value_at_end": start["value"],
        }
    if target_value > history[-1]["value"] + tolerance:
        return {**base, "status": "ahead_of_observed_us", "latest_us_value": history[-1]["value"]}
    if target_value < history[0]["value"] - tolerance:
        return {
            **base, "status": "before_observation_window", "lower_bound_is_strict": True,
            "lag_min_days": (target_date - date.fromisoformat(history[0]["date"])).days,
            "first_observed_us_date": history[0]["date"], "first_observed_us_value": history[0]["value"],
        }
    start = max((point for point in history if point["value"] < target_value), key=lambda point: point["date"])
    end = min((point for point in history if point["value"] > target_value), key=lambda point: point["date"])
    return {
        **base, "status": "between_release_events",
        "equivalent_us_date_start": start["date"], "equivalent_us_date_end": end["date"],
        "lag_min_days": (target_date - date.fromisoformat(end["date"])).days,
        "lag_max_days": (target_date - date.fromisoformat(start["date"])).days,
        "us_value_at_start": start["value"], "us_value_at_end": end["value"],
    }


def audit_records(records, snapshot, policies=POLICIES):
    country_counts = {}
    missingness = {}
    exclusions = []
    for country in COUNTRIES:
        members = [model for model in records if model["country"] == country]
        issues = Counter()
        for model in members:
            reasons = []
            if model["_release"] is None:
                reasons.append("missing_or_invalid_release_date")
            elif model["_release"] > snapshot:
                reasons.append("future_release_date")
            if model["_score"] is None:
                reasons.append("missing_or_nonfinite_intelligence")
            if model["_cost"] is None:
                reasons.append("missing_or_nonfinite_task_cost")
            elif model["_cost"] <= 0:
                reasons.append("nonpositive_task_cost")
            if model["estimated"] is True:
                reasons.append("estimated_score_excluded_from_measured")
            elif model["estimated"] is None:
                reasons.append("unknown_estimate_status_excluded_from_measured")
            issues.update(reasons)
            if reasons:
                exclusions.append({"slug": model["slug"], "name": model["name"], "country": country, "reasons": reasons})
        country_counts[country] = {
            "total_records": len(members),
            "released_by_snapshot": sum(model["_release"] is not None and model["_release"] <= snapshot for model in members),
            "deprecated_records": sum(model["deprecated"] for model in members),
            "estimated_records": sum(model["estimated"] is True for model in members),
            "unknown_estimate_status_records": sum(model["estimated"] is None for model in members),
            "by_policy": {
                policy: {
                    "scored_models": len(eligible_score_models(records, country, snapshot, policy)),
                    "scored_and_costed_models": len(eligible_cost_models(eligible_score_models(records, country, snapshot, policy))),
                } for policy in policies
            },
        }
        missingness[country] = dict(issues)
    return country_counts, missingness, exclusions


def analyze(records, snapshot=SNAPSHOT, first_month=FIRST_MONTH,
            index_version="4.3.2", policies=POLICIES):
    policies = validate_policies(policies)
    records = normalize_records(records)
    cutoffs = list(month_cutoffs(first_month, snapshot))
    if not cutoffs:
        raise ValueError("The first month must not be after the snapshot")
    counts, missingness, exclusions = audit_records(records, snapshot, policies)
    result = {
        "metadata": {
            "snapshot_date": snapshot.isoformat(),
            "first_month": first_month,
            "intelligence_index_version": index_version,
            "analysis_type": "release_cohorts_at_fixed_snapshot_scores_and_prices",
            "area_units": "average_above_floor_intelligence_index_points",
            "gap_sign": "positive means US advantage; negative means China advantage",
            "lag_units": "calendar_month_bins",
            "caveats": [
                "Current scores and task costs are applied retrospectively to release cohorts; these are not historical transaction prices.",
                "Catalog omissions, missing scores/prices/dates, and survivorship limit historical coverage.",
                "Deprecated entries are retained to reconstruct released-model cohorts, without asserting historical or current purchasability.",
                "The measured policy requires an explicit false estimate flag. API-published and estimated-inclusive policies admit published scores without claiming measured-only status.",
                "Missing and nonpositive task costs are excluded from areas; peak capability does not require cost data.",
                f"The final cohort ends on {snapshot.isoformat()}; monthly lags use calendar labels, not precise elapsed months.",
                "Area equivalence is scalar equivalence and does not establish full Pareto dominance.",
                "Equal weight per log-budget interval and per above-floor index point is a chosen convention, not measured user demand.",
                "Origin is the normalized developer country and does not identify the hosting jurisdiction.",
                "Models are counted as separate configurations when represented as separate input rows.",
            ],
        },
        "settings": {
            "floors": list(FLOORS),
            "budgets": [{"minimum": low, "maximum": high, "primary": index == 0} for index, (low, high) in enumerate(BUDGETS)],
            "score_policies": list(policies),
            "primary_score_policy": "measured" if "measured" in policies else policies[0],
            "lag_numerical_tolerance": TOLERANCE,
            "country_codes": {"us": "United States", "cn": "China"},
            "frontier_endpoint_convention": "affordable when price <= budget; integrals ignore isolated endpoints",
        },
        "snapshot_country_counts": counts,
        "missingness_by_country": missingness,
        "measured_task_cost_coverage": {},
        "exclusions": exclusions,
        "other_country_record_count": sum(model["country"] not in COUNTRIES for model in records),
        "peak_series": {},
        "scenarios": [],
    }
    for country in COUNTRIES:
        scored = eligible_score_models(records, country, snapshot, "measured")
        costed = eligible_cost_models(scored)
        missing_cost = sorted(
            [model for model in scored if model["_cost"] is None or model["_cost"] <= 0],
            key=lambda model: -model["_score"],
        )
        result["measured_task_cost_coverage"][country] = {
            "earliest_positive_cost_release_date": min(model["_release"] for model in costed).isoformat() if costed else None,
            "missing_or_nonpositive_cost_models": [model_view(model) for model in missing_cost],
            "highest_missing_or_nonpositive_cost_score": missing_cost[0]["_score"] if missing_cost else None,
        }
    for policy in policies:
        cohorts = []
        us_peak_history = []
        result["peak_series"][policy] = []
        for cutoff in cutoffs:
            scores = {country: eligible_score_models(records, country, cutoff["cutoff_date"], policy) for country in COUNTRIES}
            frontiers = {country: pareto_frontier(eligible_cost_models(scores[country])) for country in COUNTRIES}
            cohorts.append((cutoff, scores, frontiers))
            peaks = {country: peak_summary(scores[country]) for country in COUNTRIES}
            us_peak, cn_peak = peaks["us"]["score"], peaks["cn"]["score"]
            us_peak_history.append({"month": cutoff["month"], "area": us_peak})
            peak_lag = {
                key.replace("area", "score"): value
                for key, value in lag_bracket(cutoff["month"], cn_peak, us_peak_history).items()
            }
            result["peak_series"][policy].append({
                **cutoff, "countries": peaks,
                "gap_us_minus_cn": us_peak - cn_peak if us_peak is not None and cn_peak is not None else None,
                "lag": peak_lag,
            })
        latest_us_scored = cohorts[-1][1]["us"]
        peak_events = release_event_series(latest_us_scored, lambda models: max(model["_score"] for model in models))
        latest_peak = result["peak_series"][policy][-1]
        latest_peak["release_event_lag"] = release_event_lag(snapshot, latest_peak["countries"]["cn"]["score"], peak_events)
        for budget_index, (budget_min, budget_max) in enumerate(BUDGETS):
            for floor in FLOORS:
                scenario = {
                    "id": f"{policy}_b{budget_min:g}-{budget_max:g}_f{floor:g}",
                    "score_policy": policy, "floor": floor,
                    "budget_min": budget_min, "budget_max": budget_max,
                    "primary_budget": budget_index == 0,
                    "series": [],
                }
                us_history = []
                for cutoff, scores, frontiers in cohorts:
                    countries = {
                        country: country_area_summary(scores[country], frontiers[country], budget_min, budget_max, floor)
                        for country in COUNTRIES
                    }
                    us_area, cn_area = countries["us"]["area"], countries["cn"]["area"]
                    us_history.append({"month": cutoff["month"], "area": us_area})
                    scenario["series"].append({
                        **cutoff, "countries": countries,
                        "gap_us_minus_cn": us_area - cn_area if us_area is not None and cn_area is not None else None,
                        "frontier_relation": {
                            "full_raw": frontier_relation(frontiers["us"], frontiers["cn"]),
                            "selected_budget_raw": frontier_relation(frontiers["us"], frontiers["cn"], budget_min, budget_max),
                            "selected_budget_clipped": frontier_relation(frontiers["us"], frontiers["cn"], budget_min, budget_max, floor),
                        },
                        "lag": lag_bracket(cutoff["month"], cn_area, us_history),
                    })
                latest_frontiers = cohorts[-1][2]
                scenario["latest"] = {
                    **scenario["series"][-1],
                    "frontiers": {
                        country: {
                            "models": [model_view(model) for model in latest_frontiers[country]],
                            "segments": log_budget_segments(latest_frontiers[country], budget_min, budget_max, floor),
                        } for country in COUNTRIES
                    },
                }
                area_events = release_event_series(
                    eligible_cost_models(latest_us_scored),
                    lambda models: area_score(pareto_frontier(models), budget_min, budget_max, floor),
                )
                scenario["latest"]["release_event_lag"] = release_event_lag(
                    snapshot, scenario["latest"]["countries"]["cn"]["area"], area_events
                )
                for country in COUNTRIES:
                    values = [point["countries"][country]["area"] for point in scenario["series"] if point["countries"][country]["area"] is not None]
                    if any(right < left - TOLERANCE for left, right in zip(values, values[1:])):
                        raise AssertionError(f"Nonmonotonic fixed-price release cohort: {scenario['id']} {country}")
                result["scenarios"].append(scenario)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/models-2026-10-07.json"))
    parser.add_argument("--output", type=Path, default=Path("analysis/results.json"))
    parser.add_argument("--snapshot", type=date.fromisoformat, default=SNAPSHOT,
                        help="Snapshot cutoff date, YYYY-MM-DD")
    parser.add_argument("--first-month", default=FIRST_MONTH, help="First release cohort, YYYY-MM")
    parser.add_argument("--index-version", default="4.3.2", help="Compatible Intelligence Index version")
    parser.add_argument("--policies", nargs="+", choices=VALID_POLICIES, default=POLICIES)
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Input must be a JSON list of normalized model records")
    result = analyze(records, snapshot=args.snapshot, first_month=args.first_month,
                     index_version=args.index_version, policies=args.policies)
    result["metadata"]["input_file"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "input_records": len(records),
        "scenarios": len(result["scenarios"]), "months_per_scenario": len(result["scenarios"][0]["series"]),
        "snapshot_country_counts": result["snapshot_country_counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
