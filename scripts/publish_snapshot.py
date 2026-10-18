"""Maintainer-only refresh of the public, derived country-level results feed.

Requires one private AA key with external Derived Data publication rights.
The default Pro endpoint rejects Free keys. Raw observations are never written
into reports/ or uploaded by the GitHub workflow.
"""

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from aa_api import APIError, fetch_models, normalize_api_models
from analyze_frontiers import analyze
from analyze_slopes import analyze_slopes
from export_report import export_aggregates


ROOT = Path(__file__).resolve().parents[1]


def build_public_snapshot(payload, registry, snapshot):
    if payload.get("tier") not in ("pro", "commercial"):
        raise ValueError("Publishing the shared feed requires an AA tier permitting external Derived Data publication; a Free key is not sufficient.")
    models, audit = normalize_api_models(payload, registry["countries"])
    version = str(payload["intelligence_index_version"])
    released = [row["release_date"] for row in models if row["country"] in ("us", "cn")
                and row["release_date"] and row["release_date"] <= snapshot.isoformat()
                and row["intelligence"] is not None and (row["cost_per_task"] or 0) > 0]
    first_month = min(released)[:7] if released else snapshot.strftime("%Y-%m")
    options = dict(snapshot=snapshot, first_month=first_month, index_version=version, policies=("api_published",))
    baseline, slopes = analyze(models, **options), analyze_slopes(models, **options)
    slopes["metadata"]["input_sha256"] = hashlib.sha256(json.dumps(models, sort_keys=True).encode("utf-8")).hexdigest()
    report = export_aggregates(slopes, baseline)
    report["metadata"].update(
        refresh_status="published_snapshot", score_policy="api_published",
        fetched_at_utc=payload.get("metadata", {}).get("fetched_at_utc"),
        published_at_utc=datetime.now(timezone.utc).isoformat(),
        country_registry_version=registry["version"],
        release_event_lag_basis="Publisher-calculated from country release-cohort areas; monthly readers do not independently reconstruct release-event dates.",
    )
    for country in ("us", "cn"):
        report["metadata"]["coverage"][country]["unknown_score_status"] = sum(row["country"] == country and row["estimated"] is None for row in models)
    # Counts are aggregate coverage diagnostics. Creator/model identifiers and
    # individual benchmark observations are intentionally not exported.
    report["metadata"]["country_assignment_counts"] = audit["country_sources"]
    return report


def public_summary(report):
    meta = report["metadata"]
    rows = ["# Latest published country comparison", "",
            f"AA snapshot: **{meta['snapshot_date']}**. Index version: **{meta['intelligence_index_version']}**.", "",
            "This is the maintainer's latest published aggregate snapshot, not a new AA query by each reader.",
            "Source: [Artificial Analysis](https://artificialanalysis.ai/). The analysis is independent and is not endorsed by Artificial Analysis.", "",
            "Scores and task costs are from one snapshot, applied retrospectively to release cohorts. Live API scores have unknown estimated-score status.", "",
            "| Floor | Budget/task | US area | China area | Interpolated G | Staircase G |",
            "| --- | --- | ---: | ---: | ---: | ---: |"]
    number = lambda value: "Missing" if value is None else f"{value:.6f}"
    for scenario in report["scenarios"]:
        if scenario["floor"] not in (20, 30, 40):
            continue
        latest = scenario["series"][-1]
        rows.append(f"| {scenario['floor']:g} | ${scenario['budget_min']:g}-${scenario['budget_max']:g} | {number(latest['countries']['us']['slope_area'])} | {number(latest['countries']['cn']['slope_area'])} | {number(latest['slope_G'])} | {number(latest['staircase_G'])} |")
    rows += ["", "Positive G favors the US. Download and run the project to compute gaps from the published country areas and view its monthly comparisons without an AA account or key.", ""]
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--snapshot", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    try:
        key = os.environ.get("AA_API_KEY", "").strip()
        if not key:
            raise ValueError("Set AA_API_KEY as a private repository secret or environment variable. Never commit it.")
        registry = json.loads((ROOT / "config/creator-countries.json").read_text(encoding="utf-8"))
        payload = fetch_models(key, tier="pro", progress=print)
        key = None
        report = build_public_snapshot(payload, registry, args.snapshot)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (args.output_dir / "latest-summary.md").write_text(public_summary(report), encoding="utf-8")
        print(f"Published aggregate snapshot files for {args.snapshot}; no source model observations or credentials exported.")
        return 0
    except (APIError, ValueError, OSError, KeyError) as error:
        print(f"Could not refresh the public snapshot: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
