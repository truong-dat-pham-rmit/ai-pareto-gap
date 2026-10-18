"""Download the project's public derived aggregates without an AA account.

The feed contains country-level areas, not source model observations. Country
areas are supplied by the publisher; gaps and monthly crossings are recalculated
locally. An old snapshot remains old even when downloaded today.
"""

from copy import deepcopy
from datetime import date
import calendar
import json
import math
import re
import socket
from urllib import error as urllib_error
from urllib import request as urllib_request

from analyze_slopes import decline_audit, target_crossings


PUBLIC_FEED_URL = "https://raw.githubusercontent.com/truong-dat-pham-rmit/ai-pareto-gap/main/reports/latest.json"
MAX_FEED_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 30
POLICIES = {"measured", "including_estimated", "api_published"}


class FeedError(ValueError):
    """A user-readable download or aggregate-schema error."""


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def fetch_public_feed(opener=None, progress=None):
    """Download only the fixed public GitHub feed; no credentials are requested."""
    if progress:
        progress("Downloading the project's latest published country-level aggregates...")
    open_request = opener or urllib_request.build_opener(_NoRedirect()).open
    request = urllib_request.Request(PUBLIC_FEED_URL, headers={"Accept": "application/json", "User-Agent": "ai-pareto-gap/1"})
    try:
        with open_request(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_FEED_BYTES + 1)
    except urllib_error.HTTPError as error:
        if error.code == 404:
            raise FeedError("The public results feed is not available yet (HTTP 404). Try again later or use --demo.") from None
        raise FeedError(f"Could not download the public results feed (HTTP {error.code}). Try again later or use --demo.") from None
    except (TimeoutError, socket.timeout):
        raise FeedError("The public results download timed out. Check your connection and try again.") from None
    except (urllib_error.URLError, OSError):
        raise FeedError("Could not connect to the public results feed. Check your connection and try again.") from None
    if len(raw) > MAX_FEED_BYTES:
        raise FeedError("The public results feed exceeds the 4 MB safety limit.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise FeedError("The public results feed is not valid JSON. Try again later.") from None
    if not isinstance(payload, dict):
        raise FeedError("The public results feed must be a JSON object.")
    return payload


def _reject_nonfinite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise FeedError("The public results feed contains a non-finite number.")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite(item)


def _number(value, field, *, nullable=False):
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise FeedError(f"The public results feed has an invalid {field}; expected a nonnegative number{' or null' if nullable else ''}.")
    return value


def _date(value, field):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise FeedError(f"The public results feed has an invalid {field}; expected YYYY-MM-DD.") from None


def _version(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise FeedError("The public results feed needs an Intelligence Index version.")
    text = str(value).strip()
    if not re.fullmatch(r"v?[1-9][0-9]*(?:\.[0-9]+){0,2}", text):
        raise FeedError("The public results feed has an invalid Intelligence Index version.")
    return text.removeprefix("v")


def _same_version(container, expected):
    if "intelligence_index_version" in container and _version(container["intelligence_index_version"]) != expected:
        raise FeedError("The public results feed mixes Intelligence Index versions.")


def _release_event(value, cutoff):
    if value is None:
        return {"status": "not_supplied"}
    if not isinstance(value, dict) or not isinstance(value.get("status"), str):
        raise FeedError("The public results feed has an invalid release-event summary.")
    allowed = {
        "status", "target_at", "target_value", "unit", "lag_min", "lag_max",
        "history_has_decreases", "missing_observations", "upward_crossings", "downward_crossings",
        "equal_observations", "latest_us_value", "first_observed_at_or_above",
        "elapsed_since_first_observed_at_or_above", "first_attainment_left_censored",
        "equivalent_us_start", "equivalent_us_end", "lower_bound_is_strict",
    }
    event = {key: deepcopy(item) for key, item in value.items() if key in allowed}
    for field in ("target_at", "first_observed_at_or_above", "equivalent_us_start", "equivalent_us_end"):
        if event.get(field) is not None and _date(event[field], "release-event date") > cutoff:
            raise FeedError("The public results feed has a release-event date after its cohort cutoff.")
    for field in ("lag_min", "lag_max", "elapsed_since_first_observed_at_or_above", "missing_observations"):
        if event.get(field) is not None:
            _number(event[field], "release-event duration")
    if event.get("status") == "unique_crossing" and not event.get("first_observed_at_or_above"):
        raise FeedError("A published unique release-event crossing needs its observed date.")
    return event


def prepare_public_results(payload):
    """Validate aggregates and recompute gaps and monthly crossings locally.

    Release-event summaries cannot be reconstructed from monthly aggregates and
    remain explicitly publisher-supplied. No source model data is returned.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
        raise FeedError("The public results feed needs a metadata object.")
    _reject_nonfinite(payload)
    original_meta = payload["metadata"]
    snapshot = _date(original_meta.get("snapshot_date"), "snapshot date")
    version = _version(original_meta.get("intelligence_index_version"))
    _same_version(payload, version)
    supplied = payload.get("scenarios")
    if not isinstance(supplied, list) or not supplied or len(supplied) > 1000:
        raise FeedError("The public results feed needs a nonempty, bounded scenario list.")
    metadata_fields = {
        "title", "source", "source_url", "source_methodology_url", "source_input_sha256",
        "content", "analysis_type", "area_units", "gap_sign", "interpolation",
        "interpolation_status", "caveats", "data_notice", "coverage", "fetched_at_utc",
        "published_at_utc", "country_registry_version", "score_policy", "refresh_status",
        "publication_status", "feed_status", "update_status", "refresh_enabled",
    }
    metadata = {key: deepcopy(value) for key, value in original_meta.items() if key in metadata_fields}
    metadata.update(
        snapshot_date=snapshot.isoformat(), intelligence_index_version=version,
        aggregate_only=True, public_feed_url=PUBLIC_FEED_URL,
        gap_calculation="US minus China, recomputed locally from published country areas",
        monthly_lag_calculation="Recomputed locally from each scenario's monthly country-area history",
        release_event_lag_basis="Publisher-supplied release-date summaries; not independently recomputed from monthly aggregates.",
    )
    scenarios, seen = [], set()
    expected_timeline = None
    for supplied_scenario in supplied:
        if not isinstance(supplied_scenario, dict):
            raise FeedError("Every public-feed scenario must be an object.")
        _same_version(supplied_scenario, version)
        policy = supplied_scenario.get("score_policy")
        if not isinstance(policy, str) or policy not in POLICIES:
            raise FeedError("The public results feed has an unsupported score policy.")
        floor = _number(supplied_scenario.get("floor"), "capability floor")
        low = _number(supplied_scenario.get("budget_min"), "minimum budget")
        high = _number(supplied_scenario.get("budget_max"), "maximum budget")
        if not 0 < low < high:
            raise FeedError("Public-feed budget bounds must satisfy 0 < minimum < maximum.")
        identity = (policy, low, high, floor)
        if identity in seen:
            raise FeedError("The public results feed has duplicate scenarios.")
        seen.add(identity)
        series = supplied_scenario.get("series")
        if not isinstance(series, list) or not series or len(series) > 2400:
            raise FeedError("Every public-feed scenario needs a nonempty, bounded monthly series.")
        scenario = {
            "id": f"{policy}_b{low:g}-{high:g}_f{floor:g}", "score_policy": policy,
            "floor": floor, "budget_min": low, "budget_max": high, "series": [],
        }
        histories = {country: [] for country in ("us", "cn")}
        timeline = []
        previous_month = None
        for supplied_row in series:
            if not isinstance(supplied_row, dict):
                raise FeedError("Every public-feed monthly row must be an object.")
            _same_version(supplied_row, version)
            month = supplied_row.get("month")
            if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
                raise FeedError("The public results feed has an invalid cohort month.")
            cutoff = _date(supplied_row.get("cutoff_date"), "cohort cutoff")
            if cutoff.strftime("%Y-%m") != month or cutoff > snapshot or (previous_month is not None and month <= previous_month):
                raise FeedError("The public results feed has unordered or inconsistent cohort dates.")
            previous_month = month
            timeline.append((month, cutoff.isoformat()))
            supplied_countries = supplied_row.get("countries")
            if not isinstance(supplied_countries, dict):
                raise FeedError("A public-feed row needs both country-area objects.")
            countries = {}
            for country in ("us", "cn"):
                supplied_country = supplied_countries.get(country)
                if not isinstance(supplied_country, dict) or not {"slope_area", "staircase_area"}.issubset(supplied_country):
                    raise FeedError("A public-feed row needs explicit slope and staircase areas for US and China; missing areas must be null.")
                smooth = _number(supplied_country["slope_area"], "country slope area", nullable=True)
                step = _number(supplied_country["staircase_area"], "country staircase area", nullable=True)
                if (smooth is None) != (step is None):
                    raise FeedError("A public-feed country's slope and staircase areas must share missingness.")
                if smooth is not None and smooth < step - 1e-8:
                    raise FeedError("A public-feed interpolated area cannot be below its observed staircase area.")
                countries[country] = {"slope_area": smooth, "staircase_area": step,
                                      "interpolation_uplift": smooth - step if smooth is not None else None}
                histories[country].append({"at": month, "value": smooth})
            comparable = countries["us"]["slope_area"] is not None and countries["cn"]["slope_area"] is not None
            row = {
                "month": month, "cutoff_date": cutoff.isoformat(),
                "partial": cutoff.day != calendar.monthrange(cutoff.year, cutoff.month)[1],
                "countries": countries,
                "slope_G": countries["us"]["slope_area"] - countries["cn"]["slope_area"] if comparable else None,
                "staircase_G": countries["us"]["staircase_area"] - countries["cn"]["staircase_area"] if comparable else None,
                "monthly_lag": target_crossings(month, countries["cn"]["slope_area"], histories["us"], "months"),
                "release_event_lag": _release_event(supplied_row.get("release_event_lag"), cutoff),
                "release_event_lag_source": "publisher" if supplied_row.get("release_event_lag") is not None else "not_supplied",
            }
            scenario["series"].append(row)
        if series[-1]["cutoff_date"] != snapshot.isoformat():
            raise FeedError("Each public-feed series must end on its declared snapshot date.")
        if expected_timeline is None:
            expected_timeline = timeline
        elif timeline != expected_timeline:
            raise FeedError("Public-feed scenarios must use the same monthly cohort cutoffs.")
        scenario["declines"] = {country: {"monthly": decline_audit(histories[country])} for country in ("us", "cn")}
        scenarios.append(scenario)
    metadata["first_month"] = expected_timeline[0][0]
    return {
        "metadata": metadata,
        "settings": {
            "floors": sorted({s["floor"] for s in scenarios}),
            "budgets": [list(pair) for pair in sorted({(s["budget_min"], s["budget_max"]) for s in scenarios})],
            "policies": sorted({s["score_policy"] for s in scenarios}),
        },
        "scenarios": scenarios,
    }
