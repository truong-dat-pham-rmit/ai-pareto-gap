# Attribution and data rights

The original software, documentation, synthetic examples and visualization code
in this repository are available under the [MIT License](LICENSE).

The frozen research report derives country-level statistics from observations
published by [Artificial Analysis](https://artificialanalysis.ai/models/), using
its [Intelligence Index methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking).
Artificial Analysis supplies the underlying benchmark observations. The
interpolation assumptions, area metric, temporal comparisons and charts are
this project's analysis. Artificial Analysis has not endorsed this project.

The normal reader workflow downloads this project's published country-level
aggregate feed without requiring an AA account or key. It does not download
AA's model database or make a fresh AA request for each reader. The feed starts
with a clearly marked **7 October 2026 seed snapshot**; downloading that seed
does not make it a current measurement.

An optional direct `--live` mode uses the caller's own authorized API key.
A maintainer can refresh the public aggregate feed through AA's official API
with a private repository secret and appropriate external-publication rights.
AA's Free tier is intended for internal use; public derived publication needs
the appropriate Pro/Commercial rights or other permission under the applicable
[terms](https://artificialanalysis.ai/terms-of-use). The project does not create
accounts, purchase subscriptions, or distribute a shared API key.

Raw responses, normalized model observations and local calculations stay in
Git-ignored `local-results/`. The publisher exports country-level derived
aggregates only. API credentials are not saved in reports or the public feed.
Use of the API and data remains subject to the user's access and AA's terms;
the presence of a downloader does not grant redistribution rights.

The source snapshot is dated **7 October 2026**, Intelligence Index **v4.3.2**.
The published report contains derived aggregate results, not the source model
database. Raw downloads, normalized AA model observations, browser/session
artifacts and archives containing those observations are excluded from Git.

Live API output is a separate snapshot and does not update this frozen example.
API-published score policies and the creator-country fallback registry are
documented in [the data guide](docs/data.md). Country metadata supplied by AA
takes precedence over the reviewed registry; missing estimate flags remain
unknown. The registry and analysis are this project's work, not AA endorsements
of its country classification or conclusions.

The MIT license does not grant rights to third-party benchmark datasets,
model names, trademarks, or material imported by users. Obtain source data
through a channel that permits your intended use and follow its applicable
[terms](https://artificialanalysis.ai/terms-of-use). A public website should not
be assumed to provide an open dataset license.

The included example model records are invented and are explicitly labeled
synthetic. They are suitable for testing and demonstrating the method.
