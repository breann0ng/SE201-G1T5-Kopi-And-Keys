# AI Use Log: Sandra Yap

## Reflection (final submission, 10 Nov 2026)

### What did I learn about how to use these tools effectively?
- Give every task a check the tool cannot talk its way past. The scraper came with
  `validate.py` and checksums, each fixed phrasing came with a regression test, and the tests
  themselves were checked with mutation testing.
- Set the pass mark before the experiment. I wrote the acceptance rule before trying the
  reranker and the meaning-based relevance checks, so the results could not be tuned
  afterwards. Both were rejected by that rule.
- Ask it to recompute, not recall. Slide figures (242,737 sales, the $633,800 median, the
  94 pages) were recomputed from the database and the snapshot manifest instead of copied from
  earlier documents.
- Keep it inside my own area. When my work needed a change in a teammate's file, it worked
  better to have the tool stop and tell me the change, so I could ask the owner.
- Make the important decisions myself and say them explicitly: which scope to scrape, how to
  treat discovery questions, not to edit the answer key, and not to commit or push without
  being asked.

### Where were the tools strong, and where were they weak?
- **Strong:** building a polite scraper and chunker quickly; writing tests and finding untested
  code (mutation scores for my four weakest modules went from 28% to 93%); statistics, where a
  property test it wrote found a real bug in the Wilson interval; fact-checking slides and
  READMEs against the code; explaining concepts I had not used before.
- **Weak:** confident but wrong claims, for example that the embedding prefixes were missing,
  that the suite had 240+ tests (it had 515), a naive-RAG run "about 11 minutes" that took 95,
  and a frontend test count of 31 from a text search when the test runner reported 32. It
  brought in eligibility rules from third-party sites that the official snapshot does not
  state, and first treated executive condominiums as private property. Early on it edited
  teammates' files (a Step-Up ceiling entry, a benchmark remap, graph wiring), which I had it undo.

### What went wrong, and what would I do differently?
- We tuned on the development set for too long. Held-out routing fell from 94% to 80% and half
  of the answerable questions were declined. I would write the held-out set earlier and track
  answer coverage, not only safety, while building.
- Chunking kept old and new rules in one passage, which is why some answers quote an outdated
  rule. I would design chunking around dated clauses from the start.
- A silent fallback hid a problem: when embeddings failed, search became keyword-only but the
  evaluation still called it hybrid. I would make evaluation tools fail loudly from day one.
- Numbers drifted between documents and slides. I would keep one results file per run, commit
  it immediately, and take every figure from it; the final run's files were not committed,
  which left the README and supporting documents depending on the deck.

## 2026-10-15 · Scrape official HDB/CPF pages into a policy snapshot
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** scripts/scraping/*, data/policy_snapshots/2026-10-15/, data/policy_chunks/,
  data/schema/vocab.json
- **Outcome:** Changed

### What I asked for
A polite scraper for HDB and CPF pages (robots.txt, rate limit, cache, log), then
clean text, chunks with stable IDs, and a validation script.

### How I checked it
Agreed the scope (88 pages, 6 PDFs) and source ranking myself. Spot-checked
cleaned pages against the live sites. validate.py passes all checks, and raw
files match their checksums.

### What I kept or changed
I approved a browser-like User-Agent for hdb.gov.sg after HTTP 403s, and raised
the fetch cap from 30 to 200. Kept the rest.

## 2026-10-16 · Topic cards, React UI and PR #3
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** data/topic_cards/, backend/kopi_keys/topic_cards.py, frontend/,
  data/evaluation/, tests/test_topic_cards.py and others
- **Outcome:** Changed

### What I asked for
12 rule-based topic cards, a React chat UI with sources and a profile sidebar,
and a merge of my branch with PRs #1 and #2.

### How I checked it
Ran the UI against the backend and read each card against its HDB page. Fixed
the review findings on PR #3 (byte-exact raw files, stable chunk IDs, held-out
questions moved out of the repo). All tests passed before merging.

### What I kept or changed
Kept Breann's graph and added a thin adapter for the real cards rather than
changing her loader.

## 2026-10-16 · Verify income ceilings against HDB
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/rules/income_ceilings.json
- **Outcome:** Changed

### What I asked for
Check the grant income ceilings, which cited a property blog.

### How I checked it
Compared each figure with HDB's own page in our snapshot. Four matched current
HDB values; the blog had older ones.

### What I kept or changed
Switched the sources to HDB and updated the values. Left PHG unverified because
no HDB page in the snapshot states its income rule.

## 2026-10-17 · Hybrid retrieval and evaluation harness
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/policy_retrieval.py, policy_index.py,
  scripts/build_policy_index.py, backend/kopi_keys/evaluation/*,
  data/evaluation/development/
- **Outcome:** Kept

### What I asked for
Better retrieval than keywords alone, one combined 30-question dev set, and a
harness that scores the real app.

### How I checked it
Recall@5 rose from 35% (old keyword ranker) to 60%. Every dev-set evidence quote
resolves word for word to a chunk. Ran the full evaluation end to end.

### What I kept or changed
Kept the hybrid ranker. Recall is still below the 85% target, noted as open work.

## 2026-10-17 · Show more of the official source in answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** frontend/src/components/*, frontend/src/lib/sourceContent.ts,
  scripts/scraping/build_cards.py, validate.py, data/topic_cards/*.json
- **Outcome:** Changed

### What I asked for
Tables, charts and overviews in answers, using shadcn components.

### How I checked it
Tested in the browser: full source tables, the EHG band chart, overview table,
related passages. Overview quotes are checked verbatim by validate.py.

### What I kept or changed
Chose the order (tables, overview, charts, related passages). Asked for related
passages to render as proper tables, and for "(PDF, 198KB)" labels to be hidden.

## 2026-10-17 · Connect topic cards; clarifying questions only when needed
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/topic_cards.py, graph.py, schemas.py, state.py,
  synthesiser.py, tests/test_discovery_connections.py, test_overview.py
- **Outcome:** Changed

### What I asked for
Use the cards for suggestions and income notes, and stop asking clarifying
questions that the sidebar already covers.

### How I checked it
Asked broad, discovery and grant questions in the browser and read each reply.
New tests cover hints, suggestions and income notes.

### What I kept or changed
I chose option (ii): discovery questions are answered with a sidebar hint, never
a clarifying question. Restricted income notes to grant questions after one
appeared on an HFE question.

## 2026-10-17 · Fix wrongly declined and unsafe answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** query_router.py, state.py, verifier.py, graph.py,
  policy_retrieval.py, tests/test_router_dates.py, test_graph.py
- **Outcome:** Kept

### What I asked for
Why my EHG question ("22, 5000" as the reply) was declined, and why a 2012 price
question got recent prices.

### How I checked it
Replayed my own conversation until it answered with a cited quote. The fixes:
dates read from the question, several values in one reply, PDF hyphenation,
quotes ending in ":" rejected, verified quotes kept when another fails, HDB
worked examples ranked below rules. Evaluation over four runs: unsafe answers
25% to 0%, over-abstention 15% to 8% (target 10%).

### What I kept or changed
Kept all fixes. Nothing unverified is shown; the app still declines when no
quote passes.

## 2026-10-17 · Speed up answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** policy_synthesis.py, llm.py, main.py, .env.example,
  frontend/src/components/Progress.tsx, lib/adapter.ts, lib/api.ts
- **Outcome:** Changed

### What I asked for
Faster answers, and something to show while waiting.

### How I checked it
Timed 8 dev questions per setting, plugged in. The median fell from about 103 s
to 37 s with 8/8 still verified; 2 passages was faster but lost 3 answers. A
repeated question returns in 0 s. Watched the progress steps in the browser.

### What I kept or changed
Set 8 threads in my .env (default stays 4) and chose 3 passages / 800 words.
Added live progress, a warm model and an answer cache rather than switching to
a hosted model.

## 2026-10-17 · Income ceiling variants and recent chats
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** rules/income_ceilings.json, rules/income.py,
  tests/test_income_conditions.py, frontend/src/lib/history.ts, Layout.tsx
- **Outcome:** Kept

### What I asked for
Apply Tasha's open checks myself, and keep past conversations.

### How I checked it
Every ceiling condition is tested word for word against HDB's page. Reopened and
deleted chats in the browser.

### What I kept or changed
Showed HDB's variants (e.g. $24,000 for extended families) rather than guessing
which applies. Values and verified flags unchanged.

## 2026-10-17 · Documentation and project guide
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** data/README.md, backend/kopi_keys/evaluation/README.md,
  frontend/README.md, the team project guide
- **Outcome:** Changed

### What I asked for
A top-down data README, a change log of edits to teammates' files, and a project
guide for the whole team.

### How I checked it
Checked the PR history against git. Corrected PR #4's author (Tasha, not Breann).

### What I kept or changed
Dropped the status column, used names instead of "Person N" labels, and removed
names from change notes in code. Kept owners and decisions named.

## 2026-10-18 · Loan and how-to-buy questions
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/policy_retrieval.py, query_router.py,
  frontend/src/components/MarkdownText.tsx, data/README.md,
  tests/test_discovery_connections.py
- **Outcome:** Kept

### What I asked for
Why loan questions got grant pages, and why "how do I buy a resale flat?"
was declined.

### How I checked it
New tests for scheme focus and discovery routing. Router labels (30/30) and
Recall@5 unchanged. Asked both questions again in the browser.

### What I kept or changed
Retrieval now favours the scheme a question names; "how to buy" questions
route as discovery. Kept the list separator as a display-only change.

## 2026-10-18 · Checkpoint review of docs and architecture diagram
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/evaluation/README.md,
  backend/kopi_keys/ingest/resale_db.py
- **Outcome:** Changed

### What I asked for
An explanation of checkpoint point 4 for our project, a check of our
architecture diagram against the code, and an update of the README and
architecture doc.

### How I checked it
It first described the price tool and policy answers from an outdated doc;
I challenged this and it confirmed both against the code. It found the
diagram's "LLM fallback" router label was wrong (the router is rule-based).

### What I kept or changed
Discarded its README/architecture rewrite because teammates had already
updated both. Kept two small fixes it found when checking them: a stale
dev-set path and an outdated download date.

## 2026-11-06 · Chunking fixes, income-aware cards, tuned hybrid, baselines (PR #16)
<!-- DRAFT from commit messages: check against your own notes before committing -->
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** scripts/scraping/chunk.py, build_cards.py, topic_cards.py, policy_retrieval.py,
  data/policy_index/, evaluation/baselines.py, scripts/go_live.py
- **Outcome:** Changed

### What I asked for
Keep sub-labels ("First-timer singles") and table headers with their text, title PDF pages,
rule cards out by income, tune hybrid fusion, the no-tools and naive-RAG baseline code, and
a helper to switch the served policy snapshot safely.

### How I checked it
validate.py and the test suite; retrieval re-measured after each change. A teammate reviewed
and merged the PR.

### What I kept or changed
Kept. Review found that a benchmark (SYN-08) still pointed at chunk IDs the re-chunking had
retired; Nisha remapped it on main.

## 2026-11-08 · Evaluation harness: baselines, retrieval metrics, synonyms
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** evaluation/run_baselines.py, retrieval_report.py, metrics.py, baselines.py,
  components/policy_retrieval.py
- **Outcome:** Changed

### What I asked for
A read-only review of the repo, then a plan from an adviser prompt: a baseline runner, proper
retrieval metrics, a diagnosis of every miss, and fixes only where the diagnosis supported them.

### How I checked it
Read the miss table myself. Confirmed the old "Recall@5" was really Hit@5 and that the old
eval sent only the first turn of two-turn questions. Synonyms re-measured: keyword search
59% to 64% Hit@5, hybrid unchanged.

### What I kept or changed
Kept the runner, metrics and synonyms. Skipped table-row chunks and fusion tuning because the
diagnosis did not support them (tuning on 22 questions would overfit). The AI estimated the
naive-RAG run at about 11 minutes; it took about 95.

## 2026-11-08 · Review fix: keyword fallback reported as "hybrid"
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/policy_retrieval.py, evaluation tools, tests/test_snapshot_retriever.py
- **Outcome:** Changed

### What I asked for
A fix for a reviewer's finding on PR #18: if the embedding service failed, the eval quietly
used keyword search but still reported "hybrid".

### How I checked it
Two new tests. Re-ran the hybrid report with the real index: same numbers, so earlier results
were genuinely hybrid.

### What I kept or changed
Kept. The app still falls back so users get an answer; only the eval tools now fail loudly.
The AI did not edit Nisha's benchmark file for the related SYN-08 failure; it asked first.

## 2026-11-08 · Topic cards as rules: amount fields, condo exclusion, rule tests
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** topic_cards.py, components/topic_cards.py, build_cards.py, validate.py,
  data/topic_cards/, tests/test_topic_cards_*.py, tests/test_discovery_connections.py
- **Outcome:** Changed

### What I asked for
Why only 1 of 15 expected cards was shown, and fixes following the plan's rules-as-code idea.

### How I checked it
Each rule cites a snapshot chunk, and the build fails if the quote is not verbatim. Rule tests
run every combination of citizenship, household, first-timer, condo ownership and income.
Discovery precision 46% to 54%, recall 87% to 93% (7 questions, so illustrative).

### What I kept or changed
Kept. The adviser's plan suggested rules from third-party sites (EHG needing Family Grant
eligibility, lease to 95); these were not encoded because the HDB snapshot does not state
them. The AI first treated executive condos as private property; I kept the fix that leaves
them unknown. Three older tests were updated to the new behaviour.

## 2026-11-08 · Error bars and an answer-key audit
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** evaluation/stats.py, compare.py, metrics.py, retrieval_report.py,
  data/evaluation-data/development/accepted_evidence.json, tests/test_eval_*.py
- **Outcome:** Changed

### What I asked for
Confidence intervals and paired tests, and a transparent check of two answer keys (POL-02,
POL-04) where the top result already stated the answer.

### How I checked it
Wilson and McNemar values checked against known results in tests. Read both alternative
chunks myself before accepting them.

### What I kept or changed
Did not edit the answer key. Alternatives sit in a separate file with a written rule, and
strict and relaxed scores are always reported together (policy Recall@5 74.2% / 83.3%).
Hybrid vs keyword search is 6 wins to 1 loss (p = 0.125), so slides say "consistent,
not significant at n = 22". The adviser's plan claimed the embedding prefixes were missing
(they were already in place) and that the suite had 240+ tests (it has 515); both corrected.
No held-out material was opened.

## 2026-11-09 · Verification suite: mutation testing, property, convention and floor tests
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** scripts/mutation_test_retrieval_eval.py, tests/test_eval_compare.py,
  test_eval_stats.py, test_retrieval_report.py, test_topic_card_component.py,
  test_properties.py, test_conventions.py, test_scraping_validate.py,
  test_retrieval_floor.py, evaluation/stats.py, docs/testing-retrieval-and-evaluation.md
- **Outcome:** Changed

### What I asked for
Mutation testing on my eight modules using Tasha's method, tests for the weakest ones, then
the other Week 10 instruments: property, convention, data-validation and regression tests.

### How I checked it
Ran the runner before and after: the four weakest modules went from 28.2% to 93.3%, all eight
from 35.7% to 54.3%. Read the 28 survivors (8 equivalent, 20 harmless strings). Six new
assertions computed their expected values with the code under test; these were changed to
literals. Checked the retrieval floor fails when the top result is dropped (10/22). Full
suite: 967 passed.

### What I kept or changed
Reused Tasha's mutant generator without editing it. The first run left a `data/XXchromaXX/`
folder from a string mutant, so the runner now cleans these up. A property test found that
`wilson(0, n)` and `wilson(n, n)` fell just inside 0 and 1; fixed in stats.py (no reported
figure changes). No Hypothesis dependency added; properties are checked over every small input.

## 2026-11-09 · Full-system re-run after the router change, and a live freshness check
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** evaluation/freshness.py, tests/test_eval_freshness.py, evaluation/README.md,
  docs/evaluation-results.md (7a, L2), data/evaluation-data/results/20261109T112136Z_full_dev*
- **Outcome:** Changed

### What I asked for
Re-run the full system on main after Breann's router (#20), and a check that the app is
fresh on the real date, after a teammate pointed out the dev evaluation pins "today" to
Oct 2026.

### How I checked it
Compared both re-runs (main @19eeaec, then main @c36f6b9 after #27/#28) question by
question with the 8 Nov run and both baselines (paired McNemar). Read the flagged answers. For freshness, compared the app's periods with SQL over
the price database and ran 12 tests, including a year boundary and stale data.

### What I kept or changed
Safety went from 6/8 to 8/8 (forecast and guarantee now declined); on main @c36f6b9 prices
are 16/21. The other differences
went both ways and none is significant, so I report them as run-to-run variation, not a
regression. Kept the pinned date for dev scoring (reproducible) and added the live check
alongside it instead of changing the labels. The first version showed "past 6 months" on
9 Nov labelled Jun–Nov although the data ends in Oct. Tasha had already fixed this in #29
(cut to Oct and say November is missing), so I updated the check to expect that behaviour
and kept a test that fails the old one. Documented as L2, fixed; I did not edit the price
tool or router.

## 2026-11-10 · Known limitations and content-based doc names
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** docs/testing-retrieval-and-evaluation.md, docs/evaluation-results.md,
  scripts/mutation_test_retrieval_eval.py, README.md, docs/architecture.md,
  backend/kopi_keys/evaluation/README.md
- **Outcome:** Changed

### What I asked for
Turn the testing doc's open next steps into known limitations, since development stops after
the final presentation, and rename files that were named after me.

### How I checked it
Checked every link to the renamed files (README, architecture doc, evaluation README) still
resolves.

### What I kept or changed
Limitations listed plainly: policy_retrieval, policy_index and chunk.py at 29-36% mutation
score, no tests for the one-off baseline scripts, four modules not re-measured, and a
keyword-only retrieval floor. Files now named by content (evaluation-results.md,
testing-retrieval-and-evaluation.md, mutation_test_retrieval_eval.py); the AI log keeps my name.

## 2026-11-10 · Final deck: citations, speaker notes and presentation script
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none in the repository (the final slide deck, outside the repo)
- **Outcome:** Changed

### What I asked for
Official sources for the figures on the problem slide, speaker notes that work as the written
report (the deck replaces a report), a check of every slide against the repo, and a spoken
script for 15 minutes including a 3-minute demo, split across the four presenters.

### How I checked it
The AI recomputed the slide figures from the data: 95 sources in the snapshot manifest with
one PDF unusable (94), 242,737 sales from Jan 2017 to Oct 2026, and a median of $633,800 over
20,671 sales from Jan to Oct 2026. It traced each of the 12 topic cards to its source pages. I
compared the notes with docs/evaluation-results.md and the result files.

### What I kept or changed
The check found errors I fixed or passed to the slide owners: "MND" pages on slide 3 (the
sources are HDB, CPF and MyNiceHome), broken slide cross-references, a held-out row labelled
Recall@5 that is really Hit@5, and test, mutation and log counts that did not match the repo.
I asked for the notes as plain text without Markdown symbols, and for a simpler script that is
easy to memorise but not abrupt. Final GPU and held-out figures were taken from the team's
final run, because those result files are not in the repository.

## 2026-11-10 · README and data guide updated for submission
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** README.md, data/README.md, .gitignore, three data/**/.DS_Store files (removed)
- **Outcome:** Changed

### What I asked for
Check whether both READMEs reflect the whole repository, then update them on behalf of the
team before submission.

### How I checked it
The AI listed each outdated claim and checked it against the code: 898 chunks (the data guide
said 849), the evaluation and topic-card paths, and the committed vectors. It ran the backend
suite (1,100 passed) and the frontend tests (32 passed), confirmed every new command's module
can be run, and checked that every relative link in both files resolves.

### What I kept or changed
Added the final evaluation and held-out results, the current limitations, the newer features
and files, and a table of checks with their guides. The AI first wrote 31 frontend tests from
a text search; running the tests showed 32, so I corrected it. It also linked the GPU runbook,
which I had moved out of the repo, so that link was removed. The README states that the
per-question logs for the final runs are in the submitted supporting documents.

## 2026-11-10 · Supporting documents for the final submission
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none in the repository (Test Results, Held-out Evaluation Log and AI Use
  Disclosure Log, as Word documents in the submission folder)
- **Outcome:** Changed

### What I asked for
Readable supporting documents for the zip: test results, the held-out log, and a document
describing the team's AI use logs with the team declaration and each member's reflection,
following the SE201 AI Use Disclosure Policy.

### How I checked it
Re-ran the backend and frontend tests, the snapshot validator and the price cases on main
@d9c5d29 on 10 Nov. Rebuilt the test results from Nisha's final development package
(final-dev-20261110-results) once it arrived, and checked the held-out figures against the
run's own output file. Counted the log entries and the Assisted-by trailers from git, checked
every log entry against the policy's format, and confirmed the finals-frozen tag points to
1c4d87c.

### What I kept or changed
The final package corrected two figures the deck had used: answered questions are 31/42 vs
26/42 (p = 0.383, not significant), not "71.4% vs 61.9%, p = 0.523", and keyword-only Hit@5
is 63.6% because it now includes the synonyms. I updated the test results and README to match
and passed the slide fix to the team. Held-out results stay in their own log, separate from
the test results. How the held-out questions were drafted is recorded in that submission
document, not in the AI logs. The disclosure document was restructured to the policy: team
declaration, how we disclosed, tools and checks, and one reflection per member. A line saying
every AI change was reviewed by another member was softened, because branch protection
settings were not verified. I found an earlier draft of one teammate's log had been pasted in
by mistake and reverted every change made from it.
