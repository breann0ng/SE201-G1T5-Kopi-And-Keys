# Data

Everything the advisor treats as fact comes from this folder: official policy text, real resale
transactions, and the labelled questions it is evaluated on. The model never supplies facts; code
reads them from here, and every answer cites where they came from.

## 1. Overview

```text
 SOURCES                      STORED HERE (data/)                       USED BY (backend/kopi_keys/)
 ───────                      ───────────────────                       ────────────────────────────
 HDB / CPF / MyNiceHome  ──►  policy_snapshots/<date>/  (dated copies)
   websites                       │ chunk.py
                                  ▼
                              policy_chunks/<date>/chunks.jsonl  ──┬──► policy retrieval (keyword ranker)
                                  │ build_policy_index.py          │
                                  ▼                                │
                              chroma/  (vector index, local)  ─────┴──► policy retrieval (vector search)
                                  │ build_cards.py
                                  ▼
                              topic_cards/*.json  ───────────────────► topic cards: matching, suggestions,
                              schema/vocab.json   (shared values)        overview table, clarifying fields

 data.gov.sg resale CSV  ──►  raw/2017-onwards-resale-prices.csv
                                  │ build_resale_db.py
                                  ▼
                              processed/hdb_prices.db  (local)  ─────► price query (SQL statistics)

 HDB grant pages         ──►  rules/income_ceilings.json  (in backend/) ► income-ceiling notes

 Team-written questions  ──►  evaluation/development/   ─────────────► evaluation harness and router test
                              held-out set: outside the repository ──► final evaluation only
```

## 2. Directory map

| Path | Contents | In Git? | Built by | Read by |
|---|---|---|---|---|
| `policy_snapshots/<YYYY-MM-DD>/` | Dated copy of 95 official pages and PDFs: raw bytes, clean text, tables, manifest with hashes | Yes | `scripts/scraping/` (`refresh.py`) | `chunk.py`, `validate.py` |
| `policy_snapshots/ACTIVE` | One line: the snapshot date the advisor serves | Yes | A person, after review | Every loader of chunks |
| `policy_chunks/<date>/chunks.jsonl` | 849 passages with stable IDs, source, dates, tags | Yes | `scripts/scraping/chunk.py` | Retrievers, evaluation |
| `policy_chunks/chunk_id_registry.json` | Keeps chunk IDs stable across snapshots | Yes | `chunk.py` | `chunk.py` |
| `schema/vocab.json` | Shared values for profile fields (citizenship codes, flat types, towns) | Yes | By hand (DRAFT) | Cards, evaluation, frontend |
| `topic_cards/*.json` | 12 discovery cards, each with a verified overview quote | Yes | `scripts/scraping/build_cards.py` | `topic_cards.py` |
| `chroma/` | Vector index of the ACTIVE chunks (EmbeddingGemma) | No (generated) | `scripts/build_policy_index.py` | `HybridPolicyRetriever` |
| `raw/2017-onwards-resale-prices.csv` | data.gov.sg resale transactions | Yes (PR #4) | Downloaded | `build_resale_db.py` |
| `processed/hdb_prices.db` | SQLite database of 242,737 sales | No (generated) | `scripts/build_resale_db.py` | `SqlitePriceTool` |
| `evaluation/development/` | 30 dev questions and generated router labels; `archive/` holds the earlier sets | Yes | By hand; labels by `python -m kopi_keys.evaluation.dataset` | Evaluation harness, `test_development_set_contract.py` |
| held-out questions | 20 final-evaluation questions | **Never** (outside the repository) | A teammate who hasn't tuned the system | `run_eval --split heldout --final` |

Generated files (`chroma/`, `processed/`) are rebuilt on each machine from what *is* committed, so the
repository stays small and every machine builds the same data. Git ignore rules only prevent accidental
commits; they are not a security boundary, which is why held-out questions stay outside the workspace.

## 3. Data flows

### 3.1 Policy: website to answer

1. **Snapshot.** `scripts/scraping/` fetches the allowlisted HDB, CPF and MyNiceHome pages politely
   (robots.txt, 3 s per domain), saves raw bytes with SHA-256 hashes, and extracts clean text and tables
   into `policy_snapshots/<date>/`.
2. **Chunk.** `chunk.py` splits clean text by heading, then by paragraph (about 300 words), keeping a
   figure with its condition; tables split between rows with the header repeated. IDs such as
   `CHUNK_EHG_05` stay stable through the registry.
3. **Index.** `build_policy_index.py` embeds each chunk's heading and content with EmbeddingGemma into
   `chroma/`, one collection per snapshot date.
4. **Cards.** `build_cards.py` builds the 12 topic cards from rules over the chunks, plus one hand-picked
   official sentence per card (`overview`), checked word for word.
5. **Validate.** `validate.py` runs 9 checks (schemas, hashes, vocabulary, figures traceable to source,
   raw files byte-exact, card quotes verbatim). It must pass before anything goes live.
6. **Serve.** `HybridPolicyRetriever` reads the ACTIVE chunks and the index, fuses keyword and vector
   rankings, and returns the top 5 passages; the AI selects verbatim quotes from them and the verifier
   checks every quote and citation.

### 3.2 Prices: CSV to statistics

The data.gov.sg CSV is validated row by row and loaded into SQLite by `build_resale_db.py`; the price
query runs parameterised, read-only SQL for a town, flat type and month range and returns volume, mean,
median, quartiles, IQR, minimum and maximum. No price is ever written by the model.

### 3.3 Income ceilings: HDB pages to notes

`backend/kopi_keys/rules/income_ceilings.json` lists each grant's ceiling with its source and a `verified`
flag. For grant questions where the user's income is known, `check_income_ceiling()` compares it with
each verified ceiling and the answer shows a note, never an eligibility verdict.

### 3.4 Evaluation: questions to scores

`dev_set_questions.jsonl` holds each question with router labels and answer labels (verbatim evidence
resolved to chunk IDs). `stage1_gateway_labels.jsonl` is generated from it. The harness in
`backend/kopi_keys/evaluation/` scores routing, discovery and Recall@5, and end-to-end runs through the
app. See its README.

## 4. Reference

### 4.1 Policy snapshots and the refresh process (DRAFT, to be agreed with the team)

Snapshots are committed so teammates never re-scrape. Each folder has its own README describing scope and
rules, and folders are append-only: a new snapshot is a new folder; old ones are never edited.
**`policy_snapshots/ACTIVE`** names the snapshot the advisor serves. Code must read this file, never "the
newest folder". Only a person changes it, after review; to roll back, set it to an earlier date.

1. **Re-snapshot (automatic).** `.github/workflows/policy-refresh.yml` runs `scripts/scraping/refresh.py`
   at 10:00 SGT on the 1st of each month and pushes the new folder straight to `main`, **not live**. Run it
   manually from the Actions tab after an announced policy change (Budget, National Day Rally, a BTO launch).
   If the run fails (e.g. a site blocks it), nothing is pushed; run `python refresh.py` locally and commit.
   After the 1st, run `git pull` before pushing, because the bot will have added a commit.
2. **Alert (automatic).** `diff.py` compares the new snapshot with ACTIVE and writes
   `changes_since_<ACTIVE date>.md`, listing pages whose dollar, year or age figures changed first. If
   anything changed, the workflow opens a GitHub Issue with a review checklist.
3. **Review.** A person checks each change against the live page; for each real change, mark the old
   chunks `superseded: true` and re-check any topic card citing them. The verifier rejects superseded sources.
4. **Go live.** Set ACTIVE to the new date, then rebuild:
   `cd scripts/scraping && python chunk.py && python build_cards.py && python validate.py`, then
   `python scripts/build_policy_index.py`. Note the review outcome in the snapshot's README, push, and close
   the issue. If the snapshot looks broken, leave ACTIVE unchanged and close the issue with a note.

### 4.2 Freshness fields

Policy records keep stable IDs, source URL, snapshot version and superseded status. An effective date is
never inferred from a crawl date.

| Field | Meaning |
|---|---|
| `snapshot_date` / `fetched_at` | When the text was last seen live |
| `last_updated_printed` / `page_last_updated` | The page's own "Last updated" line, verbatim, or null |
| `effective_date` | Only when the page states one, otherwise null |

Answers show the snapshot date ("according to HDB, as of 15 Oct 2026") and link to the live page.

### 4.3 Policy chunks, retrieval and topic cards

See `policy_chunks/README.md` (chunking rules and known limits) and `topic_cards/README.md` (card schema
and matching rules). The app never uses fictional evidence: test-only passages live in `tests/fakes.py`.

### 4.4 Resale transactions (Price Query Tool)

1. Download the CSV from data.gov.sg: [Resale flat prices based on registration date from Jan-2017
   onwards](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view). Use only this file: the
   older files use approval dates (1990 to Feb 2012) or a different or missing `remaining_lease` format.
2. Save it as `data/raw/2017-onwards-resale-prices.csv` (already committed in PR #4).
3. Build the database, recording the download date:

   ```bash
   python scripts/build_resale_db.py --downloaded-on YYYY-MM-DD
   ```

   Every row is validated first; one bad row rejects the import and leaves any existing database
   untouched. Output: `data/processed/hdb_prices.db` (override with `KOPI_RESALE_DB`). Team snapshot:
   downloaded 2026-10-14, 242,737 sales, 2017-01 to 2026-10 (October partial).
4. Query it (dates default to the last 12 months, as in the graph):

   ```bash
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM"
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM" \
       --question "What are 4-room prices in Tampines?" --output .local/tampines.json
   python -m kopi_keys.cli --input .local/tampines.json   # full graph with Ollama
   ```

`SqlitePriceTool.query()` returns `PriceResult` (`schemas.py`). Quartiles use inclusive linear
interpolation (Excel `QUARTILE.INC`); mean, median and IQR are rounded once to cents. Zero matches return
`volume: 0`. Unknown towns or flat types and dates outside the data raise `InvalidPriceFilterError` (a
`ToolUnavailableError`, so the graph stores it in `price_error`), with suggestions. `is_low_volume()` flags
fewer than 10 sales. An absent dataset is never replaced with invented price figures.

### 4.5 Income ceilings

Tasha's `rules/income_ceilings.json` originally cited a secondary blog with every figure
`verified: false`. On 2026-10-16 each figure was checked against the official HDB page in snapshot
`2026-10-15` (verbatim text in `policy_snapshots/2026-10-15/clean/<slug>.md`); the four below now cite HDB,
with `checked_on: "2026-10-15"` and `verified: true`. **Only the source fields changed; no ceiling value
changed.**

| Scheme key | Ceiling | Snapshot slug | Official wording |
|---|---|---|---|
| `cpf_housing_grant_family` | $16,000 | `hdb-grant-family-cpf-housing-grants` | "must not exceed: $16,000" |
| `cpf_housing_grant_single` | $8,000 | `hdb-grant-singles-cpf-housing-grant` | "$8,000 if purchasing a flat on your own" |
| `enhanced_cpf_housing_grant_family` | $9,000 | `hdb-grant-family-ehg` | "must not exceed $9,000" (first-timer households) |
| `enhanced_cpf_housing_grant_single` | $4,500 | `hdb-grant-singles-ehg` | "$4,500 if you are buying a flat on your own" |

Sources: [family CPF Housing Grant](https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/couples-and-families/cpf-housing-grants),
[singles CPF Housing Grant](https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/singles/cpf-housing-grant),
[family EHG](https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/couples-and-families/enhanced-cpf-housing-grant),
[singles EHG](https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/singles/enhanced-cpf-housing-grant).

**Left unverified:** `proximity_housing_grant` ("no income ceiling"). The snapshot has only the singles PHG
page, which does not mention income; silence does not prove there is no ceiling. Unverified ceilings are
never shown to users.

**Not yet in the file**, though the snapshot states them: $24,000 for extended or multi-generation
families (family CPF grant); $16,000 for singles buying with family or other singles; $9,000 for singles
buying with other singles or with parents (EHG).

### 4.6 Evaluation data

The development set is committed so the team can reproduce routing and evaluation results. The held-out
set must not be used while tuning routing, extraction or prompts: keep its questions and labels outside the
workspace and provide them only for the final evaluation (`KOPI_HELDOUT_DIR`). See
`evaluation/development/README.md` and `backend/kopi_keys/evaluation/README.md`.

## 5. Rules for adding or changing data

- Facts come from a dated official source, cited by chunk ID; never from memory or a model.
- Keep stable IDs; mark replaced text `superseded`, never delete it from an old snapshot.
- Never infer an effective date from a crawl date.
- Record every import's source, download date, coverage and schema.
- Never replace missing data with invented figures; say it is unavailable.
- Run `validate.py` and the tests after any change to snapshots, chunks or cards.

## 6. Change log: Sandra's changes to teammates' code (please review)

By architecture layer. Code was only added to, or replaced with tested equivalents.

| Layer | File (owner) | Change |
|---|---|---|
| Data | `rules/income_ceilings.json` (Tasha) | Four ceilings verified against HDB (section 4.5); old blog source kept in each note |
| Data | `evaluation/development/` (Breann) | Dev set replaced by the combined 30 questions; router labels generated from it; earlier sets in `archive/` |
| Retrieval | `components/policy_retrieval.py` (Nisha, PR #5) | Keyword ranker replaced by a general one fused with EmbeddingGemma vectors (`HybridPolicyRetriever`); `SnapshotPolicyRetriever` renamed `KeywordPolicyRetriever`; the fictional `DemoPolicyRetriever` moved to `tests/fakes.py` |
| Router | `components/query_router.py` (Breann) | Recognises Option to Purchase, spouse and pass questions, "confirm we are eligible" (declined), "with our grants"; "not Singaporean" no longer read as the user's citizenship |
| Router | `components/query_router.py` (Breann) | Reads the period a price question names ("in 2025", "last half of 2025", "January to June 2026", "this year", "past 6 months") into `start_month` / `end_month`; before, every price question used the last 12 months, so "in 2012" got 2025 prices. A year outside the data now gets an honest "outside the dataset" decline |
| Graph | `main.py`, `graph.py` (Breann) | App uses `HybridPolicyRetriever`; evidence `mode` declared by the retriever, `data_mode` kept as an override |
| Graph | `graph.py`, `schemas.py`, `state.py` (Breann) | Topic cards connected to answers: overview table for broad questions, up to three cited suggestions, income-ceiling notes, sidebar hint for discovery questions (`overview`, `related`, `income_notes`, `profile_hint`); logic in Sandra's `components/topic_cards.py` |
| Graph | `graph.py` verifier step (Breann) | When a draft fails, quotes that pass every check on their own are kept if the trimmed answer passes in full (no ~60 s repair); a repair, then a decline, still follow when no quote passes. Tests in `test_graph.py` |
| Retrieval | `components/policy_retrieval.py` (Person 2 / Sandra) | Worked examples (HDB's fictional households, 4 chunks: EHG_12, 14, 23, 26) score x0.3 unless the question asks for an example; they had outranked the rules and led the model to stitch an invented quote. Test in `test_discovery_connections.py` |
| UI | `lib/sourceContent.ts`, `MarkdownText.tsx` (Sandra) | Table rows split by a line break inside a cell are rejoined for display (answers, related passages, full source tables); stored text unchanged |
| Rules | `rules/income_ceilings.json`, `rules/income.py` (Tasha) | Each verified grant gains `conditions`: HDB's ceiling variants verbatim (e.g. $24,000 extended families; EHG half-income rule for first-timer + second-timer couples; singles buying with parents). `IncomeCheck.conditions` carries them and the message points to them; values and `verified` flags unchanged. PHG left unverified: no HDB page in the snapshot states its income rule. Test: `tests/test_income_conditions.py` checks each condition is verbatim in the snapshot |
| API | `main.py` (Breann) | `POST /chat/stream` (newline-delimited JSON: each finished graph step, then the same response as `/chat`); in-memory response cache keyed on the whole request plus the ACTIVE snapshot (`KOPI_RESPONSE_CACHE`); model warm-up at startup (`KOPI_WARM_UP`). Tests in `test_api.py` |
| AI client | `llm.py` (Breann) | `keep_alive` configurable (`KOPI_OLLAMA_KEEP_ALIVE`, default 30 min, was 5 min); `warm_up()` loads the model with the policy context size |
| UI | `Progress.tsx` (Sandra), `adapter.ts`, `api.ts`, `Thread.tsx` | Live progress while answering: each finished step ticked, the current one named, seconds counted; a failed check says a corrected quote is being requested |
| UI | `Overview.tsx` (Sandra), `MarkdownText.tsx` | Related passages render as Markdown (tables, bullets), full text in a scroll box |
| State | `state.py` (PR #5, Nisha) | A reply giving several requested values in order ("22, 5000" to "Please provide: age, household income.") resumes the original question |
| Synthesis | `components/synthesiser.py` (Breann) | Passes the topic-card suggestions into the answer |
| Synthesis | `components/policy_synthesis.py` (Nisha) | Passage budget configurable (`KOPI_POLICY_MAX_PASSAGES`, `KOPI_POLICY_MAX_WORDS`); default 800 words (was 1,100) after measuring ~45% faster answers with the same 8/8 verified |
| Verification | `components/verifier.py` (Breann; quote checks by Nisha) | Overview rows must quote their source verbatim; an AI quote ending in ":" (a lead-in) is rejected and repaired; a word the source hyphenates across lines ("first-⏎timer") now matches its quote, which was wrongly rejected before |
| Rules | `rules/income.py` (Tasha) | Called, not changed: `check_income_ceiling()` runs for grant and discovery questions with a known income; verified ceilings only |
| Evaluation | `backend/kopi_keys/evaluation/` (Breann's placeholders) | Placeholders filled with the working harness |
| Tests | `test_graph.py`, `test_api.py`, `test_price_stats.py` (Breann); `test_policy_advisor.py` (Nisha) | Use `tests/fakes.py`; table tests pin HDB's citizenship table and the ranking test checks the hybrid retriever |
| Config and docs | `pyproject.toml`, `.env.example`, `README.md`, `docs/` (Breann, Nisha) | Optional `rag` extra; `KOPI_OLLAMA_NUM_THREADS=8` and power-mode tip; retrieval and evaluation docs |
