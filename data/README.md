# Data integration

Planned local directories, excluded from Git:

- `raw/`: downloaded official policy snapshots and resale transaction CSVs.
- `processed/`: normalized policy chunks and the resale SQLite database.
- `topic_cards/`: committed, reviewed discovery cards (12 cards; see its README).
- `policy_snapshots/`, `policy_chunks/`, `schema/`: committed official policy
  snapshots, their chunks and the shared vocabulary (see "Policy refresh process").
- `evaluation/`
    - `development/`: committed development questions and Stage 1 gateway labels.
    - `held-out/`: private final-evaluation questions; kept outside the repository
- `chroma/`: generated vector index.

Generated, imported and private evaluation data are excluded from Git. The
development set is the exception: it is committed so the team can reproduce
gateway and routing tests. See `evaluation/development/README.md` for the
relationship between the rich semantic questions and the machine-readable
Stage 1 labels.

The held-out set must not be used while tuning routing, extraction or prompts.
Git ignore rules only prevent accidental commits; they are not a security
boundary. Keep held-out questions and labels outside the workspace or provide
them only during final evaluation.

Policy records should preserve stable IDs, source URL, effective date, snapshot
version and superseded status. Do not infer an effective date from a crawl date;
decide how unknown dates are represented before loading official pages.

Transaction imports should record their source, download date, coverage and schema.
The SQLite adapter will accept validated filters and use parameterised read-only
queries. An absent dataset must not be replaced with invented price figures.

The only evidence shipped with this scaffold is fictional and lives in
`backend/kopi_keys/components/policy_retrieval.py`. Topic cards go in
`topic_cards/` (see its README).

## Resale transactions (Price Query Tool)

1. Download the CSV from data.gov.sg: [Resale flat prices based on registration
   date from Jan-2017 onwards](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view).
   Use only this file: the older files in the collection use approval dates
   (1990 to Feb 2012) or a different / missing `remaining_lease` format.
2. Save it as `data/raw/2017-onwards-resale-prices.csv`.
3. Build the database, recording the date the CSV was downloaded:

   ```bash
   python scripts/build_resale_db.py --downloaded-on YYYY-MM-DD
   ```

   Every row is validated first; one bad row rejects the import and leaves any
   existing database untouched. Output: `data/processed/hdb_prices.db`
   (override with the `KOPI_RESALE_DB` environment variable). Team snapshot:
   downloaded 2026-10-14, 242,737 sales, 2017-01 to 2026-10 (October partial).
4. Query it (dates default to the last 12 months, as in the graph):

   ```bash
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM"
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM" \
       --question "What are 4-room prices in Tampines?" --output .local/tampines.json
   python -m kopi_keys.cli --input .local/tampines.json   # full graph with Ollama
   ```

`SqlitePriceTool.query()` returns `PriceResult` (`schemas.py`). Quartiles use
inclusive linear interpolation (Excel `QUARTILE.INC`); mean, median and IQR are
rounded once to cents. Zero matches return `volume: 0`. Unknown towns / flat
types and dates outside the data raise `InvalidPriceFilterError` (a
`ToolUnavailableError`, so the graph stores it in `price_error`), with
suggestions. `is_low_volume()` flags fewer than 10 sales.

## Income ceilings

`backend/kopi_keys/rules/income_ceilings.json` holds grant income ceilings with
source URL and dates; `kopi_keys.rules.check_income_ceiling()` compares an
income against them and never states eligibility. Four of the five
figures are now `verified: true` against the official HDB pages in the policy
snapshot; the Proximity Housing Grant entry is still `verified: false`. See
"Income ceilings verified against the policy snapshot" below.

## Policy refresh process (DRAFT — Person 4, 2026-10-15; to be agreed with the team)

Official policy snapshots live in `data/policy_snapshots/<YYYY-MM-DD>/`. They are
committed to Git, so teammates don't need to re-scrape. Each snapshot folder has
its own README describing its scope and rules. Folders are append-only: a new
snapshot is a new folder, and old ones are never edited.

**`data/policy_snapshots/ACTIVE`** holds one line: the date of the snapshot the advisor
serves. Code that loads policy chunks must read this file, never "the newest folder".
Only a person changes it, after review. To roll back, set it to an earlier date.

1. **Re-snapshot (automatic)**. `.github/workflows/policy-refresh.yml` runs
   `scripts/scraping/refresh.py` at 10:00 SGT on the 1st of each month and pushes the
   new folder straight to `main`. The new folder is **not live**. Run it manually from
   the Actions tab ("Run workflow") after any announced HDB/CPF policy change, e.g. Budget,
   National Day Rally or a BTO launch. If the run fails (e.g. a site blocks it), nothing
   is pushed. In that case run `python refresh.py` locally and commit the result.
   - After the 1st of the month, run `git pull` before pushing, because the bot will have added a commit.
2. **Alert (automatic)**. `refresh.py` ends with `diff.py`, which compares the new snapshot
   with the `ACTIVE` one and writes `changes_since_<ACTIVE date>.md` into the new folder.
   Pages whose dollar, year or age figures changed are listed first. If anything changed,
   the workflow opens a GitHub Issue with a review checklist.
3. **Review**. A person reads each change against the live page. For each change confirmed as real:
   - mark the affected old chunks `superseded: true`;
   - re-check any topic card that cites them.
   The output verifier already rejects citations of superseded sources.
4. **Go live**. Set `ACTIVE` to the new date. Rebuild the chunks and cards for it with
   `cd scripts/scraping && python chunk.py && python build_cards.py && python validate.py`
   and fix anything `validate.py` reports. Then note the review outcome in the
   snapshot's README (including anything unresolved), push, and close the issue. If the
   snapshot looks broken, leave `ACTIVE` unchanged and close the issue with a note.

Freshness fields kept per source. The first two are in each snapshot's
`manifest.json`; `effective_date` is added per chunk in Day 2:

| Field | Meaning |
|---|---|
| `snapshot_date` / `fetched_at` | When we last saw this text live |
| `last_updated_printed` | The page's own "Last updated" line, verbatim, or null |
| `effective_date` | Only when the page states one, otherwise null. Never derived from the two fields above |

Answers should show the snapshot date, e.g. "according to HDB, as of 15 Oct 2026",
and link to the live page.

## Income ceilings verified against the policy snapshot (Person 4, 2026-10-16)

Tasha's `backend/kopi_keys/rules/income_ceilings.json` (PR #2) cited a secondary
blog and set every figure to `verified: false`. Each figure below was checked
against the official HDB page in snapshot `2026-10-15` (verbatim text in
`data/policy_snapshots/2026-10-15/clean/<slug>.md`). These entries now have
the HDB `source_url`, `checked_on: "2026-10-15"` and `verified: true` (applied in
the merge of `main` into `feat/policy-snapshot-topic-cards-and-ui`). **Only the
source fields changed. No ceiling value changed.**

| Scheme key | Ceiling | Snapshot slug | Official wording |
|---|---|---|---|
| `cpf_housing_grant_family` | $16,000 | `hdb-grant-family-cpf-housing-grants` | "must not exceed: $16,000" |
| `cpf_housing_grant_single` | $8,000 | `hdb-grant-singles-cpf-housing-grant` | "$8,000 if purchasing a flat on your own" |
| `enhanced_cpf_housing_grant_family` | $9,000 | `hdb-grant-family-ehg` | "must not exceed $9,000" (first-timer households) |
| `enhanced_cpf_housing_grant_single` | $4,500 | `hdb-grant-singles-ehg` | "$4,500 if you are buying a flat on your own" |

Source URLs (from the snapshot `manifest.json`):

- family CPF Housing Grant: https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/couples-and-families/cpf-housing-grants
- singles CPF Housing Grant: https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/singles/cpf-housing-grant
- family EHG: https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/couples-and-families/enhanced-cpf-housing-grant
- singles EHG: https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/singles/enhanced-cpf-housing-grant

**Left unverified:** `proximity_housing_grant` ("no income ceiling"). The snapshot
has only the singles PHG page, and it does not mention income. A page that says
nothing about income does not prove there is no ceiling, so this stays
`verified: false` until someone finds an official statement.

Related variants the snapshot also states (not yet in the JSON):
- $24,000 for extended or multi-generation families (family CPF grant);
- $16,000 for singles buying with family or other singles;
- $9,000 for singles buying with other singles or with parents (EHG).
