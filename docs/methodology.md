# Methodology

The equations below apply to both the frozen research example and newer
maintainer-published snapshots. The ordinary reader downloads country-level
aggregates without an AA account; the local tool recomputes their signed gaps
and monthly brackets. Release-event dates are publisher-calculated summaries.
The original October example uses explicitly non-estimated scores. New API
snapshots use the **API-published** policy because the API omits estimate flags.
See [the data guide](data.md) for these source and eligibility differences.

## Purpose and measurement basis

This project compares the capability available across a declared range of inference budgets. It combines two familiar descriptions of public AI models: their measured benchmark capability and the average cost of running the benchmark workload. It reports both a signed area difference and an equivalent historical release-cohort bracket.

The dataset is frozen at **7 October 2026** and uses **Artificial Analysis Intelligence Index v4.3.2**. The underlying observations come from [Artificial Analysis's model catalog](https://artificialanalysis.ai/models/); definitions of the source measurements are in AA's [general methodology](https://artificialanalysis.ai/methodology) and [Intelligence Index methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking).

Each historical cohort contains catalogued configurations whose AA release date is on or before the cutoff. Every cohort uses the same snapshot scores and prices. This is a retrospective release-cohort comparison, not an archive of what a buyer actually saw or paid in that month. October ends on October 7; earlier cohorts end at month-end.

## Observations and eligibility

For each locally analyzed configuration, the normalized records retain the creator, creator country, release date, Intelligence Index score, estimated-score flag, cost per task, reasoning effort and other source fields. Values are copied without imputing missing scores or costs. These source records are not distributed with this repository; the public reports contain derived aggregates. A runnable fictional example is provided instead. See the [authorized input schema](data.md).

The primary sample requires:

1. AA creator-country metadata of `us` or `cn`.
2. A valid release date no later than the cohort cutoff.
3. A finite numeric Intelligence Index score that AA does not flag as estimated.
4. A finite, strictly positive published aggregate cost per Intelligence Index task.

The frozen source contains 691 configurations across all countries. At the final cutoff, the primary cost-aware sample contains 113 US and 48 Chinese configurations. The source country field supplies the classification; the analysis does not infer countries from lab names. Hosting location, data residency and model-creator country are different concepts.

Lower reasoning efforts and non-reasoning configurations qualify on the same rules. Configurations of the same model remain separate points. Small parameter counts are not an exclusion criterion: the capability floor is the declared mechanism for concentrating on a relevant score range.

Configurations with intelligence but no usable cost are excluded from area calculations. They can still enter the separate peak-capability analysis if their score meets that analysis's policy. Missing/nonpositive prices are not treated as free inference. Deprecated configurations remain in cumulative release cohorts because withdrawal dates are unavailable; inclusion is not a claim of continued purchasability.

The scripts also produce a score-policy sensitivity that admits estimated scores. In this snapshot none of the estimated-score records has a usable published aggregate task cost, so that policy does not expand the area sample. It can affect peak-score comparisons.

## What cost and intelligence mean

Cost is **USD per Intelligence Index evaluation task**, averaged using AA's benchmark weights and actual token consumption. Token use, reasoning and output length can affect it. Retained per-million-token prices are source metadata and are not the cost axis used here.

The Intelligence Index aggregates benchmark performance. A score of 44 is not a calibrated difficulty label for an individual task, and the published average cost is not the price of every future task. A workload-specific decision would require evaluating the candidate models, effort settings and any routing policy on that same workload.

Benchmark scores can change with measurement noise, benchmark versions or evaluation updates. This project provides no statistical confidence interval for that noise and no estimate of missing model performance.

## Observed frontier

Let $M_g(t)$ be the eligible configurations for country $g$ released by cutoff $t$. Configuration $m$ has score $I_m$ and cost $c_m$.

The observed best affordable score at budget $b$ is:

$$
F_g(t,b)=\max_{m\in M_g(t),\ c_m\leq b} I_m.
$$

The Pareto points are the configurations that increase this running maximum as cost rises. At a shared cost only the highest score is needed. This creates a staircase: a higher capability is available only once its measured configuration becomes affordable.

An interval with no affordable configuration contributes zero above-floor utility. A country-month with no usable costed observations at all is recorded as missing, rather than assigned an area of zero.

## Log-linear interpolation

For the alternative representation, join consecutive nondominated measured points with straight segments in **log cost and raw score**. Between endpoints $(c_0,I_0)$ and $(c_1,I_1)$:

$$
\widetilde F_g(t,b)=I_0+(I_1-I_0)
\frac{\ln(b/c_0)}{\ln(c_1/c_0)},\qquad c_0\leq b\leq c_1.
$$

This is an assumption about unmeasured intermediate operating points. It does not demonstrate that either model has a compute setting, a router or a workload on which it achieves those points. Interpolating settings within one model family may have a stronger empirical rationale, but this illustrative sensitivity connects all adjacent country-frontier points.

For example, endpoints of score 40 at $0.10 and score 48 at $10 imply score 44 at $1 under log-linear interpolation. A straight line in raw dollars would instead imply $5.05. Endpoints alone cannot choose between those assumptions.

Interpolation is applied **before** subtracting and clipping the capability floor. There is no capability extrapolation below the cheapest observed point. Above the most capable point's cost, that observed capability stays available. An anchor outside the chosen budget window is retained when its connecting segment intersects the window.

Equal log-budget weighting and log-linear interpolation are separate choices. The former does not prove the latter.

## Area index and signed gap

For capability floor $f$ and common budget bounds $0<B_{\min}<B_{\max}$, define:

$$
A_g(t;f)=\frac{1}{\ln(B_{\max}/B_{\min})}
\int_{\ln B_{\min}}^{\ln B_{\max}}
\max\left(F_g(t,e^x)-f,0\right)\,dx.
$$

For the interpolated result, replace $F_g$ with $\widetilde F_g$. Both use the same floor and budget bounds across countries and dates. The signed gap is:

$$
G(t;f)=A_{\mathrm{US}}(t;f)-A_{\mathrm{China}}(t;f).
$$

Positive $G$ favors the US; negative $G$ favors China. Units are budget-averaged, above-floor Intelligence Index points. This is not a percentage, a ratio of intelligence or an estimate of economic value.

Integration in log budget weights every proportional cost interval equally: $0.10–$0.20 receives the same weight as $1–$2. Equivalently, the integral can be written over dollar budgets using the weight $db/b$.

The declared main scenario is floor **30**, budget **$0.01–$10/task**. Sensitivities use floors 0, 20, 30 and 40, and budget windows $0.01–$10, $0.01–$1 and $0.10–$10. The floor expresses relevance; it is not a natural boundary between capable and incapable models. Near-zero areas after clipping need not indicate broad capability parity.

Integration is exact over price breakpoints. Observed intervals have constant scores. Interpolated intervals have scores linear in log budget; the implementation integrates the positive part exactly, including intervals where the line crosses the floor.

## Historical comparisons

For a Chinese cohort at cutoff $t$, hold its area fixed as the target and compare it with the US history under the same floor, budget and representation.

**Monthly bracket.** Locate the US monthly observations that bracket the target. The lag labels subtract calendar-month indices. For example, a Chinese October target between US August and September is labeled 1–2 month bins. That is not an elapsed duration of 30–60 days, particularly for a partial October cutoff.

**Release-event crossing.** Independently evaluate cumulative US cohorts at actual release dates. Report the first observed US area at or above the target, together with the elapsed days from that release date to the Chinese cutoff. The target need not have been exactly attained. The code does not interpolate a fictitious equality date between releases.

In the main interpolated scenario, China's October 7 area falls between the US August and September monthly observations. The first US release crossing is September 22: **15 elapsed days before October 7**. The September and October country areas are identical in the snapshot, so the shift from 0–1 to 1–2 month bins reflects the advancing calendar label.

Missing observations, no above-floor Chinese coverage, targets ahead of the current US area, left-censored comparisons, equality and multiple crossings receive explicit statuses. A Chinese lead is not reported as a positive Chinese lag. Country frontiers can cross across budgets; equality of areas is not equality of their shapes or Pareto dominance.

## Nonmonotonicity of the interpolated estimate

The observed staircase cannot lose capability when another eligible configuration is added to a fixed-price cohort. The adjacent-point interpolation can lose area: a newly measured nondominated point below an earlier connecting segment bends that segment downward. This changes an estimate of unmeasured space, not measured capability.

In the main scenario, the interpolated US area decreases from 9.357972 in July to 9.292544 in August. The scripts audit these declines and check crossings for each target. They do not silently impose a running maximum. Multiple crossings are retained explicitly rather than collapsed to one convenient lag.

This also exposes a coverage problem. Countries may have different numbers of tested effort settings and different gaps between their measured points. The staircase and interpolation both depend on that coverage. Interpolation can fill a large observational gap with assumed capability; it is not an unbiased correction for missing data.

## Interpretation limits

- The analysis measures a selected public benchmark tradeoff, not a country's overall AI capacity or unobserved private models.
- Fixed snapshot prices are not training costs, marginal production costs or historical prices. They do not establish commercial sustainability.
- Scores and prices are specific to the benchmark's workload. Latency, reliability, context limits, deployment restrictions and downstream task value are outside the area formula.
- The contemporary catalog is incomplete as a historical archive. Missing scores, missing costs and missing release/withdrawal information can alter comparisons.
- A time bracket depends on the shape and release cadence of the US reference history. It is not a forecast or a constant rate of progress.
- The main defaults are choices that should be read alongside the sensitivity results. Interpolation can change even the sign of a small gap: at floor 20 in April, the observed Chinese lead becomes an interpolated US lead.

## Reproduction and source rights

From the repository root, run the fictional example and tests:

```sh
python -m unittest discover -s scripts -p "test_analyze*.py"
python scripts/run_example.py
```

The published [aggregate results](../reports/monthly-comparison.json) and [snapshot summary](../reports/snapshot-summary.md) contain the real-snapshot comparisons without redistributing model-level source observations. The optional plot command and dependencies are documented in the [README](../README.md).

With an authorized normalized input, the two analysis scripts can generate detailed JSON locally. The staircase output includes areas and historical comparisons. The interpolation output also includes target crossings, decline audits and frontier segments; its `--summary` argument selects a readable text report. These detailed outputs can contain source observations and should be handled under the source's terms. See [data instructions](data.md) for commands.

Artificial Analysis supplies the observations; this project supplies the derived frontier metrics, interpolation and comparisons. Project code and documentation are MIT-licensed. AA source observations are omitted because their [terms of use](https://artificialanalysis.ai/terms-of-use) restrict redistribution. Third-party data remain subject to their source rights and terms and are not relicensed under MIT.
