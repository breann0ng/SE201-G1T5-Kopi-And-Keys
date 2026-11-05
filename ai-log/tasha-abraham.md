# AI Use Log: Tasha Abraham

## 2026-10-14 · Architecture advice on the Discovery step
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none changed (advice only)
- **Outcome:** Changed

### What I asked for
Explanations of our prof's question about Discovery: whether it needs to be
a separate agent, whether it needs an LLM, whether it should ask the user
before or after answering, and whether our design is a multi-agent system
or a workflow.

### How I checked it
Compared the answers with our proposal diagram (Appendix C) and the prof's
feedback, and discussed them with the team before anything was built.

### What I kept or changed
Kept the point that a fixed workflow with one LLM step is enough for us.
The team decided to merge Discovery into the Synthesiser rather than keep a
separate agent, so I did not use the separate-agent version it first drew.

## 2026-10-16 · SQLite price tool, resale DB and income ceiling rules
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/price_query.py,
  scripts/build_resale_db.py, backend/kopi_keys/rules/,
  tests/test_resale_db.py, tests/test_price_stats.py,
  tests/test_income_rules.py, data/README.md,
  data/raw/2017-onwards-resale-prices.csv
- **Outcome:** Changed

### What I asked for
The price query tool from our midpoint plan: a SQLite database built from
the data.gov.sg resale prices (Jan 2017 onwards), a read-only query that
returns median, mean, IQR, min, max and volume, and the income ceiling
checks.

### How I checked it
I chose and downloaded the dataset myself (242,737 rows, 2026-10-14). I had
it compare the code with Breann's interface spec, and it found and fixed
mismatches before I pushed. The tests use hand-computed statistics, and the
Tampines 4-room figures were recomputed straight from the CSV. Sandra later
found the income ceilings it wrote cited a property blog with outdated
figures; they were marked unverified, so nothing relied on them yet.

### What I kept or changed
Kept the tool and the builder (which reuses Breann's validated importer).
The income ceilings were replaced with HDB's own figures (Sandra's entry).
I committed the CSV so everyone builds the same database.

## 2026-10-16 · Chatbot errors and missing towns in the router
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py
- **Outcome:** Kept

### What I asked for
Why the chatbot returned HTTP 500, and how to run Ollama and the app.

### How I checked it
Ran the app myself. The 500 came from the backend not running, which went
away once it was started. Asking price questions then showed some towns were
not recognised; after the fix, all 26 towns routed and the dev routing
labels still passed.

### What I kept or changed
Kept the fix (all 26 resale towns plus common aliases, and the price
database connected to the graph).

## 2026-10-17 · Price answers: buttons, breakdown and router fixes (PR)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/query_router.py, price_query.py, price_display.py,
  schemas.py, state.py, graph.py, frontend/src/components/QuickReplies.tsx,
  AnswerExtras.tsx, PriceRefine.tsx, frontend/src/lib/api.ts, adapter.ts,
  priceBands.ts, pendingPriceFilters.ts, tests/test_price_*.py,
  tests/test_query_router.py, tests/test_api.py
- **Outcome:** Changed

### What I asked for
Fixes for problems I found while testing price questions in the app: "how
much is a flat in Toa Payoh" was declined, answers showed an internal query
ID and one wide range, and I suggested a form to narrow the figures by
remaining lease and floor.

### How I checked it
Tested each change in the app. I spotted that a narrowed figure looked
cheaper than expected and asked for it to be checked; the figures matched
the CSV (Toa Payoh 5-room: 143 sales, median $1,050,000; 80+ years left and
high floor: 23 sales, median $1,490,000). I found a maisonette question
being answered with an unrelated grant table, and asked whether the form
conflicted with our dev-set case that declines unit valuations. 240 tests
pass and all 30 dev routing labels still pass.

### What I kept or changed
I asked it to explain its proposed form before building it. Following
the dev-set case, fewer than 5 matching sales now lists the sales instead of
giving a median, and the button says "Update figures", not "estimate". A
block-level lookup was proposed but I left it out for now.

## 2026-10-17 · Checkpoint report sections A to C and architecture diagram
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** checkpoint report (sections A, B, C), architecture diagram
- **Outcome:** Changed

### What I asked for
Drafts of sections A to C from what we had actually built and measured, and
an updated architecture diagram in the style of our proposal's Appendix C.

### How I checked it
Checked the claims against the code and Sandra's evaluation results
(routing 100%, Recall@5 60%). Sent the failure rows and the DSC-02 cause to
Sandra to confirm, and the Streamlit-to-React and qwen2.5:3b reasons to the
team.

### What I kept or changed
It first gave a cause for the DSC-02 failure that we had not confirmed;
changed to "not yet diagnosed". Fixes still in review are marked as such.

## 2026-10-31 · Dev set expansion (30 to 50), price scoring and held-out guide
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/price_query.py, graph.py (one line),
  backend/kopi_keys/evaluation/ (dataset.py, metrics.py, run_eval.py, README.md),
  data/evaluation-data/development/, data/evaluation-data/question_template.jsonl,
  docs/heldout-guide.md, .gitignore, tests/test_price_stats.py,
  tests/test_eval_routes.py, tests/test_development_set_contract.py
- **Outcome:** Changed

### What I asked for
A summary of how the dev set labels price questions and what run_eval scores,
then 20 new dev questions aimed at known weak spots, with price figures
computed by SQL straight on the database and policy quotes copied word for
word from the ACTIVE snapshot. Also price-filter and price-figure checks in the
evaluation, a fix to my default price window and impossible-period handling,
and a guide and template for the 40-question held-out set kept outside the repo.

### How I checked it
Ran the test suite (338 passed, 4 expected router-gap failures) and the bm25 evaluation myself. Checked four price answers in the app against the expected figures, including that the default period ends at Oct 2026 and that “in 2028” is declined. Read a sample of the new labels and confirmed the EHG row on HDB’s PDF. Made the decisions on the period convention, the CHG questions and the MIX-08/DSC-06 rewording.

### What I kept or changed
It found that run_eval checked neither price filters nor figures, and that 9
existing labels used a different period from the app. I kept the app's
convention, fixed those labels, and had my default window anchored to the
latest month in the database. I replaced its two new-flat (BTO) policy-change
questions with resale ones, reworded MIX-08, added the owned 2-room to DSC-06,
swapped OOS-06 for a "next year" forecast, and narrowed CHG-06's superseded
value to "initial payment is 20%". The router was not tuned: MIX-07, DSC-06,
OOS-06 and OOS-07 are listed as known router gaps, and the `_cap` future-year
bug goes to Breann.

## 2026-11-05 · Mutation testing on the price tool and a draft CI workflow
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** scripts/mutation_test.py, tests/test_price_boundaries.py,
  tests/test_price_wording.py, docs/testing-price-tool.md,
  .github/workflows/ci.yml, backend/kopi_keys/ingest/resale_db.py,
  tests/test_resale_db.py
- **Outcome:** Changed

### What I asked for
Mutation testing limited to my price modules (price_query.py, price_display.py)
and their tests, with every surviving mutant marked equivalent or not, and a
test with hand-checkable literal values for each one that is not. Also a draft
CI workflow for the team (pytest without Ollama, frontend lint and build,
report-only dependency audits, gitleaks), not to be merged without agreement.

### How I checked it
Ran the full suite and the mutation script myself (66.4% → 95.9%). Checked the lease and floor boundary tests by hand (720/960 months, storeys 6/7 and 12/13, the 4-vs-5 sales rule). Read the reasons for the 15 equivalent mutants. Decided to reject storey 00 at import rather than test around it. Reviewed the CI workflow’s permissions (read-only, no secrets, no held-out).

### What I kept or changed
It used a small standard-library AST script instead of mutmut, which does not
fit our backend/ layout and skips the module-level band constants. The score
went from 66.4% (259/390) to 95.9% (374/390). It marked 15 of the 16 survivors
as equivalent and left one for me to decide: a sale on storey 00 fell in no
floor band. I decided the importer should reject storey 00, which makes that
mutant equivalent too; the rebuilt database is unchanged at 242,737 rows. In the
draft CI workflow I changed setup-python from v7.1.0 (two weeks old) to v7.0.0
and kept the gitleaks step as it was. The workflow stays a draft on this branch
until the team agrees.
