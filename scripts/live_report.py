"""Write a self-contained local report. No network requests or third-party code.

The report intentionally renders only allowlisted provenance fields. Source
records stay in the local output folder; credentials never belong in the HTML.
"""

from __future__ import annotations

import html
import math
from collections import Counter
from datetime import date
from pathlib import Path


COUNTRIES = {"us": "United States", "cn": "China"}


def _escape(value):
    return html.escape(str(value), quote=True)


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _formatted(value, digits=3, signed=False):
    value = _number(value)
    if value is None:
        return "Missing"
    return format(value, f"{'+' if signed else ''}.{digits}f")


def _lag_text(lag):
    lag = lag or {}
    status = lag.get("status")
    if status == "unique_crossing":
        start, end = lag.get("equivalent_us_start"), lag.get("equivalent_us_end")
        low, high = lag.get("lag_min"), lag.get("lag_max")
        return f"{start} to {end} · {low}–{high} calendar-month bins"
    if status == "observed_equal_values":
        return "Equal aggregate area observed in the monthly sample"
    if status == "before_observation_window":
        return "US had already reached this area at the start of the sample"
    return {
        "ahead_of_us_at_cutoff": "China ahead at the cutoff",
        "no_above_floor_coverage": "No above-floor Chinese coverage; no lag estimate",
        "multiple_crossings": "Multiple crossings; no single lag estimate",
        "missing_china": "Missing Chinese data",
        "missing_us": "Missing US data",
    }.get(status, "No lag estimate available")


def _crossing_text(event):
    event = event or {}
    status = event.get("status")
    if status in ("unique_crossing", "observed_equal_values", "before_observation_window"):
        at = event.get("first_observed_at_or_above")
        elapsed = event.get("elapsed_since_first_observed_at_or_above")
        if at is not None:
            suffix = f" · {elapsed} elapsed days before this cutoff" if elapsed is not None else ""
            censored = " · first attainment may have been earlier" if event.get("first_attainment_left_censored") else ""
            return f"First observed US release cohort at or above China's aggregate area: {at}{suffix}{censored}."
    return _lag_text(event) + "."


def _models(frontier):
    rows = []
    for model in frontier.get("models", []):
        cost, score = _number(model.get("cost_per_task")), _number(model.get("intelligence"))
        if cost is not None and cost > 0 and score is not None:
            rows.append((cost, score, model))
    return sorted(rows, key=lambda row: row[0])


def _score_at(models, cost, interpolate):
    if not models or cost < models[0][0]:
        return None
    for left, right in zip(models, models[1:]):
        if cost < right[0]:
            if not interpolate:
                return left[1]
            fraction = math.log(cost / left[0]) / math.log(right[0] / left[0])
            return left[1] + fraction * (right[1] - left[1])
    return models[-1][1]


def _frontier_svg(scenario, floor, budget_min, budget_max):
    frontiers = scenario.get("latest_frontiers", {})
    by_country = {country: _models(frontiers.get(country, {})) for country in COUNTRIES}
    scores = [score for rows in by_country.values() for _, score, _ in rows]
    if not scores:
        return '<p class="empty">No usable cost–capability observations for this chart.</p>'
    width, height = 960, 440
    left, right, top, bottom = 72, 26, 24, 67
    plot_width, plot_height = width - left - right, height - top - bottom
    y_min = min(0, floor, min(scores))
    y_max = max(floor + 5, max(scores))
    y_max += max(2, (y_max - y_min) * .08)
    log_min, log_width = math.log(budget_min), math.log(budget_max / budget_min)

    def x(cost):
        return left + (math.log(cost) - log_min) / log_width * plot_width

    def y(score):
        return top + (y_max - score) / (y_max - y_min) * plot_height

    content = [
        '<svg viewBox="0 0 960 440" role="img" aria-labelledby="chart-title chart-desc" xmlns="http://www.w3.org/2000/svg">',
        '<title id="chart-title">US and Chinese cost–capability frontiers</title>',
        '<desc id="chart-desc">Dots are published configurations. Dashed lines interpolate intelligence linearly in log cost and represent hypothetical operating points. Faint steps show observed affordable choices.</desc>',
        f'<defs><clipPath id="plot-clip"><rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}"/></clipPath></defs>',
    ]
    for index in range(6):
        score = y_min + (y_max - y_min) * index / 5
        yy = y(score)
        content += [f'<line class="grid" x1="{left}" x2="{width-right}" y1="{yy:.2f}" y2="{yy:.2f}"/>',
                    f'<text class="tick" text-anchor="end" x="{left-11}" y="{yy+4:.2f}">{score:.0f}</text>']
    ticks = {budget_min, budget_max}
    for exponent in range(math.floor(math.log10(budget_min)), math.ceil(math.log10(budget_max)) + 1):
        value = 10.0 ** exponent
        if budget_min <= value <= budget_max:
            ticks.add(value)
    for cost in sorted(ticks):
        xx = x(cost)
        content += [f'<line class="grid" x1="{xx:.2f}" x2="{xx:.2f}" y1="{top}" y2="{height-bottom}"/>',
                    f'<text class="tick" text-anchor="middle" x="{xx:.2f}" y="{height-bottom+24}">${cost:g}</text>']
    content.append(f'<text class="axis-label" text-anchor="middle" x="{left+plot_width/2}" y="{height-14}">Average USD per benchmark task · logarithmic scale</text>')
    content.append(f'<text class="axis-label" transform="translate(18 {top+plot_height/2}) rotate(-90)" text-anchor="middle">Intelligence Index</text>')
    content.append(f'<g clip-path="url(#plot-clip)"><line class="floor" x1="{left}" x2="{width-right}" y1="{y(floor):.2f}" y2="{y(floor):.2f}"/>')
    for country, models in by_country.items():
        if not models:
            continue
        bounds = sorted({budget_min, budget_max} | {cost for cost, _, _ in models if budget_min < cost < budget_max})
        for low, high in zip(bounds, bounds[1:]):
            score_low = _score_at(models, low, True)
            if score_low is None:
                continue
            score_high = _score_at(models, high, True)
            content.append(f'<line class="curve {country}" x1="{x(low):.2f}" y1="{y(score_low):.2f}" x2="{x(high):.2f}" y2="{y(score_high):.2f}"/>')
            step_low, step_high = _score_at(models, low, False), _score_at(models, high, False)
            content.append(f'<path class="step {country}" d="M{x(low):.2f},{y(step_low):.2f} H{x(high):.2f} V{y(step_high):.2f}"/>')
        for cost, score, model in models:
            if budget_min <= cost <= budget_max:
                title = f"{model.get('name') or model.get('slug') or 'Model'}: score {score:.3f}, ${cost:.4f}/task"
                content.append(f'<circle class="point {country}" cx="{x(cost):.2f}" cy="{y(score):.2f}" r="4.5"><title>{_escape(title)}</title></circle>')
    content.append('</g></svg>')
    return "".join(content)


def _gap_from_areas(row, key):
    countries = row.get("countries", {})
    us = _number(countries.get("us", {}).get(key))
    cn = _number(countries.get("cn", {}).get(key))
    return us - cn if us is not None and cn is not None else None


def _gap_svg(scenario):
    """Draw published country-area differences without needing model records."""
    rows = scenario.get("series", [])
    values = [value for row in rows for key in ("slope_G", "staircase_G")
              if (value := _number(row.get(key))) is not None]
    if not values:
        return '<p class="empty">No comparable country areas in the published monthly series.</p>'
    width, height, left, right, top, bottom = 960, 440, 72, 26, 24, 67
    plot_width, plot_height = width - left - right, height - top - bottom
    y_min, y_max = min(0, min(values)), max(0, max(values))
    pad = max(.1, (y_max - y_min) * .12)
    y_min, y_max = y_min - pad, y_max + pad

    def x(index):
        return left + plot_width * (index / (len(rows) - 1) if len(rows) > 1 else .5)

    def y(value):
        return top + (y_max - value) / (y_max - y_min) * plot_height

    content = [
        '<svg viewBox="0 0 960 440" role="img" aria-labelledby="gap-title gap-desc" xmlns="http://www.w3.org/2000/svg">',
        '<title id="gap-title">Weighted US–China gap by release month</title>',
        '<desc id="gap-desc">Two series show the interpolated and observed staircase gaps, calculated locally as US area minus Chinese area. Positive favors the US; negative favors China. Lines connect sampled monthly values and do not estimate an exact crossing date.</desc>',
    ]
    for index in range(6):
        value = y_min + (y_max - y_min) * index / 5
        yy = y(value)
        content += [f'<line class="grid" x1="{left}" x2="{width-right}" y1="{yy:.2f}" y2="{yy:.2f}"/>',
                    f'<text class="tick" text-anchor="end" x="{left-11}" y="{yy+4:.2f}">{value:+.2f}</text>']
    tick_indices = sorted({0, len(rows) - 1} | set(range(0, len(rows), max(1, math.ceil(len(rows) / 8)))))
    for index in tick_indices:
        xx = x(index)
        content += [f'<line class="grid" x1="{xx:.2f}" x2="{xx:.2f}" y1="{top}" y2="{height-bottom}"/>',
                    f'<text class="tick" text-anchor="middle" x="{xx:.2f}" y="{height-bottom+24}">{_escape(rows[index].get("month", "Unknown"))}</text>']
    content.append(f'<line class="zero" x1="{left}" x2="{width-right}" y1="{y(0):.2f}" y2="{y(0):.2f}"/>')
    content.append(f'<text class="axis-label" text-anchor="middle" x="{left+plot_width/2}" y="{height-14}">Release cohort month · one fixed score and price snapshot</text>')
    content.append(f'<text class="axis-label" transform="translate(18 {top+plot_height/2}) rotate(-90)" text-anchor="middle">Weighted gap · US minus China</text>')
    for key, css, label in (("slope_G", "gap-slope", "Interpolated gap"), ("staircase_G", "gap-step", "Staircase gap")):
        previous = None
        for index, row in enumerate(rows):
            value = _number(row.get(key))
            if value is None:
                previous = None
                continue
            xx, yy = x(index), y(value)
            if previous is not None:
                content.append(f'<line class="gap-line {css}" x1="{previous[0]:.2f}" y1="{previous[1]:.2f}" x2="{xx:.2f}" y2="{yy:.2f}"/>')
            title = f"{row.get('month', 'Unknown')}: {label} {value:+.3f}"
            content.append(f'<circle class="gap-dot {css}" cx="{xx:.2f}" cy="{yy:.2f}" r="4"><title>{_escape(title)}</title></circle>')
            previous = xx, yy
    content.append('</svg>')
    return "".join(content)


def _published_coverage(metadata):
    coverage = metadata.get("coverage")
    if not isinstance(coverage, dict):
        return '<p class="note">Country-area aggregates are supplied by the published snapshot. Per-model coverage counts were not supplied.</p>'
    labels = (
        ("Source configurations", ("total_configurations",)),
        ("Scored configurations", ("measured_scored_configurations", "scored_configurations")),
        ("Scored configurations with positive cost", ("measured_costed_configurations", "costed_configurations", "scored_and_costed_configurations")),
        ("Unknown estimated-score status", ("unknown_score_status",)),
    )
    rows = []
    for label, keys in labels:
        cells, any_supplied = [], False
        for country in COUNTRIES:
            entry = coverage.get(country, {})
            entry = entry if isinstance(entry, dict) else {}
            value = next((entry[key] for key in keys if isinstance(entry.get(key), int)
                          and not isinstance(entry[key], bool) and entry[key] >= 0), None)
            cells.append(str(value) if value is not None else "Not supplied")
            any_supplied |= value is not None
        if any_supplied:
            rows.append(f'<tr><td>{label}</td><td>{cells[0]}</td><td>{cells[1]}</td></tr>')
    if not rows:
        return '<p class="note">Per-model coverage counts were not supplied in this published snapshot.</p>'
    return '<div class="table-wrap"><table><thead><tr><th>Published snapshot coverage</th><th>United States</th><th>China</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def _audit(records, snapshot):
    counts = Counter()
    for row in records:
        country = str(row.get("country") or "").lower()
        counts[f"country_{country if country in COUNTRIES else 'other'}"] += 1
        if country not in COUNTRIES:
            continue
        counts[f"estimate_{country}"] += row.get("estimated") is None
        score, cost = _number(row.get("intelligence")), _number(row.get("cost_per_task"))
        counts[f"score_missing_{country}"] += score is None
        counts[f"cost_missing_{country}"] += cost is None or cost <= 0
        release = row.get("release_date")
        try:
            release = date.fromisoformat(str(release)[:10]).isoformat()
        except (TypeError, ValueError):
            release = None
        counts[f"date_missing_{country}"] += release is None
        counts[f"future_{country}"] += bool(release and release > snapshot)
    return counts


def write_report(result, records, provenance, output_path, *, floor=30, budget_min=.01, budget_max=10):
    """Save the selected scenario plus monthly results as an offline HTML file."""
    if not 0 < budget_min < budget_max:
        raise ValueError("Budget bounds must satisfy 0 < minimum < maximum")
    provenance = provenance or {}
    published = provenance.get("published_feed") is True
    scenarios = result.get("scenarios", [])
    if published:
        scenarios = [{**scenario, "series": [
            {**row, "slope_G": _gap_from_areas(row, "slope_area"),
             "staircase_G": _gap_from_areas(row, "staircase_area")}
            for row in scenario.get("series", [])
        ]} for scenario in scenarios]
    selected = next((row for row in scenarios if row.get("floor") == floor
                     and row.get("budget_min") == budget_min and row.get("budget_max") == budget_max), None)
    if selected is None or not selected.get("series"):
        raise ValueError("No results for the requested floor and budget range")
    metadata = result.get("metadata", {})
    snapshot = str(metadata.get("snapshot_date") or provenance.get("snapshot_date") or "Unknown")
    fetched = provenance.get("fetched_at_utc") or provenance.get("fetched_at") or snapshot
    version = metadata.get("intelligence_index_version") or provenance.get("intelligence_index_version") or "not supplied by source"
    latest = selected["series"][-1]
    policy = selected.get("score_policy", "unknown")
    policy_label = {
        "api_published": "API-published scores · estimate status unavailable",
        "measured": "Measured scores · explicitly estimated scores excluded",
        "including_estimated": "Published scores including estimates",
    }.get(policy, str(policy))
    counts = _audit(records, snapshot)
    cards = []
    for country, label in COUNTRIES.items():
        values = latest.get("countries", {}).get(country, {})
        cards.append(f'<article class="metric"><span class="eyebrow">{label} · interpolated area</span><strong class="{country}">{_formatted(values.get("slope_area"))}</strong><span>Observed staircase: {_formatted(values.get("staircase_area"))}</span></article>')
    cards.append(f'<article class="metric gap"><span class="eyebrow">Weighted gap · US minus China</span><strong>{_formatted(latest.get("slope_G"), signed=True)}</strong><span>Observed staircase gap: {_formatted(latest.get("staircase_G"), signed=True)}</span></article>')
    monthly = []
    for row in selected["series"]:
        country_values = row.get("countries", {})
        month = str(row.get("month", "Unknown")) + (" · partial" if row.get("partial") else "")
        monthly.append('<tr>' + ''.join(f'<td>{_escape(value)}</td>' for value in (
            month,
            _formatted(country_values.get("us", {}).get("slope_area")),
            _formatted(country_values.get("cn", {}).get("slope_area")),
            _formatted(row.get("slope_G"), signed=True),
            _formatted(row.get("staircase_G"), signed=True),
            _lag_text(row.get("monthly_lag")),
        )) + '</tr>')
    sensitivity = []
    for scenario in scenarios:
        if scenario.get("score_policy") != policy or scenario.get("budget_min") != budget_min or scenario.get("budget_max") != budget_max or scenario.get("floor") not in (20, 30, 40):
            continue
        rows = scenario.get("series", [])
        if not rows:
            continue
        row = rows[-1]
        sensitivity.append('<tr>' + ''.join(f'<td>{_escape(value)}</td>' for value in (
            scenario["floor"], _formatted(row.get("slope_G"), signed=True),
            _formatted(row.get("staircase_G"), signed=True), _lag_text(row.get("monthly_lag")),
        )) + '</tr>')
    audit_rows = []
    for label, prefix in (
        ("Supplied configurations", "country"),
        ("Unknown estimated-score status", "estimate"),
        ("Missing intelligence score", "score_missing"),
        ("Missing or nonpositive task cost", "cost_missing"),
        ("Missing or invalid release date", "date_missing"),
        ("Release date after cutoff", "future"),
    ):
        audit_rows.append(f'<tr><td>{label}</td><td>{counts[f"{prefix}_us"]}</td><td>{counts[f"{prefix}_cn"]}</td></tr>')
    frontier_rows = []
    for country, label in COUNTRIES.items():
        for cost, score, model in _models(selected.get("latest_frontiers", {}).get(country, {})):
            frontier_rows.append('<tr>' + ''.join(f'<td>{_escape(value)}</td>' for value in (
                label, model.get("name") or model.get("slug") or "Unnamed configuration",
                f"{score:.3f}", f"${cost:.4f}", model.get("release_date") or "Missing",
            )) + '</tr>')
    unknown = counts["estimate_us"] + counts["estimate_cn"]
    warnings = []
    if provenance.get("synthetic") is True:
        warnings.append("SYNTHETIC EXAMPLE: all model observations and results in this report are fictional demonstration data. They do not describe the current US–China gap.")
    if published:
        if provenance.get("using_bundled_snapshot") is True:
            warnings.append("Using the bundled snapshot. This report has not obtained a newer published result and does not establish today's gap.")
        if provenance.get("published_status") == "seed_snapshot":
            warnings.append(f"Latest published snapshot: {snapshot}. This initial seed snapshot is an older example, not a live measurement. Downloading it today does not update the measurement date.")
        else:
            warnings.append(f"Latest published snapshot: {snapshot}. This report downloads published country-level aggregates and calculates their gaps locally. The snapshot date is the measurement cutoff; the download time is separate.")
        if policy == "api_published":
            warnings.append("This published snapshot uses API-published scores. The API does not expose estimated-score status, so this is not a verified non-estimated-only sample.")
    elif policy == "api_published" or unknown:
        warnings.append(f"This run uses source-published scores. Estimated-score status is unknown for {unknown} supplied US/Chinese configurations; unknown does not mean verified non-estimated.")
    if latest.get("partial"):
        warnings.append(f"The latest month is partial through {latest.get('cutoff_date', snapshot)}.")
    country_note = "Country follows source metadata where available, with the project's reviewed creator-country registry as a fallback. Unmapped creators remain excluded from the US/China comparison."
    registry = provenance.get("country_registry_version")
    if registry:
        country_note += f" Registry version: {registry}."
    audit = provenance.get("country_audit")
    audit_note = ""
    unknown_creators = []
    if isinstance(audit, dict):
        safe_audit = []
        for key, label in (("from_source", "Source-country assignments"), ("from_registry", "Registry assignments"), ("unknown", "Unmapped records"), ("conflicts", "Country conflicts")):
            value = audit.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                safe_audit.append(f"{label}: {value}")
        sources = audit.get("country_sources")
        if isinstance(sources, dict):
            for key, label in (("api_metadata", "API metadata"), ("registry", "Reviewed registry"), ("unknown", "Unmapped")):
                value = sources.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    safe_audit.append(f"Country assignment via {label}: {value}")
        audit_note = "; ".join(safe_audit)
        if isinstance(audit.get("unknown_creators"), list):
            unknown_creators = [name for name in audit["unknown_creators"] if isinstance(name, str)]
    unmapped_note = ""
    if unknown_creators:
        names = ", ".join(_escape(name) for name in unknown_creators)
        unmapped_note = f'<p class="note"><b>Unmapped creators:</b> {names}. These names may include labs from other countries, as well as US or Chinese labs missing from the registry. They are excluded until a country assignment is reviewed.</p>'
    precision_note = (
        "The AA API publishes task costs rounded to four decimal places. Calculations use that published precision, not unrounded source costs. Zero-cost entries are excluded because logarithmic costs require positive values."
        if policy == "api_published" else
        "Task costs are displayed to four decimal places; calculations use the precision supplied by the input. Zero-cost entries are excluded because logarithmic costs require positive values."
    )
    chart_section = f'''<section><h2>Cost–capability frontier</h2><div class="legend"><b class="us"><span class="dot">●</span> United States</b><b class="cn"><span class="dot">●</span> China</b><span>Dots: published configurations</span><span>Dashed lines: hypothetical interpolation</span><span>Faint steps: observed choices</span></div><p class="note scroll-hint">Scroll the chart horizontally to read the full budget range. Labels keep their readable size on smaller screens.</p><div class="chart-wrap" role="region" aria-label="Scrollable cost–capability chart" tabindex="0">{_frontier_svg(selected, floor, budget_min, budget_max)}</div><p class="note">Connect adjacent Pareto points with a straight line in log cost and raw intelligence, then apply the capability floor. The lines assume intermediate operating points; they do not show measured model settings. The dotted horizontal guide marks the floor. Anchors outside the budget range are retained when their connecting line crosses this window; no capability is extrapolated below the cheapest configuration.</p></section>'''
    coverage_section = f'''<section><h2>Data coverage and country assignment</h2><p>{_escape(country_note)}</p>{f'<p class="note">{_escape(audit_note)}</p>' if audit_note else ''}{unmapped_note}<div class="table-wrap"><table><thead><tr><th>Input audit</th><th>United States</th><th>China</th></tr></thead><tbody>{''.join(audit_rows)}</tbody></table></div><p class="note">Other or unmapped country records: {counts['country_other']}. Audit rows can overlap. Missing scores, nonpositive/missing task costs, and missing/future release dates are excluded from the relevant cohort. Different published reasoning settings remain separate configurations.</p></section>'''
    model_section = f'''<section><details><summary>Latest Pareto configurations and task costs</summary><p class="note">Includes anchors outside the chosen budget window. Cost is average USD per Intelligence Index benchmark task; it is not price per million tokens. Costs are displayed to four decimal places; calculations use the precision supplied by the input.</p><div class="table-wrap"><table><thead><tr><th>Country</th><th>Configuration</th><th>Intelligence</th><th>USD/task</th><th>Release date</th></tr></thead><tbody>{''.join(frontier_rows) or '<tr><td colspan="5">No usable frontier observations.</td></tr>'}</tbody></table></div></details></section>'''
    header_meta = f'''Snapshot cutoff: <b>{_escape(snapshot)}</b> · Retrieved (UTC): {_escape(fetched)}'''
    if published:
        downloaded = provenance.get("downloaded_at_utc") or "Not recorded"
        measured_at = provenance.get("fetched_at_utc") or "Not recorded"
        feed_time_label = "Bundled snapshot opened (UTC)" if provenance.get("using_bundled_snapshot") is True else "Feed downloaded (UTC)"
        header_meta = f'''Published snapshot cutoff: <b>{_escape(snapshot)}</b><br>Source data retrieved (UTC): {_escape(measured_at)} · {feed_time_label}: {_escape(downloaded)}'''
        precision_note = "Gaps are calculated locally as published US area minus published Chinese area. The feed contains derived country-level results; individual model records and configurations are not downloaded."
        chart_section = f'''<section><h2>Weighted gap by release month</h2><div class="legend"><b class="us">● Interpolated gap</b><b class="cn">● Observed staircase gap</b><span>Zero: equal aggregate area</span></div><p class="note scroll-hint">Scroll the chart horizontally to read the full monthly series. Labels keep their readable size on smaller screens.</p><div class="chart-wrap" role="region" aria-label="Scrollable monthly weighted gap chart" tabindex="0">{_gap_svg(selected)}</div><p class="note">Positive values favor the US; negative values favor China. The interpolated calculation assumes straight lines between adjacent Pareto points in log cost and raw intelligence; these are hypothetical operating points. Lines here connect monthly samples and do not establish an exact crossing date.</p></section>'''
        feed_metadata = provenance.get("feed_metadata")
        feed_metadata = feed_metadata if isinstance(feed_metadata, dict) else metadata
        coverage_section = f'''<section><h2>Published snapshot coverage</h2><p>Country assignments and exclusions were applied before aggregation. This download contains country-level areas and derived comparisons, rather than individual model observations.</p>{_published_coverage(feed_metadata)}<p class="note">Coverage counts describe the source snapshot used by its publisher. The model dataset is not included or relicensed by this project.</p></section>'''
        model_section = ""
    stylesheet = """
    :root{color-scheme:light dark;--bg:#f4f6fa;--panel:#fff;--ink:#172033;--muted:#526078;--border:#dce2ec;--us:#2563c4;--cn:#c64e4e;--accent:#eaf0fb;--warn:#fff4d8}
    @media(prefers-color-scheme:dark){:root{--bg:#101620;--panel:#192231;--ink:#edf2fa;--muted:#b6c2d4;--border:#334155;--us:#80b2ff;--cn:#ff9990;--accent:#24334d;--warn:#3a3020}}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1160px;margin:0 auto;padding:42px 26px 60px}h1{font-size:clamp(2rem,5vw,3.1rem);line-height:1.12;margin:7px 0 18px;letter-spacing:-.04em}h2{font-size:1.35rem;margin:0 0 13px}p{margin:10px 0 17px}a{color:var(--us)}.eyebrow{text-transform:uppercase;font-size:.74rem;font-weight:750;letter-spacing:.09em;color:var(--muted)}.lede{max-width:840px;color:var(--muted)}.meta{font-size:.9rem;color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:25px 0}.metric,section{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:23px}.metric{display:flex;flex-direction:column;gap:5px}.metric strong{font-size:2.55rem;line-height:1.3;font-variant-numeric:tabular-nums}.metric>span:last-child{font-size:.9rem;color:var(--muted)}.gap{background:var(--accent)}.us{color:var(--us);stroke:var(--us)}.cn{color:var(--cn);stroke:var(--cn)}section{margin:20px 0}.warning{background:var(--warn);border-radius:10px;padding:13px 17px;font-size:.92rem}.legend{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:.9rem;color:var(--muted)}.legend b{font-weight:650}.dot{font-size:1.1rem}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--muted);font-weight:650;white-space:nowrap}td:not(:first-child){font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}svg{display:block;width:100%;height:auto;margin:10px 0}.grid{stroke:var(--border);stroke-width:1}.tick,.axis-label{fill:var(--muted);font:13px system-ui,sans-serif}.axis-label{font-size:14px}.curve{stroke-width:2.8;stroke-dasharray:8 5;fill:none}.step{stroke-width:1.5;opacity:.32;fill:none}.point{fill:var(--panel);stroke-width:2.5}.floor{stroke:var(--muted);stroke-width:1.2;stroke-dasharray:3 5;opacity:.65}.note,.empty{font-size:.9rem;color:var(--muted)}details summary{cursor:pointer;font-weight:650}footer{color:var(--muted);font-size:.85rem;margin-top:26px}code{font-size:.9em} @media(max-width:700px){main{padding:25px 14px 40px}.cards{grid-template-columns:1fr}.metric,section{padding:17px}.metric strong{font-size:2.1rem}th,td{padding:9px 8px}.legend{gap:5px 14px}} @media print{body{background:white;color:black}main{max-width:none;padding:0}section,.metric{break-inside:avoid}.table-wrap{overflow:visible}details{display:block}}
    .chart-wrap{overflow-x:auto;overscroll-behavior-x:contain}.chart-wrap svg{min-width:960px}.scroll-hint{display:none}.gap-line{stroke-width:2.5;fill:none}.gap-slope{stroke:var(--us)}.gap-step{stroke:var(--cn);stroke-dasharray:7 4}.gap-dot{fill:var(--panel);stroke-width:2.5}.zero{stroke:var(--muted);stroke-width:1.7}@media(max-width:1100px){.scroll-hint{display:block}}@media print{.chart-wrap{overflow:visible}.chart-wrap svg{min-width:0}.scroll-hint{display:none}}
    """
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"><title>Pareto Gap · {_escape(snapshot)}</title><style>{stylesheet}</style></head>
<body><main><header><div class="eyebrow">Pareto Gap · {'synthetic demonstration' if provenance.get('synthetic') is True else 'published results' if published else 'local analysis'}</div><h1>What capability does each budget buy?</h1><p class="lede">A cost-aware comparison of public US and Chinese model configurations. The weighted gap averages capability above a chosen floor, with equal weight per budget doubling.</p><p class="meta">{header_meta}<br>Source: {_escape(provenance.get('source') or 'Artificial Analysis')} · Intelligence Index version: {_escape(version)}<br>Score policy: {_escape(policy_label)}</p></header>
{''.join(f'<p class="warning">{_escape(warning)}</p>' for warning in warnings)}
<div class="cards">{''.join(cards)}</div>
<p class="meta">Capability floor <b>{_escape(floor)}</b> · Budget <b>${budget_min:g}–${budget_max:g} per benchmark task</b> · Units: average above-floor Intelligence Index points. Positive gap favors the US; negative favors China. Missing data is shown as “Missing”, never zero.</p>
<p class="note">{_escape(precision_note)}</p>
{chart_section}
<section><h2>Historical release-cohort comparison</h2><p>{_escape(_crossing_text(latest.get('release_event_lag')))}</p><p class="note">{_escape(_lag_text(latest.get('monthly_lag')))}. This compares aggregate areas; it does not establish equality of entire frontiers. Month bins are calendar labels, not exact elapsed durations.</p><div class="table-wrap"><table><thead><tr><th>Release cohort</th><th>US area</th><th>China area</th><th>Interpolated gap</th><th>Staircase gap</th><th>US monthly comparison</th></tr></thead><tbody>{''.join(monthly)}</tbody></table></div><p class="note">All cohorts use this snapshot's scores and prices, restricted to configurations released by each cutoff. These are retrospective comparisons, not reconstructed historical prices, historical benchmark versions, or service availability. A zero area can reflect floor clipping and does not establish parity.</p></section>
<section><h2>How much does the floor matter?</h2><div class="table-wrap"><table><thead><tr><th>Capability floor</th><th>Interpolated gap</th><th>Staircase gap</th><th>US monthly comparison</th></tr></thead><tbody>{''.join(sensitivity) or '<tr><td colspan="4">No floor sensitivity results supplied.</td></tr>'}</tbody></table></div><p class="note">Same latest cutoff and budget range. Adding an observation can bend a connecting line downward, so interpolated area need not rise with each release. Crossings are checked without imposing a running maximum.</p></section>
{coverage_section}
{model_section}
<footer>Benchmark source: <a href="https://artificialanalysis.ai/models/">Artificial Analysis</a> · <a href="https://artificialanalysis.ai/methodology">AA methodology</a>. Independent project; not affiliated with or endorsed by Artificial Analysis. This report runs fully offline; no scripts, fonts, trackers, or external chart libraries are loaded. Source data retains its original terms; the project's code license does not relicense it.</footer></main></body></html>'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
