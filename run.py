"""Download published country areas and calculate a gap without an AA account."""

import sys

if sys.version_info < (3, 11):
    print("Please install Python 3.11 or newer: https://www.python.org/downloads/")
    raise SystemExit(2)

import argparse
from datetime import date, datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import webbrowser


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from aa_api import APIError, fetch_models, normalize_api_models
from analyze_frontiers import analyze, finite_number, parse_date
from analyze_slopes import analyze_slopes, summary_text
from live_report import write_report
from public_feed import FeedError, fetch_public_feed, prepare_public_results


KEY_URL = "https://artificialanalysis.ai/api-key-management-redirect"


def iso_date(value):
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a date like 2026-10-18 (YYYY-MM-DD).") from error


def month_label(value):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) or value.startswith("0000"):
        raise argparse.ArgumentTypeError("Use a month like 2026-03 (YYYY-MM).")
    return value


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare_records(args, registry):
    """Return observations, source envelope and provenance without credentials."""
    if args.demo:
        records = json.loads((ROOT / "examples/models-synthetic.json").read_text(encoding="utf-8"))
        provenance = {
            "source": "Synthetic example", "source_url": "", "synthetic": True,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "intelligence_index_version": "synthetic", "score_policy": "measured",
            "country_audit": {"total_models": len(records), "unknown_creators": [], "unknown_score_status": 0},
        }
        return records, None, provenance

    if args.input:
        print(f"Reading local input: {args.input}")
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            version = args.index_version
            provenance_path = args.input.parent / "provenance.json"
            saved_metadata = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {}
            if not isinstance(saved_metadata, dict):
                raise ValueError("The saved provenance.json must contain a JSON object.")
            version = version or saved_metadata.get("intelligence_index_version")
            if not version:
                raise ValueError("A normalized input needs --index-version, or its saved provenance.json beside it.")
            if not all(isinstance(row, dict) for row in payload):
                raise ValueError("Each normalized model record must be a JSON object.")
            provenance = {"source": "Local normalized input", "source_url": "https://artificialanalysis.ai/",
                          "synthetic": saved_metadata.get("synthetic", False),
                          "fetched_at_utc": saved_metadata.get("fetched_at_utc"),
                          "snapshot_date": saved_metadata.get("snapshot_date"),
                          "intelligence_index_version": str(version), "score_policy": "api_published",
                          "country_audit": saved_metadata.get("country_audit", {"total_models": len(payload)})}
            return payload, None, provenance
    else:
        key = os.environ.get("AA_API_KEY", "").strip()
        if not key:
            print("A free Artificial Analysis API key is required.")
            print(f"Get one here: {KEY_URL}")
            print("Your key will be hidden while you paste it and will not be saved.")
            if not sys.stdin.isatty():
                raise ValueError("No API key found. Run interactively to paste it, or set AA_API_KEY in your environment.")
            key = getpass.getpass("Paste your AA API key, then press Enter: ").strip()
        if not key:
            raise ValueError("No key entered. Try again, or run python run.py --demo without a key.")
        print("Fetching current model data from the official AA API...")
        try:
            payload = fetch_models(key, tier=args.tier, progress=print)
        finally:
            key = None
        payload.setdefault("metadata", {})["snapshot_date"] = date.today().isoformat()

    if not isinstance(payload, dict):
        raise ValueError("Use a saved official API response or a normalized model list.")
    records, audit = normalize_api_models(payload, creator_countries=registry["countries"])
    source_meta = payload.get("metadata") or {}
    if not isinstance(source_meta, dict):
        raise ValueError("The API response metadata must be a JSON object.")
    provenance = {
        "source": "Artificial Analysis API", "source_url": "https://artificialanalysis.ai/",
        "synthetic": False, "fetched_at_utc": source_meta.get("fetched_at_utc"),
        "snapshot_date": source_meta.get("snapshot_date"),
        "intelligence_index_version": str(payload["intelligence_index_version"]),
        "score_policy": "api_published", "endpoint": source_meta.get("endpoint"),
        "country_registry_version": registry["version"], "country_audit": audit,
        "pages_fetched": source_meta.get("pages_fetched"), "api_tier": payload.get("tier"),
    }
    return records, payload, provenance


def choose_snapshot(args, provenance):
    if args.as_of:
        return args.as_of
    if args.demo:
        return date(2026, 10, 7)
    if provenance.get("snapshot_date"):
        try:
            snapshot = date.fromisoformat(provenance["snapshot_date"])
            if snapshot.isoformat() != provenance["snapshot_date"]:
                raise ValueError
            return snapshot
        except (TypeError, ValueError):
            raise ValueError("The cached snapshot date is invalid. Supply --as-of YYYY-MM-DD.") from None
    if provenance.get("fetched_at_utc"):
        try:
            fetched = datetime.fromisoformat(provenance["fetched_at_utc"].replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                raise ValueError
            return fetched.astimezone(timezone.utc).date()
        except (TypeError, ValueError, AttributeError):
            raise ValueError("The cached fetch time must include a timezone. Supply --as-of YYYY-MM-DD.") from None
    if args.input:
        raise ValueError("This cached response has no fetch date. Add --as-of YYYY-MM-DD to declare its snapshot date.")
    return date.today()


def choose_first_month(args, records, snapshot):
    if args.first_month:
        first = args.first_month
    else:
        dated = [parse_date(row.get("release_date")) for row in records
                 if row.get("country") in ("us", "cn")
                 and finite_number(row.get("intelligence")) is not None
                 and (finite_number(row.get("cost_per_task")) or 0) > 0]
        dated = [day for day in dated if day is not None and day <= snapshot]
        first = min(dated).strftime("%Y-%m") if dated else snapshot.strftime("%Y-%m")
    if first > snapshot.strftime("%Y-%m"):
        raise ValueError("The first month must be on or before the snapshot month.")
    return first


def fresh_output_folder(parent, snapshot):
    stamp = snapshot.isoformat() + "_" + datetime.now().strftime("%H-%M-%S")
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1000):
        candidate = parent / (stamp if index == 0 else f"{stamp}_{index + 1}")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            pass
    raise ValueError("Too many result folders with the same timestamp; choose another --output-dir.")


def run_published(args, payload=None):
    """Normal reader mode: no AA account, API key or raw source data."""
    if args.as_of or args.first_month or args.index_version:
        raise ValueError("Published snapshots keep their original dates and version. Date/version overrides require --live or source-data --input.")
    bundled = args.offline
    downloaded_at = None
    if payload is None:
        if not bundled:
            print("Downloading the latest published country-level results. No AA account or key is needed.")
            try:
                payload = fetch_public_feed(progress=print)
                downloaded_at = datetime.now(timezone.utc).isoformat()
            except FeedError as error:
                print(f"Could not download the published feed: {error}")
                print("Using the bundled snapshot instead; its original date will be shown.")
                bundled = True
        if bundled:
            payload = json.loads((ROOT / "reports/latest.json").read_text(encoding="utf-8"))
    result = prepare_public_results(payload)
    metadata = result["metadata"]
    snapshot = date.fromisoformat(metadata["snapshot_date"])
    folder = fresh_output_folder(args.output_dir, snapshot)
    provenance = {
        "source": "Published Pareto Gap country-level results", "source_url": "https://artificialanalysis.ai/",
        "published_feed": True, "published_status": metadata.get("refresh_status"),
        "synthetic": False, "snapshot_date": snapshot.isoformat(),
        "fetched_at_utc": metadata.get("fetched_at_utc"),
        "downloaded_at_utc": downloaded_at, "feed_opened_at_utc": datetime.now(timezone.utc).isoformat(),
        "using_bundled_snapshot": bundled, "feed_metadata": metadata,
        "intelligence_index_version": metadata["intelligence_index_version"],
        "cost_unit": "USD per Intelligence Index benchmark task",
    }
    save_json(folder / "published-results.json", result)
    save_json(folder / "provenance.json", provenance)
    (folder / "summary.txt").write_text(summary_text(result), encoding="utf-8")
    report = write_report(result, [], provenance, folder / "report.html", floor=args.floor)
    candidates = [s for s in result["scenarios"] if s["floor"] == args.floor and s["budget_min"] == .01 and s["budget_max"] == 10]
    selected = next((s for s in candidates if s["score_policy"] in ("api_published", "measured")), candidates[0] if candidates else None)
    if not selected:
        raise ValueError("The published feed does not contain the selected floor and budget.")
    latest = selected["series"][-1]
    print(f"AA snapshot date: {snapshot.isoformat()} | Index version: {metadata['intelligence_index_version']}")
    if metadata.get("refresh_status") == "seed_snapshot":
        print("This is the frozen seed example, not a newly refreshed AA measurement. The maintainer has not activated fresh publication yet.")
    age = (date.today() - snapshot).days
    if age > 0:
        print(f"This snapshot is {age} calendar days old; downloading it does not change its measurement date.")
    if latest["slope_G"] is None:
        print("The published data does not support a gap for both countries at this cutoff.")
    else:
        print(f"Locally calculated gap, floor {args.floor}, $0.01-$10/task: {latest['slope_G']:+.3f} interpolated points.")
        print(f"Observed staircase gap: {latest['staircase_G']:+.3f} points. Positive favors the US; negative favors China.")
    print(f"Report: {report.resolve()}")
    print("No AA account or API key was used. Gaps were calculated locally from published country areas.")
    if not args.no_open:
        webbrowser.open(report.resolve().as_uri())
    return 0 if latest["slope_G"] is not None else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download published country-level data and calculate the US-China gap without an AA account or key.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Advanced: fetch AA directly with your own existing API key")
    mode.add_argument("--offline", action="store_true", help="Use the dated bundled published snapshot without downloading")
    mode.add_argument("--demo", action="store_true", help="Try invented models offline, without an API key")
    mode.add_argument("--input", type=Path, help="Reuse a saved API response or authorized normalized JSON")
    parser.add_argument("--no-open", action="store_true", help="Save the report without opening your browser")
    parser.add_argument("--tier", choices=("free", "pro"), default="free", help="Default: free. Pro requires an existing Pro/Commercial key")
    parser.add_argument("--as-of", type=iso_date, help="Explicit snapshot date for cached inputs")
    parser.add_argument("--first-month", type=month_label, help="First monthly cohort, e.g. 2026-03")
    parser.add_argument("--index-version", help="Version label required for a normalized input without provenance")
    parser.add_argument("--floor", type=int, choices=(0, 20, 30, 40), default=30)
    parser.add_argument("--countries", type=Path, default=ROOT / "config/creator-countries.json", help="Creator-country registry")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "local-results", help="Parent folder for timestamped local results")
    args = parser.parse_args(argv)
    print("Pareto Gap - cost-aware US-China model comparison")
    try:
        if not (args.live or args.demo or args.input):
            return run_published(args)
        if args.input:
            candidate = json.loads(args.input.read_text(encoding="utf-8-sig"))
            if isinstance(candidate, dict) and isinstance(candidate.get("scenarios"), list):
                return run_published(args, payload=candidate)
        registry = json.loads(args.countries.read_text(encoding="utf-8-sig"))
        if not isinstance(registry, dict) or not isinstance(registry.get("countries"), dict) or not registry.get("version"):
            raise ValueError("Country registry must contain a version and a countries object.")
        records, payload, provenance = prepare_records(args, registry)
        snapshot = choose_snapshot(args, provenance)
        first_month = choose_first_month(args, records, snapshot)
        provenance.update(snapshot_date=snapshot.isoformat(),
                          cost_unit="USD per Intelligence Index benchmark task",
                          first_month=first_month,
                          interpretation="Current snapshot scores and costs applied retrospectively to release cohorts, not historical prices.")
        folder = fresh_output_folder(args.output_dir, snapshot)
        if payload is not None:
            save_json(folder / "api-response.json", payload)
        save_json(folder / "models.json", records)
        provenance["normalized_sha256"] = hashlib.sha256((folder / "models.json").read_bytes()).hexdigest()
        save_json(folder / "provenance.json", provenance)
        print(f"Calculating release cohorts from {first_month} through {snapshot.isoformat()}...")
        kwargs = {"snapshot": snapshot, "first_month": first_month,
                  "index_version": provenance["intelligence_index_version"],
                  "policies": (provenance["score_policy"],)}
        baseline, slopes = analyze(records, **kwargs), analyze_slopes(records, **kwargs)
        save_json(folder / "staircase.json", baseline)
        save_json(folder / "slopes.json", slopes)
        (folder / "summary.txt").write_text(summary_text(slopes), encoding="utf-8")
        report = write_report(slopes, records, provenance, folder / "report.html", floor=args.floor)
        latest = next(s for s in slopes["scenarios"] if s["floor"] == args.floor and s["budget_min"] == .01 and s["budget_max"] == 10)["series"][-1]
        print("SYNTHETIC DEMONSTRATION" if provenance["synthetic"] else "Source: Artificial Analysis API (API-published scores)")
        print(f"Snapshot: {snapshot.isoformat()} | Index version: {provenance['intelligence_index_version']}")
        if latest["slope_G"] is not None:
            gap = latest["slope_G"]
            lead = "US" if gap > 0 else "China" if gap < 0 else "neither country"
            print(f"Floor {args.floor}, $0.01-$10/task: interpolated G = {gap:+.3f} points ({lead} ahead).")
            print(f"Observed staircase G = {latest['staircase_G']:+.3f} points.")
            lag = latest["release_event_lag"]
            if lag["status"] == "unique_crossing":
                print(f"First US crossing: {lag['first_observed_at_or_above']} ({lag['elapsed_since_first_observed_at_or_above']} elapsed days before cutoff).")
        else:
            print("A gap could not be calculated: one country lacks usable dated scores and task costs. See the report's coverage details.")
        audit = provenance.get("country_audit") or {}
        if audit.get("unknown_creators"):
            print(f"Excluded unclassified creators: {len(audit['unknown_creators'])}. See report for details.")
        if audit.get("unknown_score_status"):
            print("Note: the API does not identify estimated scores; live results use the API-published score policy.")
        print(f"Report: {report.resolve()}")
        print("Downloads and results stay on your computer. Your API key was not saved.")
        if not args.no_open:
            webbrowser.open(report.resolve().as_uri())
        return 0 if latest["slope_G"] is not None else 2
    except (APIError, FeedError, ValueError, OSError, KeyError) as error:
        print(f"Could not finish: {error}", file=sys.stderr)
        print("For an offline trial, run: python run.py --demo", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Your API key was not saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
