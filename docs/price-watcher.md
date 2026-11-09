# Candidate-only resale price watcher

The watcher checks the official data.gov.sg resale transaction export and creates
an **inactive** candidate CSV and SQLite database. It never updates the app's
active CSV/database, policy snapshot/index, evaluation questions or expected prices.
Keep the team's tested dataset frozen during evaluation.

## Run locally

From the repository root, after installing the project:

```powershell
.\.venv\Scripts\python.exe scripts\watch_resale_prices.py
```

No Ollama, GPU or policy index is required. The local default does not publish
anything on GitHub. An optional `--baseline-csv PATH` changes the comparison
input, not the active application dataset or candidate destination.

Each run gets a unique directory under `.local/price-refresh/` containing
`resale.csv`, a validated `hdb_prices.db` when building succeeds, and `report.json`.
The CLI also writes `.local/reports/price-refresh-status.json`. These are ignored
generated files; keep a reviewed copy if needed for reproducibility.

## Outcomes and safeguards

| Outcome | Meaning | CLI exit |
| --- | --- | --- |
| `changed` | Valid candidate differs from the baseline | 0 |
| `unchanged` | Normalised row multiset matches the baseline | 0 |
| `blocked` | Source returned 401, 403 or 429 | 1 |
| `incomplete` | Empty/invalid CSV, regressed month coverage, export not ready, size limit or integrity failure | 1 |
| `failed` | Other HTTP, API, download, validation setup or build failure | 1 |

A GitHub notification failure also returns 1 and retains the candidate report.
A failed check never means the source is unchanged or newly verified.

The fixed dataset is
[`d_8b84c4ee58e3cfc0ece0d773c8ca6abc`](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view).
Downloads use its official
[initiate/poll API](https://guide.data.gov.sg/developer-guide/dataset-apis/download-dataset).
Polling is bounded to five attempts, spaced 15 seconds apart. Requests have
timeouts and CSV downloads are capped at 64 MiB. Redirects are rejected. Export
URLs must use HTTPS and the verified S3 host, bucket and dataset prefix; API
format/location changes require a reviewed code change. Signed export URLs and
raw network exceptions are excluded from diagnostic reports.

The existing resale importer validates every row before building the candidate.
The watcher then checks SQLite integrity and row count. Coverage must retain the
baseline's earliest month and reach at least its latest month. Reports include
byte and normalised-content hashes, month counts, duplicate counts and added/
removed row counts. Row reordering alone is `unchanged`. Exact duplicates retain
their multiplicity: the source has no unit identifier, so deduplication could
discard legitimate transactions. Corrections cannot reliably be distinguished
from deletions/additions; review both rather than treating every addition as a new sale.

## Scheduled review

`.github/workflows/price-refresh.yml` runs daily at approximately **10:33 SGT**
(GitHub may delay it), and supports manual dispatch after it reaches the default
branch. It has read access to repository contents and permission to write issues;
it cannot commit, push or activate data.

The workflow passes `--notify` explicitly. A changed, blocked, incomplete or
failed check opens an attention issue, or comments on an existing marked issue
with the new run link. An unchanged check leaves pending review issues open.
Notification errors fail visibly instead of silently claiming success. Search
index delays can still cause duplicate issues; consolidate them during review.

Diagnostic artifacts are retained for 30 days. Changed, validated candidates also
upload the specific CSV, database and report. Archive any candidate you intend to
retain before the artifacts expire. The first hosted run still needs checking for
repository permissions and data.gov.sg access; local tests cannot prove those.

## Manual activation belongs in a separate reviewed change

1. Review provenance, actual download date, coverage, validation, duplicate counts,
   additions and removals. Inspect unexpected corrections or missing months.
2. Archive the reviewed candidate and its metadata. Decide when evaluation data
   may change; do not replace the dataset while measuring a frozen test run.
3. Run the price tool regressions and development evaluation against that candidate.
   Review changed expected statistics against SQL; do not adjust labels merely
   to make a failing run pass. Do not open or tune on held-out questions.
4. After team approval, separately back up and replace the active source/build
   artifacts through the existing importer process. Preserve the actual download
   date; rebuilding an old CSV today does not make it freshly downloaded.
5. Restart the backend after a reviewed switch so cached dataset metadata and
   response caches cannot retain results from the previous version.

The watcher provides no activation command. Retrieval and LLM generation still
use the existing frozen data until the team performs that separate change.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_price_watch.py -q
```

Offline tests cover inactive builds, active-file preservation, duplicate-aware
comparisons, row reordering, corrections, invalid inputs, bounded polling,
redirect/destination restrictions, size limits, error sanitisation, repeat runs
and notification failures. No live GitHub issue is created by these tests.

A local live check on **9 November 2026** downloaded 244,312 validated rows through
2026-11, compared with the frozen 242,737-row baseline through 2026-10. The multiset
comparison found 1,586 additions and 11 removals. Candidate SQLite integrity was
`ok`; SHA-256 checks confirmed the active CSV and database were unchanged. The
candidate was not activated and no live GitHub notification was sent.
