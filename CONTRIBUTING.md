# Contributing

Please keep changes reproducible and make assumptions explicit. Useful changes
include tests for mathematical edge cases, alternative clearly labeled
interpolation models, and improvements to the documentation and figures.

Run from the repository root:

```sh
python -m unittest discover -s scripts -p "test_analyze*.py"
python scripts/run_example.py
```

Analysis and tests need Python 3.11+ and no third-party packages. Plotting needs
the optional `requirements-plot.txt` dependencies.

Do not commit source datasets without redistribution permission, credentials,
browser/session artifacts, local archives, or personal paths. New empirical
reports should identify their snapshot, benchmark version, coverage, price
basis and temporal assumptions. Label synthetic demonstrations as synthetic.
