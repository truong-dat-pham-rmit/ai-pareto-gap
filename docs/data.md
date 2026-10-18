# Input data

The repository includes invented records in
[`examples/models-synthetic.json`](../examples/models-synthetic.json).
The empirical AA source snapshot remains local; it is not redistributed.
Public country-level aggregate outputs are in
[`reports/monthly-comparison.json`](../reports/monthly-comparison.json).

## Normalized schema

Analysis inputs are UTF-8 JSON arrays. One record represents one model and
reasoning/configuration setting. Supply observations that you have permission
to use. Fields consumed by the analysis are:

| Field | Meaning |
| --- | --- |
| `slug` | Unique configuration identifier |
| `name` | Display name |
| `country` | Developer country, `us` or `cn` for the included comparison |
| `release_date` | ISO date, `YYYY-MM-DD` |
| `intelligence` | Finite Intelligence Index score, or `null` |
| `cost_per_task` | Positive USD cost per benchmark task, or `null` |
| `estimated` | Explicit boolean; `true` is excluded by the measured-only policy |
| `deprecated` | Optional boolean; deprecated entries are retained in release cohorts |

Supply explicit estimate flags. The original scripts treat only the boolean
`true` as estimated; a missing flag is not independently verified as measured.
Keep scores on one compatible benchmark version. Do not substitute blended
dollars per million tokens for dollars per benchmark task.

Missing scores are excluded. Missing, zero and negative costs are excluded from
area comparisons. A scored model without a usable cost may still enter the
separate peak-capability calculation. Countries with no costed observations
produce missing area, not a country score of zero.

## Run the frozen empirical analysis with authorized local data

From the repository root:

```sh
python scripts/analyze_frontiers.py --input path/to/models.json --output outputs/staircase.json
python scripts/analyze_slopes.py --input path/to/models.json --output outputs/slopes.json --summary outputs/slopes.txt
```

These analysis scripts deliberately use the frozen **2026-10-07** cutoff and
**v4.3.2** benchmark metadata. Supplying a new input file does not automatically
turn them into a current-data tracker. Review those constants and source
compatibility before adapting the research to another snapshot.

`normalize_snapshot.py` is an optional adapter for an already obtained compatible
AA-style JSON object with a `models` array. It copies `creator.country`, the
published aggregate task cost and other source fields. It does not download
data and does not infer lab nationality. Its metadata describes this frozen
snapshot; it is not a general-purpose live API client.

See [NOTICE](../NOTICE.md) for source attribution and rights.
