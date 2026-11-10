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

## 2026-11-07 · Answer feedback loop
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/feedback.py, backend/kopi_keys/main.py,
  backend/kopi_keys/graph.py, backend/kopi_keys/schemas.py,
  frontend/src/components/FeedbackControls.tsx,
  frontend/src/components/Thread.tsx, frontend/src/lib/api.ts,
  frontend/src/pages/SettingsPage.tsx, scripts/review_feedback.py,
  docs/feedback-loop.md, docs/responsible-ai.md, .gitignore,
  tests/test_feedback.py, tests/test_review_feedback.py, tests/test_api.py,
  tests/conftest.py, tests/fixtures/feedback_isolation_baseline.json
- **Outcome:** Changed

### What I asked for
Thumbs up/down under every answer with an optional reason and comment,
recorded for the team to review: on the answer's LangSmith trace (primary)
and in a git-ignored local SQLite backup, through a write-only
POST /api/feedback. Feedback must never change answers, prompts, retrieval,
routing, topic cards, the price tool or the model. Also a fallback review
script, a doc covering the review and fix process, and tests proving
isolation. Investigate first and wait for my OK before editing.

### How I checked it
Ran the app and clicked thumbs up and down on several answers. I found I could
keep switching between the two, and asked whether that should be allowed. I
found the reason I had typed on the answer's trace in LangSmith. Teammates'
review on PR #17 found duplicate feedback items and a run id taken from the
browser; both were fixed (below) before merging.

### What I kept or changed
After its investigation I changed the plan in four ways. /chat keeps calling
run_chat, which gained an optional run_id that only goes into the graph
config (it had proposed calling graph.invoke directly, which would skip
run_graph's state validation and recursion limit). I dropped the
browser-supplied question/answer fallback: context comes only from a
bounded in-memory map of the last 1000 answers, and a miss is stored with
context_missing=1. I asked for regression tests against answers captured
on main before the change, and for a cache hit to keep the original trace
id with a new message_id. I approved the Settings wording and the
responsible-AI Feedback bullet. Choices it made that I kept: ratings must
be exactly the integers 1 or -1 (Pydantic otherwise accepts true and 1.0);
the server's own trace id wins over the browser's copy; feedback does not
extend LangSmith trace retention; a database error returns 503 without
affecting chat. Two existing cache tests in test_api.py now ignore
message_id. After review on PR #17 (2026-11-08) I changed two things: a later
click now updates one LangSmith feedback item (id derived from message_id)
instead of adding another, and the run id comes only from the server, so
requests that include one are rejected and unknown messages are saved locally
without calling LangSmith.

## 2026-11-09 · Testing the system and diagnosing failures from traces
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none changed (the diagnosis led to the PRs below)
- **Outcome:** Kept

### What I asked for
A check of where the codebase stood, stress-test questions, and help working
out from LangSmith traces why some policy answers declined.

### How I checked it
Ran the stress questions in the app myself and pasted the outputs and traces
back. Re-asked the failing questions after clearing my sidebar profile, which
showed the stale profile was only part of the cause.

### What I kept or changed
Kept the diagnosis: a stale sidebar profile could override the message, and
the verifier's word-overlap relevance check rejected correct quotes. These
became PR #31 (mine) and Nisha's context-relevance PR #34. Forecast and
guarantee wording, latency and stacking over-refusal were listed as known
limitations, not fixed.

## 2026-11-09 · Price answers say which months have no data (PR #29)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/price_query.py, price_display.py,
  graph.py, tests/test_price_missing_months.py, tests/test_price_wording.py,
  tests/test_eval_routes.py, tests/test_integration_gaps.py
- **Outcome:** Changed

### What I asked for
I noticed "past 6 months" asked in November showed Jun–Nov although our data
ends in October. I wanted the answer to use the user's current date and say
which months have no data yet.

### How I checked it
I found the problem by asking "past 6 months" in the app, and asked for the
answer to name the missing months rather than just shorten the period. Reviewed
the plan before it was built. Nisha's integration test expected the old period,
so I told her before it was updated.

### What I kept or changed
Kept: the period is capped at the latest month in the database and the answer
names the missing months. Its first version failed the verifier's month check
(the stated period no longer matched the figures), so the graph now records the
months actually used.

## 2026-11-09 · Verifier rejecting correct, differently worded quotes (PR #31)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/policy_guardrails.py, verifier.py,
  scripts/mutation_test_policy.py, tests/test_verifier_relevance_wording.py
- **Outcome:** Changed

### What I asked for
Why a correct PR-spouse answer was rejected as "not relevant" (score 0.17
against a 0.20 threshold), and how to make the check less literal without
letting wrong quotes through.

### How I checked it
Found the rejected answer in the LangSmith trace (relevance 0.17 against the
0.20 threshold) and pasted it back. The fix was checked with new tests for
differently worded quotes and the policy mutation script (21/21 mutants caught
after the update).

### What I kept or changed
Kept synonym groups for the relevance check (e.g. spouse/married) and a rule
that accepts a table row answering the question. Nisha later narrowed that rule
to citizenship rows only. The mutation script's anchor broke after the change;
it was updated and a mutant for the new rule added.

## 2026-11-09 · Relevance and reranker experiments (not adopted)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none merged; scripts and results kept in my local .local/evidence/
  (calibrate_semantic_relevance.py, calibrate_cross_encoder.py, reranker.patch)
- **Outcome:** Rejected

### What I asked for
Whether a meaning-based relevance check (EmbeddingGemma similarity or a
cross-encoder) would beat word overlap, and whether a cross-encoder reranker
would improve retrieval.

### How I checked it
Ran the calibration scripts and the retrieval report on my laptop on the dev
set, after rebuilding my out-of-date search index (it was missing 195 chunks).
We agreed the pass mark before running the reranker.

### What I kept or changed
Rejected all three. Word overlap rejects 17/42 correct quotes. EmbeddingGemma
scores for right and wrong quotes overlap too much. The cross-encoder separates
best (AUC 0.90) but as a gate lets 12–36% of wrong quotes through. The reranker
made retrieval worse (Hit@5 81.8% → 68.2%, 148 → 799 ms). I deleted the branch
and kept the results for the slides. Nisha ran the temperature experiment from
instructions it wrote; we kept temperature 0.

## 2026-11-10 · Remove the Settings page; light mode only (PR #32)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** frontend/src/pages/SettingsPage.tsx, components/Layout.tsx,
  ProfilePanel.tsx, AnswerTrace.tsx, lib/theme.ts, main.tsx,
  docs/chat-ux.md, docs/responsible-ai.md
- **Outcome:** Changed

### What I asked for
Remove the Settings page and keep light mode only.

### How I checked it
Reviewed what would move and what would be removed, then approved the merge.
"Clear my data" and the data note had to stay available, so they moved into the
profile sidebar.

### What I kept or changed
Kept as built. "Clear my data" moved into the sidebar rather than being
removed.

## 2026-11-10 · Final presentation deck and demo script
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none in the repository (presentation deck, demo script)
- **Outcome:** Changed

### What I asked for
Slides from our template for the final presentation, later updated with the
final dev and held-out numbers, the experiments, the feedback loop and a
clearer pipeline than the AI-generated image I had added. Also a demo script
merged with Breann's draft.

### How I checked it
Gave it Nisha's dev and held-out outputs rather than letting it reuse old
numbers. It flagged that the dev price figure was 18/18 in one run and 18/21 in
another, to confirm with Nisha. I dry-ran the demo questions in the app, which is
how I found the PR-spouse and "be cheaper" problems.

### What I kept or changed
Replaced the AI-generated pipeline image with three diagrams checked against
graph.py; the image had an unrelated logo and paths that do not exist. Cut the
grants scene and the PR-spouse question from the demo after a dry run quoted
the non-resident spouse rule. A forecast worded "be cheaper next year" was
answered with past prices because the forecast rule doesn't cover that word;
that is now a listed limitation, not a fix, because the held-out run was
already done.

## Reflection

### What I learned about using these tools effectively
The most useful habit was asking the assistant to investigate and explain its
plan before changing anything. For the feedback loop, its first plan would have
called the graph directly and trusted IDs sent by the browser; because I asked
for the investigation first, I could change the plan before any code existed.
The same worked for the price "Narrow it down" form. It is much easier to
correct a plan than to unpick finished code.

The hardest problem in the project wasn't a coding one. Housing advice has to be
right: a wrong grant amount or an outdated rule could cost a buyer money, so we
made the system quote official text word for word and had code check every
quote and number. The cost was rigidity. The relevance check rejected correct
answers that used different words from the question ("spouse" against "married"),
and teammates said the chatbot felt stiff. The tools were most useful here for
trying different approaches quickly and measuring them rather than guessing. We
added synonym groups to the word check. We tested whether EmbeddingGemma
similarity or a cross-encoder could judge relevance by meaning, and whether a
reranker would find better passages. We also tested higher model temperatures.
The cross-encoder separated right from wrong quotes best, but as a pass/fail
check it would have let too many wrong quotes through. The reranker made
retrieval worse, and a higher temperature only helped one case. We kept the
safer options and reported the rest. I learned that AI can build and run these
experiments in an evening, but deciding the trade-off is our job. It works best
when we agree the pass mark before seeing the results.

### Where the tools were strong, and where they were weak
They were strongest at testing and debugging. Mutation testing raised the share
of injected bugs our price tests caught from 66% to 96%, and reading LangSmith
traces with the assistant showed why correct policy answers were being declined
(a stale profile and a too-literal relevance check). Their weakness was being
confident but wrong. It gave a cause for a checkpoint failure that we had not
confirmed, numbers went stale when copied between documents, and an AI-generated
pipeline image showed paths our code doesn't have. It never said it was unsure,
so I learned to check claims against the code, the data or a real run before
using them.

### What went wrong, and what I would do differently
Early on I accepted AI-written work that looked finished without checking where
it came from. The income ceiling rules it wrote for the price tool cited a
property blog with outdated figures, and Sandra caught it before anything relied
on them. The same thing happened on a smaller scale near the end: a demo question
that had worked in testing quoted the wrong rule on the day, because I hadn't
re-checked it against the latest code. Next time I would require an official
source for every rule before committing it, and re-run anything I plan to show
after the last change, rather than trusting that it still works.
