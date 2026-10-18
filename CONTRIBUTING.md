# Contributing

Please keep changes reproducible and make assumptions explicit. Useful changes
include tests for mathematical edge cases, alternative clearly labeled
interpolation models, and improvements to the documentation and figures.

Run from the repository root:

```sh
python -m unittest discover -s scripts -p "test_*.py"
python run.py --demo --no-open
python scripts/run_example.py
```

The keyless runner, HTML report, analysis and tests need Python 3.11+ and no
third-party packages. Regenerating the frozen PNG/SVG chart needs the optional
`requirements-plot.txt` dependencies. Tests and the offline demo must not need
an AA key or network access; API behavior should be tested with synthetic
fixtures and mocked responses. State separately whether a credentialed live
request was verified.

Normal runs must work without an AA account or key. They fetch this project's
published country aggregates and clearly show their original data date, age,
and seed status. A download/report timestamp must never be presented as a new
AA measurement. Do not embed a maintainer's key in the client or public feed.

For optional `--live` and publisher changes, use AA's official API, preserve source version metadata,
and keep benchmark task costs separate from token-price quotes. Preserve
missing estimate flags as unknown, and never label API-published scores as
measured-only without explicit evidence. Creator-country registry changes
should use exact creator names and cite sources; unknown creators remain
excluded until reviewed. Preserve separate reasoning/configuration records.

Keep the beginner workflow usable from a downloaded ZIP. Avoid adding required
package-installation steps to the runner or requiring Git. Treat changes to the
frozen report as a separate, deliberate research update; running the reader
tool should create local results, not rewrite the published example.

The public-feed publisher must export only explicitly allowed country-level
derived aggregates. Never copy model-level observations, raw responses, API
keys, request headers, or private input paths into the feed. Refreshing the
feed requires a maintainer's configured secret and rights for external derived
publication; see [maintainer setup](docs/maintainer.md). Keep refresh manual
unless the repository owner explicitly requests a schedule.

Do not commit source datasets without redistribution permission, credentials,
browser/session artifacts, local archives, `local-results/`, or personal paths. New empirical
reports should identify their snapshot, benchmark version, coverage, price
basis and temporal assumptions. Label synthetic demonstrations as synthetic.
