# Fetching and using data

## First run

1. [Download the ZIP](https://github.com/truong-dat-pham-rmit/ai-pareto-gap/archive/refs/heads/main.zip) and extract it. Run from the extracted folder, not from inside the ZIP.
2. Install [Python 3.11 or newer](https://www.python.org/downloads/). On Windows, enable **Add Python to PATH**.
3. On Windows, double-click `Run-Pareto-Gap.cmd`. On macOS/Linux, open a terminal in the folder and run `python3 run.py`.
4. The local report opens in your browser. Check its **data as of** date, age, and seed/publication status.

The normal workflow needs **no AA account or API key**. It uses Python's standard library; Git, a package manager, and Matplotlib are unnecessary. Generated files stay in `local-results/`.

Try the same report workflow offline with invented data:

```sh
python run.py --demo
```

Use `python3` if that is your system's Python command. Add `--no-open` to save results without opening a browser. The demo is explicitly synthetic and does not provide empirical country findings. To use the bundled empirical snapshot offline instead, run `python run.py --offline`.

## What the normal run downloads

The default run downloads [`reports/latest.json`](../reports/latest.json) from this repository's public GitHub feed. It contains **derived country-level aggregates**, with dates, versions, score policies, and coverage metadata. It does not contain AA's model database or anyone's API key. Your report uses the latest snapshot the maintainer has published; clicking Run does not initiate a new AA query.

**Initial feed: October 7, 2026, Intelligence Index v4.3.2, marked `seed_snapshot`.** This historical seed makes the keyless workflow usable immediately. It is not a newly fetched measurement. Fresh publication requires the maintainer's private AA key and appropriate rights to publish derived statistics; that setup remains required. See [the maintainer guide](maintainer.md).

The console and report identify the data date separately from the date you generated your report and show the snapshot's age. A successful download does not reset that age. If the publisher has not refreshed the feed, everyone receives the same dated snapshot.

If downloading the feed fails, the runner warns visibly and uses the bundled snapshot. That fallback keeps its original data date and seed label; it is not described as a successful fresh fetch. `--offline` selects the bundled snapshot explicitly and makes no HTTP request.

The report's main scenario uses $0.01–$10 per Intelligence Index task and defaults to capability floor 30. `--floor` accepts `0`, `20`, `30`, or `40`, using the corresponding published scenario. A missing country area stays missing rather than being presented as zero.

## Optional direct API mode

Advanced users and maintainers who already have authorized AA access can fetch directly:

```sh
python run.py --live
```

This optional mode requires your own [AA API key](https://artificialanalysis.ai/api-key-management-redirect). Paste it at the hidden prompt, or supply the `AA_API_KEY` environment variable. Keys are never saved to output files. No key is bundled with the project or shared through the public feed.

Direct mode calls AA's official [free language-model endpoint](https://artificialanalysis.ai/api/v2/language/models/free) by default, which supplies release dates, scores, and benchmark task costs. `--live --tier pro` uses an existing Pro/Commercial key. A free key can support private local analysis; publishing a shared derived feed needs the appropriate external-publication rights described in the [maintainer guide](maintainer.md). No paid subscription or account is created automatically.

**Task cost remains task cost.** The analysis uses dollars per Intelligence Index task, including evaluation token consumption. Blended dollars per million tokens are never substituted for missing task costs.

The free API omits creator country and estimate flags. Direct API normalization therefore uses the reviewed [`config/creator-countries.json`](../config/creator-countries.json) registry for exact creator-name matches, while preferring country metadata supplied by the API. Unknown creators remain excluded and are listed. Scores with missing estimate flags remain unknown; the **`api_published`** policy does not claim they were all measured. The frozen seed retains its original measured-only policy.

The client follows pagination and rejects incompatible benchmark versions across pages. It records the major/minor version supplied by the API without inventing a patch version.

## Where the result goes

Each run creates a folder under `local-results/`, named with its date and time:

| File | Content |
| --- | --- |
| `report.html` | Local browser report, including source date and snapshot status |
| `summary.txt` | Plain-text results |
| `api-response.json` | Direct API mode only: downloaded/cached response |
| `models.json` | Direct API, normalized-input, or demo mode: observations used |
| `provenance.json` | Fetch/source details, benchmark version, and normalization coverage |
| `staircase.json` | Observed frontier areas and historical comparisons |
| `slopes.json` | Log-linear interpolation, gaps, and crossing checks |

`local-results/` is excluded from Git. The key is not saved. Keep the source data subject to AA's applicable terms; the project's MIT license covers its code and original documentation, not AA's dataset.

Available data/provenance files depend on the selected mode. Normal runs use aggregate data and do not create AA model-level observations. Local runs do not overwrite the published October 7 research report or refresh the shared feed.

## Options and cached data

Show all options:

```sh
python run.py --help
```

Examples:

```sh
python run.py --floor 20
python run.py --no-open
python run.py --offline
python run.py --live --first-month 2026-03 --as-of 2026-10-18
python run.py --input path/to/api-response.json
python run.py --input path/to/models.json --index-version 4.3
```

`--input` reuses a saved aggregate report, a cached API response, or authorized normalized input without another download or API-key prompt. Replace example paths with actual files. Normalized input needs `--index-version` unless a saved `provenance.json` beside it supplies the version. A cached response without a saved fetch date also needs `--as-of` to declare its snapshot date.

For direct API, normalized inputs, or demos, `--as-of` sets the final release-cohort cutoff and `--first-month` sets the first monthly cohort. These overrides are rejected for published aggregate feeds: an aggregate-only file cannot be relabeled as a newly calculated date. The filters apply the **same fetched scores and prices** to models released by each cutoff. Choosing an old date does not fetch an archive of historical scores, prices, or availability. Missing release dates are excluded rather than filled with the fetch date.

Above-floor coverage of zero is distinct from missing observations; no usable observations produce missing area, not a country score of zero.

Monthly lag brackets use calendar-month labels. Release-date crossings report elapsed days separately. Interpolation creates hypothetical operating points and can introduce decreases or multiple crossings, so a single lag is not always identifiable.

## Normalized schema

Analysis inputs are UTF-8 JSON arrays. One record represents one model and reasoning/configuration setting. Fields consumed by the analysis are:

| Field | Meaning |
| --- | --- |
| `slug` | Unique configuration identifier |
| `name` | Display name |
| `country` | Creator country; `us` or `cn` for this comparison |
| `release_date` | ISO date, `YYYY-MM-DD`, or `null` |
| `intelligence` | Finite Intelligence Index score, or `null` |
| `cost_per_task` | Positive USD cost per benchmark task, or `null` |
| `estimated` | `true`, `false`, or `null` for unknown |
| `deprecated` | Optional boolean; deprecated entries remain in release cohorts |

Keep scores on a compatible benchmark version. Missing scores and nonpositive or missing costs are excluded from areas. A scored model without a cost may still enter the separate peak-capability calculation. The `measured` policy requires an explicit `estimated: false`; `including_estimated` and `api_published` admit numeric published scores while preserving unknown status.

The repository's [`examples/models-synthetic.json`](../examples/models-synthetic.json) contains invented records. The empirical October 7 observations are not redistributed; its country-level aggregates remain in [`reports/monthly-comparison.json`](../reports/monthly-comparison.json).

For direct use of the calculation scripts, pass the intended metadata explicitly:

```sh
python scripts/analyze_frontiers.py --input path/to/models.json --output local-results/staircase.json --snapshot 2026-10-18 --first-month 2026-03 --index-version 4.3 --policies api_published
python scripts/analyze_slopes.py --input path/to/models.json --output local-results/slopes.json --summary local-results/summary.txt --snapshot 2026-10-18 --first-month 2026-03 --index-version 4.3 --policies api_published
```

Without these overrides, the lower-level scripts retain the original October 7, 2026 / v4.3.2 defaults for reproducibility. `normalize_snapshot.py` is a legacy adapter for the original already-obtained bulk snapshot. Ordinary readers should use the keyless `run.py` workflow.

## Troubleshooting

- **Python is not found:** install Python 3.11+ and reopen the terminal or launcher. On Windows, enable the installer's PATH option; on macOS/Linux, try `python3 --version`.
- **Old data or seed notice:** the download succeeded, but the maintainer has not published a newer snapshot. Running it again does not query AA. The published data date remains authoritative.
- **Unauthorized / invalid key in `--live` mode:** check your key and tier in your own AA account. Normal keyless mode does not need a key. Never paste credentials into an issue or commit them.
- **Rate limit in direct API mode:** wait before trying again, or reuse a cached `api-response.json` with `--input`.
- **Network error:** normal mode warns and falls back to the dated bundled snapshot. Check connectivity and retry to obtain a newer published feed. `--offline`, cached input, and `--demo` need no download.
- **Missing country or gap:** inspect the report's coverage. Missing observations are not a finding of zero capability. Direct-mode reports list excluded creators; registry updates should cite sources.
- **Browser did not open:** find `report.html` in the printed `local-results/` folder and open it manually, or read `summary.txt`.
- **The response format/version changed:** preserve the displayed error and report it without credentials or raw source data. The client rejects incompatible data instead of silently changing the metric.

See [NOTICE](../NOTICE.md) for attribution and data rights and [methodology](methodology.md) for the metric and frozen research assumptions.
