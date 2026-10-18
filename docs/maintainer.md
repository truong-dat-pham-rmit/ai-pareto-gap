# Maintaining the public aggregate feed

Readers run the tool without an AA account or key. Their normal run downloads
`reports/latest.json` from this repository and renders a local report. Only a
maintainer refreshes that shared feed from the official AA API.

## Current status

The initial feed is the **7 October 2026, Intelligence Index v4.3.2** research
snapshot, explicitly marked `seed_snapshot`. Fresh publication is not activated
merely by installing the tool. A maintainer still needs to configure an
authorized AA key and the required publication rights. The reader displays the
data date and snapshot age instead of implying that each download is live.

## One-time setup

1. Confirm your AA access permits **external publication of derived statistics**.
   AA's Free tier is for internal use; public derived feeds require the
   appropriate Pro/Commercial rights or separate permission. Check the current
   [AA terms](https://artificialanalysis.ai/terms-of-use) and your agreement.
   The workflow does not purchase an upgrade or establish those rights for you.
2. Obtain your authorized key through [AA's key management](https://artificialanalysis.ai/api-key-management-redirect).
3. In this GitHub repository, open **Settings → Secrets and variables → Actions**.
4. Choose **New repository secret**. Name it **`AA_API_KEY`** and paste the key
   into the secret value. Save it there; do not put it in chat, an issue, a
   committed `.env` file, workflow text, or a public configuration file.
5. Confirm the applicable external-publication rights before running the
   workflow. A key authenticates the API call; it does not establish
   redistribution permission by itself.

The maintainer's key remains a GitHub Actions secret. Readers never receive it
and do not make requests through a proxy using that shared credential.

## Publish a refreshed snapshot

1. Open the repository's **Actions** tab.
2. Select **Refresh published snapshot**.
3. Choose **Run workflow**, use the intended branch, and start the manual run
   after confirming the applicable external-publication rights.
4. Check that the workflow succeeds and inspect its generated summary and the
   commit updating `reports/latest.json`.
5. Verify that the new feed records the actual snapshot date, benchmark version,
   score policy, coverage, and publication time. Confirm the old seed label is
   gone only after a successful fresh publication. Update the README's initial
   seed-status paragraph when that first refresh is actually complete.
6. Run the reader locally and check that the report shows the published data
   date and age accurately.

The workflow is manually triggered. It has no automatic schedule; do not add
one unless the repository owner asks for recurring refreshes. Without the
secret and appropriate publication rights, fresh publishing remains unconfigured.

The workflow source is
[`refresh-snapshot.yml`](../.github/workflows/refresh-snapshot.yml), and its
publisher is `python scripts/publish_snapshot.py`. The publisher defaults to
the Pro API and checks the tier returned by AA. It rejects a Free-tier response
for this public-feed path; private local analysis and public publication have
different access requirements. An API tier check does not replace reviewing
the applicable agreement or obtaining needed permission.

## What may be published

The publisher exports **derived country-level aggregates**, including areas,
gaps, crossing statuses, snapshot metadata and coverage counts. It uses an
explicit allowlist. Do not publish the raw API response, normalized model
database, frontier model records, private paths, session artifacts, request
headers, or API credentials.

Temporary source observations stay local to the job and are not committed or
uploaded as public artifacts. Check the diff before treating a refresh as
complete. Keep Artificial Analysis attribution and the source measurement
version in the resulting feed.

## Method assumptions during refresh

- Use published cost per Intelligence Index task. Token-price quotes are not
  interchangeable with benchmark task costs.
- Preserve each measured reasoning/configuration setting separately.
- Prefer creator-country metadata supplied by the API. Review exact-name
  fallback mappings in `config/creator-countries.json`; exclude unknown creators
  rather than guessing from model names.
- Preserve omitted estimate flags as unknown and label API-derived calculations
  `api_published`, rather than claiming measured-only coverage.
- Validate one compatible benchmark version across every fetched page.
- Historical cohorts reuse the snapshot's scores and prices; refreshing does
  not reconstruct historical prices or service availability.

The frozen `reports/monthly-comparison.json`, `reports/snapshot-summary.md`, and
original chart remain historical examples. Refreshing `reports/latest.json`
does not make those older artifacts current.
