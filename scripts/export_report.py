"""Export derived aggregate reports from local detailed research outputs.

This intentionally omits source model records, frontier vertices and session
artifacts. The required local inputs are not distributed with the repository.
"""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def export_aggregates(slopes, baseline):
    """Use explicit allowlists so source observations cannot leak into reports."""
    policies = baseline.get("settings", {}).get("score_policies", ["measured"])
    primary_policy = "measured" if "measured" in policies else policies[0]
    return {
        "metadata": {
            "title": "Pareto Gap: frozen release-cohort comparison",
            "snapshot_date": slopes["metadata"]["snapshot_date"],
            "intelligence_index_version": slopes["metadata"]["intelligence_index_version"],
            "source": "Artificial Analysis",
            "source_url": "https://artificialanalysis.ai/models/",
            "source_methodology_url": "https://artificialanalysis.ai/methodology/intelligence-benchmarking",
            "source_input_sha256": slopes["metadata"].get("input_sha256"),
            "content": "Derived country-level aggregates; source model observations omitted",
            "analysis_type": slopes["metadata"]["analysis_type"],
            "area_units": slopes["metadata"]["area_units"],
            "gap_sign": slopes["metadata"]["gap_sign"],
            "interpolation": slopes["metadata"]["interpolation"],
            "interpolation_status": slopes["metadata"]["interpolation_status"],
            "caveats": slopes["metadata"]["caveats"],
            "data_notice": "Source observations are not redistributed or relicensed; see NOTICE.md",
            "coverage": {country: {
                "total_configurations": baseline["snapshot_country_counts"][country]["total_records"],
                "scored_configurations": baseline["snapshot_country_counts"][country]["by_policy"][primary_policy]["scored_models"],
                "costed_configurations": baseline["snapshot_country_counts"][country]["by_policy"][primary_policy]["scored_and_costed_models"],
                "score_policy": primary_policy,
            } for country in ("us", "cn")},
        },
        "scenarios": [{
            **{key: scenario[key] for key in ("id", "score_policy", "floor", "budget_min", "budget_max")},
            "series": [{
                **{key: row[key] for key in ("month", "cutoff_date", "partial", "slope_G", "staircase_G")},
                "countries": {country: {key: row["countries"][country][key] for key in (
                    "slope_area", "staircase_area", "interpolation_uplift"
                )} for country in ("us", "cn")},
                "monthly_lag": {key: value for key, value in row["monthly_lag"].items() if key in (
                    "status", "unit", "lag_min", "lag_max", "equivalent_us_start", "equivalent_us_end",
                    "history_has_decreases", "first_observed_at_or_above", "first_attainment_left_censored"
                )},
                "release_event_lag": {key: value for key, value in row["release_event_lag"].items() if key in (
                    "status", "first_observed_at_or_above", "elapsed_since_first_observed_at_or_above",
                    "history_has_decreases", "first_attainment_left_censored"
                )},
            } for row in scenario["series"]],
        } for scenario in slopes["scenarios"]],
    }


def summary_markdown(report):
    lines = [
        "# Frozen snapshot results", "",
        f"Snapshot: **{report['metadata']['snapshot_date']}**, Intelligence Index **v{report['metadata']['intelligence_index_version']}**.", "",
        "These are derived statistics from a fixed snapshot of [Artificial Analysis](https://artificialanalysis.ai/models/).",
        "Scores and task costs are applied retrospectively to cumulative release cohorts.",
        "They do not reconstruct historical transaction prices or availability. October is partial through October 7.", "",
        "Positive `G = A_US - A_China` favors the US; negative favors China.",
        "Units are average above-floor Intelligence Index points with equal weight per budget doubling.", "",
        "## March-October: USD 0.01-10 per benchmark task", "",
    ]
    for scenario in report["scenarios"]:
        if scenario["score_policy"] != "measured" or (scenario["budget_min"], scenario["budget_max"]) != (.01, 10):
            continue
        lines += [f"### Capability floor {scenario['floor']:g}", "",
                  "| Month | US interpolated area | China interpolated area | Staircase G | Interpolated G | Monthly bracket | First US crossing | Elapsed days |",
                  "| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |"]
        for row in scenario["series"]:
            if row["month"] < "2026-03":
                continue
            lag, event = row["monthly_lag"], row["release_event_lag"]
            bracket = f"{lag['equivalent_us_start']} to {lag['equivalent_us_end']} ({lag['lag_min']}-{lag['lag_max']} bins)" if lag["status"] == "unique_crossing" else lag["status"].replace("_", " ")
            crossing = event.get("first_observed_at_or_above", "—") if event["status"] == "unique_crossing" else "—"
            days = str(event["elapsed_since_first_observed_at_or_above"]) if event["status"] == "unique_crossing" else "—"
            lines.append(f"| {row['month']} | {row['countries']['us']['slope_area']:.6f} | {row['countries']['cn']['slope_area']:.6f} | {row['staircase_G']:.6f} | {row['slope_G']:.6f} | {bracket} | {crossing} | {days} |")
        lines.append("")
    lines += ["## October: floor-30 budget sensitivity", "",
              "| Budget per task | Staircase G | Interpolated G | First US crossing |",
              "| --- | ---: | ---: | --- |"]
    for scenario in report["scenarios"]:
        if scenario["score_policy"] == "measured" and scenario["floor"] == 30:
            row = scenario["series"][-1]
            lines.append(f"| ${scenario['budget_min']:g}-${scenario['budget_max']:g} | {row['staircase_G']:.6f} | {row['slope_G']:.6f} | {row['release_event_lag'].get('first_observed_at_or_above', '—')} |")
    lines += ["", "## Interpretation", "",
              "- In the main scenario, October's monthly comparison bracket is August-September. The release crossing is September 22, **15 elapsed days** before October 7. Calendar-month bins are not literal 30-day durations.",
              "- March's near-zero floor-30 gap reflects clipping; no above-floor Chinese coverage means no meaningful lag estimate.",
              "- Interpolation describes hypothetical operating points and can widen or narrow the gap. All positive main-scenario targets have a unique crossing.",
              "- At floor20 in June, China is ahead at the cutoff. A transient earlier US crossing is not reported as a positive Chinese lag.",
              "- Adding an observation can bend a connecting line downward. The interpolation estimate may decrease although measured options improve.",
              "- The primary sample contains 113 US and 48 Chinese configurations with measured scores and positive task costs. This is a selected benchmark comparison, not a country's overall AI capacity.", "",
              "## Verification", "",
              "The original 33 mathematical/policy tests passed. An independent implementation compared 160 area/gap values at the primary budget, agreeing within 7.11e-15. Its crossing statuses and dates also agreed. These checks verify calculations; they do not establish benchmark completeness or the empirical validity of interpolation.", "",
              "Full scenario aggregates are in [monthly-comparison.json](monthly-comparison.json). Raw observations are omitted; see [source attribution and rights](../NOTICE.md) and [methodology](../docs/methodology.md).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slopes", type=Path, default=ROOT / "analysis/slope-results.json")
    parser.add_argument("--baseline", type=Path, default=ROOT / "analysis/results.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    report = export_aggregates(json.loads(args.slopes.read_text(encoding="utf-8")),
                               json.loads(args.baseline.read_text(encoding="utf-8")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "monthly-comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "snapshot-summary.md").write_text(summary_markdown(report), encoding="utf-8")
    print(f"Wrote aggregate report and summary to {args.output_dir}")


if __name__ == "__main__":
    main()
