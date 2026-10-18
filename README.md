# Pareto Gap

A small, reproducible comparison of US and Chinese public AI models across **capability and cost**, using observations from [Artificial Analysis](https://artificialanalysis.ai/models/).

The question: how does the comparison change when we value the capability available across a range of budgets, rather than only the highest benchmark score? The goal is a transparent method, with assumptions readers can inspect and change.

## Run without an account

You need **Python 3.11 or newer** and an internet connection. No Artificial Analysis account, API key, subscription, Git, or extra Python packages are needed for the normal workflow.

1. [Download the repository ZIP](https://github.com/truong-dat-pham-rmit/ai-pareto-gap/archive/refs/heads/main.zip) and extract it into a folder.
2. [Install Python](https://www.python.org/downloads/) if needed. On Windows, enable **Add Python to PATH** in the installer.
3. **Windows:** open the extracted folder and double-click **`Run-Pareto-Gap.cmd`**. **macOS/Linux:** open a terminal in that folder and run `python3 run.py`.
4. A local report opens in your browser. Read its **data as of** date and snapshot age before interpreting the results.

The runner downloads this repository's **latest published country-level aggregates** and generates your local report. It does not query AA each time someone runs it. A maintainer can refresh the shared aggregate feed using the official AA API; their private key is never distributed to users.

**Current feed status: seeded from 7 October 2026, Intelligence Index v4.3.2.** The bundled seed is historical, not a newly fetched measurement. Fresh publication is not activated until a maintainer configures an authorized AA key and the required external-publication rights. [Maintainer setup](docs/maintainer.md). Each run shows the actual data date and age; fetching the feed does not make old observations current.

To try the report workflow **without internet access**, run:

```sh
python run.py --demo
```

Use `python3` instead of `python` on macOS/Linux if needed. The demo uses invented models and is labeled synthetic. `--offline` uses the bundled published snapshot without a download. `--no-open` saves the report without opening a browser. Generated reports stay in the Git-ignored `local-results/` folder. If a normal download fails, the tool visibly warns before using the bundled snapshot and shows that snapshot's original date.

Advanced users with their own AA access can run `python run.py --live` to fetch and calculate directly. This optional mode requires a key and follows the applicable AA terms. Ordinary users do not need it. [Data details, cached inputs, options, and troubleshooting](docs/data.md).

## Frozen research example

**The chart and table below remain the 7 October 2026 snapshot, Intelligence Index v4.3.2.** They do not update when you run the tool. Your generated reports appear in `local-results/` and identify the snapshot they use.

Historical comparisons apply one snapshot's scores and prices to cumulative release cohorts; they do **not** reconstruct historical prices or API availability.

![Monthly US–China weighted gaps, comparing observed staircases and log-linear interpolation at three capability floors](outputs/slope-gap-march-october-2026.png)

## How it works

1. For each country and cutoff date, keep released model configurations with eligible intelligence scores and a positive published benchmark task cost.
2. Build the cost–capability Pareto frontier: configurations that improve on the capability available at a lower cost.
3. Compare the area above a chosen capability floor, with equal weight for every budget doubling.
4. Compare China's area with earlier US cohorts to obtain a monthly bracket and an actual release-date crossing.

Two representations make the assumption visible:

- **Observed staircase:** only eligible source configurations are affordable options.
- **Log-linear interpolation:** join adjacent frontier points with straight lines in log cost and raw intelligence. The connecting lines represent hypothetical intermediate operating points, not measured model offerings.

The signed gap is `G = US area − China area`. Positive values favor the US; negative values favor China. Units are average above-floor Intelligence Index points, not percentages. A single area ordering does not imply dominance across every budget.

## Example: March–October 2026

Budget: **$0.01–$10 per Intelligence Index task**. Capability floor: **30**. Each cohort ends at month-end, except October, which ends on October 7.

| Chinese cohort | Observed G | Interpolated G | US monthly bracket for interpolated area | Lag in calendar-month bins | First US release crossing |
|---|---:|---:|---|---:|---|
| March | 0.011599 | 0.012058 | No above-floor Chinese coverage | — | — |
| April | 2.163337 | 2.510939 | March–April | 0–1 | April 23 |
| May | 2.608917 | 3.065358 | March–April | 1–2 | April 23 |
| June | 1.858071 | 2.020963 | March–April | 2–3 | April 23 |
| July | 3.950299 | 3.117499 | June–July | 0–1 | July 9 |
| August | 1.453443 | 1.676552 | June–July | 1–2 | July 9 |
| September | 3.755047 | 4.311289 | August–September | 0–1 | September 22 |
| October 7 | 3.755047 | 4.311289 | August–September | 1–2 | September 22 |

For October 7, September 22 is **15 elapsed days earlier**. The “1–2” result is a bracket between calendar-month labels, not a claim of 30–60 elapsed days. September and October have identical areas here; only the cutoff date advances. March's near-zero gap reflects floor clipping and does not establish capability parity.

Interpolation can widen or narrow the gap. It can also lower an estimated area when a new observation bends an earlier connecting line downward. The code checks for multiple crossings rather than assuming the interpolated history always rises. See [the full method and limitations](docs/methodology.md), [snapshot summary](reports/snapshot-summary.md) and [aggregate results](reports/monthly-comparison.json).

## Reproduce

Run from the repository root with Python 3.11+. The calculations and tests use only the standard library. This example uses fictional observations, not the Artificial Analysis snapshot:

```sh
python -m unittest discover -s scripts -p "test_*.py"
python run.py --demo --no-open
python scripts/run_example.py
```

Optional: regenerate the PNG and SVG chart with Matplotlib:

```sh
python -m pip install -r requirements-plot.txt
python scripts/plot_slopes.py --input reports/monthly-comparison.json
```

The real source observations are **not distributed** in this repository. Normal runs use the public aggregate feed. The optional `--live` mode uses the caller's own AA key; advanced users can also [reuse a cached response or import authorized normalized data](docs/data.md). The lower-level analysis scripts retain the original snapshot defaults for reproducibility and accept explicit date, version, and score-policy arguments for other snapshots.

## Data and scope

- Country describes the **model creator**, not an API host. The frozen snapshot uses AA's country metadata. The live free API omits that metadata, so the runner uses the reviewed [creator-country registry](config/creator-countries.json); country metadata supplied by the API takes precedence. Unmapped creators remain excluded and appear in the report.
- Measured lower reasoning efforts and non-reasoning variants are included when the necessary score and cost exist. Configurations remain separate observations.
- The frozen primary analysis excludes estimated scores. The live **API-published** policy includes published numeric scores without inventing missing estimate flags. Explicit measured-only analysis requires an estimate flag of `false`. All area comparisons exclude missing or nonpositive task costs; values are not imputed.
- The frozen local snapshot contained 691 configurations; 113 US and 48 Chinese configurations qualified for its primary cost-aware sample. Live coverage depends on the current API response and is reported for each run.
- Cost is the weighted average cost per Intelligence Index evaluation task, including actual token consumption. It is neither a token-price quote nor a fixed fee for every real-world task.
- Release cohorts retain deprecated records. Historical withdrawal dates and catalog coverage are unavailable.
- The analysis concerns public benchmark observations. It does not estimate private frontier models, training costs, profitability, robotics capability, or a country's overall AI capacity.

The calculations cover floors `0 / 20 / 30 / 40` and budget windows `$0.01–$10 / $0.01–$1 / $0.10–$10`. The live report defaults to floor `30`; change its focus with `--floor 20`, for example. The floor and budget are declared relevance choices, not universal constants.

## Files

| Path | Purpose |
|---|---|
| `run.py` | Download the published aggregate snapshot and open a local report; optional direct API mode |
| `Run-Pareto-Gap.cmd` | Windows launcher |
| `reports/latest.json` | Latest published country aggregates; initially the explicitly labeled October 7 seed |
| `config/creator-countries.json` | Reviewed creator-country fallback for API responses without country metadata |
| `local-results/` | Your downloaded data, provenance, calculations, and HTML reports; excluded from Git |
| `examples/models-synthetic.json` | Fictional observations for the runnable example |
| `scripts/run_example.py` | Run both analyses on the fictional dataset |
| `scripts/analyze_frontiers.py` | Observed frontier areas and historical comparisons |
| `scripts/analyze_slopes.py` | Interpolated areas, crossings and decline audits |
| `reports/monthly-comparison.json` | Derived aggregate results, without model-level observations |
| `reports/snapshot-summary.md` | Frozen-snapshot results and interpretation |
| `docs/methodology.md` | Definitions, interpretation and limitations |
| `docs/data.md` | Keyless setup, optional API mode, input schema, and troubleshooting |
| `docs/maintainer.md` | Private-key setup and manual refresh of the public aggregate feed |

## Attribution and license

[Artificial Analysis](https://artificialanalysis.ai/) supplies the model observations. The frontier calculations, interpolation assumptions, comparisons and charts are derived in this project. Read AA's [general methodology](https://artificialanalysis.ai/methodology) and [Intelligence Index methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking) for the source measurements.

Project code and documentation are available under the [MIT License](LICENSE). Artificial Analysis source observations are omitted because their [terms of use](https://artificialanalysis.ai/terms-of-use) restrict redistribution. Third-party data remain subject to their source rights and terms; the MIT license does not relicense them. This is an independent project, without claimed endorsement by Artificial Analysis.
