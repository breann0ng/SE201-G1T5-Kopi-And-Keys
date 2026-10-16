# Data integration (not connected yet)

Planned local directories, excluded from Git:

- `raw/`: downloaded official policy snapshots and resale transaction CSVs.
- `processed/`: normalized policy chunks, topic cards and the resale SQLite database.
- `chroma/`: generated vector index.

Policy records should preserve stable IDs, source URL, effective date, snapshot
version and superseded status. Do not infer an effective date from a crawl date;
decide how unknown dates are represented before loading official pages.

Transaction imports should record their source, download date, coverage and schema.
The SQLite adapter will accept validated filters and use parameterised read-only
queries. An absent dataset must not be replaced with invented price figures.

The only evidence shipped with this scaffold is fictional and lives in
`backend/kopi_keys/tools/policy.py`.

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
`data/policy_snapshots/2026-10-15/clean/<slug>.md`). On merge, these entries get
the HDB `source_url`, `checked_on: "2026-10-15"` and `verified: true`. **Only the
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
