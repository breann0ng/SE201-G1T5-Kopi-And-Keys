# Policy snapshot — 2026-10-15 (SGT)

Official HDB/CPF housing-policy pages for the Kopi & Keys advisor. The snapshot is committed to git so
teammates don't need to re-scrape. Owner: Person 4. Status: **awaiting review**. This is the ACTIVE snapshot (see `../ACTIVE`). Do not chunk until approved.

## Scope (agreed by Person 4, 2026-10-15)

| Area | What | Sources |
|---|---|---|
| hdb.gov.sg | every page under `/buying-a-flat/` in HDB's sitemap: eligibility, grants, loans, HFE, resale, BTO/SBF, ECs, financial planning, EIP/SPR quota | 63 pages |
| hdb.gov.sg PDFs | policy PDFs linked from those pages: EHG amounts (families, singles), extended-family income ceiling, OTP Important Notes, Resale T&Cs, ECF T&Cs | 6 PDFs |
| mynicehome.gov.sg | all `/get-started/` guides | 12 pages |
| cpf.gov.sg | all `/member/home-ownership/` pages, plus 2 explainer articles | 14 pages |

**Total: 95 sources.**
- `scripts/scraping/seeds.json` has the first 18 seed pages plus the 70 pages added by `discover.py` from the cached sitemaps.
- Interactive tools are excluded: planners, calculators and e-services.
- Some linked PDFs were skipped:
  - EC project lists, an EC land-sales list and a booking authorisation form (not policy)
  - an aic.sg form (not on the allowlist)

**Non-Singaporean audience.** The advisor also serves PRs and people buying with non-citizens. These pages carry those rules:

| Topic | Pages |
|---|---|
| SC/SPR households, non-resident spouse, parent or child | `hdb-elig-couples-families`, `hdb-elig-singles` |
| Grant amounts by citizenship (SC/SC vs SC/SPR) | `hdb-grant-*` |
| SPR quota for resale flats | `hdb-process-for-buying-a-resale-flat-resale-flat-planning-eip-and-spr-quota` |
| EC eligibility | `hdb-executive-condominiums-*` |

No page captured here states rules for foreigners buying on their own. Don't infer any; the advisor should say so instead.

## Source tiers

Tiers are set in `scripts/scraping/extract.py` (`SOURCE_TIERS`) by URL prefix. When sources disagree,
prefer the lower number. This ranking was decided by Person 4 on 2026-10-15.

| Tier | Sources | Count |
|---|---|---|
| 1 | HDB scheme pages and HDB PDFs, CPF `/member/home-ownership` pages | 81 |
| 2 | MyNiceHome guides, which summarise HDB pages | 12 |
| 3 | CPF infohub explainer articles | 2 |

`last_updated_printed` is the verbatim "Last updated …" text printed on a page. It is a page-revision
date, **not** a policy effective date. HDB pages print none, and their CMS `publishedDate` is empty, so the field is null for them.

## How

| Script | What it does |
|---|---|
| `discover.py` | Adds in-scope URLs from the cached sitemaps to `seeds.json`. No network. |
| `fetch.py` | Handles robots.txt, sitemaps, pages, PDFs and Playwright renders. It is sequential, waits at least 3 s per domain, caches everything, and logs every request with its User-Agent to `fetch_log.json`. **105 fetches** in total. |
| `extract.py` | Writes `clean/*.md`, `tables/*.csv` and `manifest.json`. No network. |
| `verify.py` | Diffs the `$` amounts, "N years" and "age N" figures between each source and its clean text, and writes `verification.json`. |

Rerun: `cd scripts/scraping && .venv/Scripts/python fetch.py seeds && .venv/Scripts/python extract.py && .venv/Scripts/python verify.py`.
A rerun on the same date re-fetches nothing. A run on a new date writes a new snapshot folder.

**Fetch cap.** It was 30 for the first pass. Person 4 raised it to **200** on 2026-10-15. It is now a safety stop
against runaway loops, not a budget.

**hdb.gov.sg access (approved by Person 4, 2026-10-15).** The plain research User-Agent got HTTP 403 on
robots.txt; that attempt is kept in `fetch_log.json` → `robots_history`. hdb.gov.sg requests then used a
browser-compatible User-Agent that still names the project: `... (compatible; SMU-SE201-StudentResearch/0.1 ...)`.
The other rules still applied:
- robots.txt was obeyed. It disallows only e-service paths.
- The rate limit still applied.
- The fetcher aborts on 401/403/429 or a CAPTCHA/challenge page. None occurred.

**`nextdata` method (63 HDB pages).** HDB pages are Next.js/Sitecore pages. Their static HTML is mostly navigation, and
the real body ships in the same response inside `<script id="__NEXT_DATA__">`. `extract.py` rebuilds the
body from the PageHeader, BodyContent and AccordionWrapper components, in page order, and writes it to `derived/<slug>.html`.
Navigation components (Cards, AdvisoryBanner, etc.) are skipped and named in each page's notes.
`verify.py` confirms that no figure in `__NEXT_DATA__` is missing from the clean text.

## Known gaps and flags

- **Not captured: `hdb-pdf-ecf-terms-conditions`.** The PDF has no text layer and would need OCR.
- **Thin by design:**
  - 11 HDB section landing pages, which are navigation cards only
  - the CPF "apply to use CPF" link hub
  - the CPF housing case study, which is an interactive widget
- **Hard-to-read PDF text:** `clean/hdb-pdf-income-ceiling-extended-family.md` interleaves its multi-column table text.
  Use the matching `tables/*.csv` or the PDF.
- **Figures that differ in detail between sources** (not resolved; see the `manifest.json` notes):
  - **Family Grant:** MyNiceHome says "Up to $80,000". HDB gives SC/ SC: $80,000 and SC/ SPR: $70,000.
  - **Income ceiling:** MyNiceHome gives "$16,000". HDB also gives "$24,000 if purchasing with an extended or multi-generation family".
  - **Resale deposit:** MyNiceHome says Option Fee is "a sum between $1 and $1,000". HDB says "a deposit ($2 to $5,000)".
- **Table quirk:** `tables/mnh-hdb-resale-buying-guide_1.csv` has a column shift caused by merged header cells.
- **CPF banner:** CPF clean pages begin with a temporary "Notice" banner about CPF hotlines.
- **Verification false positives:**
  - "age 55/65" on CPF pages comes from the site navigation menu.
  - `$1`/`$13`-style values on MyNiceHome are React references.
  - "age35" on hdb-grant-singles-ehg comes from the way table cells are split in markdown.
  - "aged35/55" on hdb-flat-grant-and-loan-eligibility comes from navigation-card summaries.
- **Size:** about 25 MB in total, of which `raw/` is 22 MB. One rendered CPF page is about 6 MB.

## Decisions for Day 2 (Person 4, 2026-10-15)

- **Thin pages:** chunk them, but mark them low priority (`low_priority: true`) so they rank below content chunks.
- **Source differences:** cite **HDB (tier 1)** for all three: the Family Grant SC/SC vs SC/SPR split, the
  $16,000 vs $24,000 income ceiling, and the resale deposit "$2 to $5,000". MyNiceHome stays as supporting
  context only. The $1 vs $2 lower-bound mismatch is still listed as an open question for the team.
- **Non-citizen chunks:** tag chunks that cover non-citizen rules for retrieval:
  - the SC/SPR requirement
  - SPR households
  - non-resident spouse
  - EHG (Singles) with a non-resident spouse
  - the EIP/SPR quota
