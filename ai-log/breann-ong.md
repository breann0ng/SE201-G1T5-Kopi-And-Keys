# AI Use Log: Breann Ong

## 2026-10-16 · Review of repo structure against the proposal
- **Tool (model):** Claude Code (Claude Opus 5.5; the session started on Claude Fable 5.1)
- **Files:** none changed (advice only; led to the refactor entry below)
- **Outcome:** Changed

### What I asked for
Feedback on why our repo structure and files did not match the architecture
diagram in our proposal, and how to make the layout easier to follow.

### How I checked it
Compared its list of mismatches against our proposal (sections 3.2, 5 and
Appendix C) and the actual files. Its points matched what I had seen: two
separate graphs, one "Advisor" covering three diagram boxes, and folders
named after people and milestones rather than components.

### What I kept or changed
It assumed a separate Discovery Agent, as in the proposal. I corrected it:
our team has merged Discovery into the Synthesiser Agent. I kept the
revised layout (one module per diagram box) and the order of steps.

## 2026-10-16 · Refactor backend into one graph matching the diagram
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/graph.py, state.py, schemas.py, llm.py, cli.py,
  main.py, components/*, evaluation/* (placeholders), data/topic_cards/README.md,
  tests/*, scripts/run_price_cases.py, README.md, docs/architecture.md,
  docs/price-synthesis-and-verification.md, examples/price_cases/
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
Merge the old Advisor workflow, the Stage 1 gateway graph and the midpoint
subgraph into one LangGraph graph and one state. Move the gateway and
router into query_router.py, the midpoint synthesiser into synthesiser.py,
and the numeric verifier into verifier.py. Add placeholders for topic cards
and the evaluation runner, which other team members will build.

### How I checked it
- The test suite went from 59 to 62 passing tests. All 30 development-set
  routing labels pass without any change to the label file.
- Nisha's numeric verifier tests were kept and now run through the full
  graph rather than a separate subgraph.
- The six synthetic price cases pass through the new graph, with a real model
  (see the next entry).
- [Describe your own review: e.g. which files you read line by line, and
  anything you questioned or changed.]

### What I kept or changed
The AI made behaviour choices that the team still needs to confirm:
- price questions with no dates default to the last 12 months
- mixed questions still answer the policy part when price data is missing
- the old "demo" shortcut in the API was removed
- the owners for Policy Retrieval and Evaluation are marked TBC in
  docs/architecture.md.
[Record which of these you kept or changed.]

## 2026-10-16 · Run the local Ollama model on macOS
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none (local setup only; downloaded the qwen2.5:3b model)
- **Outcome:** Kept

### What I asked for
Help to run the price synthesis with the local Ollama model on my Mac. The
repo's setup script only supports Windows.

### How I checked it
The first attempt with qwen2.5:7b timed out after 180 seconds (the code forces
CPU-only, and my Mac has 8 GB of RAM). The graph abstained instead of showing
an unverified answer, which is the intended behaviour. With qwen2.5:3b the
fixture was answered correctly after one Verifier retry, and 6/6 synthetic
price cases passed. I compared the output figures with
examples/price_sql_result.json.

### What I kept or changed
Kept qwen2.5:3b as the model for local runs. The proposal names Qwen3 8B, so
the team needs to update the proposal or the docs to state the 3B model.

## 2026-10-16 · Fix LangSmith tracing for CLI runs
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/cli.py, backend/kopi_keys/llm.py,
  scripts/run_price_cases.py, tests/conftest.py, pyproject.toml
- **Outcome:** Kept

### What I asked for
Why a CLI run did not appear in our LangSmith tracing.

### How I checked it
The cause it identified was correct: only the API server loaded .env. After
the fix, the run appeared in our LangSmith project as one LangGraph trace with
every node and the Ollama call as child steps. It also found that the tests
were sending traces to our project, and after the fix new test runs no longer
appear there. All 62 tests still pass.

### What I kept or changed
Kept all changes.

## 2026-10-18 · Review of folder layout and project name
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** none changed (advice only; led to the refactor entry below)
- **Outcome:** Changed

### What I asked for
Whether to move scripts/ into backend/kopi_keys/ and combine it with
components/, and whether the name kopi_keys could be confused with
key-value pairs.

### How I checked it
Checked its points against the files. scripts/scraping/ has its own
requirements.txt and runs separately in the policy-refresh GitHub workflow,
so merging it into components/ would add scraper packages to the app.
Confirmed that three tests loaded scripts/build_resale_db.py by file path,
and that evaluation files were spread over three folders.

### What I kept or changed
I did not merge scripts/ into components/. Instead I took three of its
suggestions: put evaluation data in one folder, move the build logic into the package, and move examples/ into tests/fixtures/. I kept the name kopi_keys: users only see "Kopi & Keys" in the app, and renaming would touch every import and conflict with teammates' open branches. Its other suggestion, merging the two topic_cards.py files, is not done yet.

## 2026-10-18 · Restructure evaluation data, build scripts and fixtures
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/ingest/ (new: resale_db.py, policy_index.py),
  scripts/build_resale_db.py, scripts/build_policy_index.py,
  scripts/run_price_cases.py, backend/kopi_keys/evaluation/dataset.py,
  data/evaluation-data/ (from data/evaluation/ and evaluation/results/),
  tests/fixtures/ (from examples/), tests/test_resale_db.py,
  tests/test_price_stats.py, tests/test_price_refine.py,
  tests/test_synthesiser_verifier.py, tests/test_development_set_contract.py,
  README.md, docs/architecture.md, docs/price-synthesis-and-verification.md
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
Make the three layout changes and fix every import and path they affect.

### How I checked it
- All 247 tests pass (1 skipped), the same count as on main before the change.
- The six synthetic price cases pass in validation-only mode from their new
  folder, and scripts/build_resale_db.py --help still works.
- During the session data/evaluation/ was renamed on disk to
  data/evaluation-data/, which broke 5 evaluation tests. The AI stopped and
  asked rather than guessing. I chose to keep the new name, and it pointed
  the evaluation code and tests at it.
- Checked that my held-out questions in data/evaluation-data/held-out/ are
  still ignored by .gitignore and are not in the commit.
- [Describe your own review: e.g. which diffs you read, and anything you
  questioned or changed.]

### What I kept or changed
The AI left scripts/build_resale_db.py and scripts/build_policy_index.py as thin wrappers, so the commands in the README and docs work unchanged. The team needs to know that data/evaluation/ is now data/evaluation-data/ before merging, because open branches that touch the dev set will conflict.
[Record anything you kept or changed.]

## 2026-11-06 · LangSmith evaluators and dev-set experiments
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/evaluation/langsmith_eval.py (new), pyproject.toml
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
Whether LangSmith's built-in evaluators suit our app, how to set one up on
live traces, and a way to run the dev set as LangSmith experiments.

### How I checked it
- It mapped each evaluator against our existing metrics: most (hallucination,
  exact match, tool selection) are already covered more strictly by the
  verifier and run_eval; answer relevance was the gap.
- Set up an Answer Relevance evaluator on the kopi-and-keys project; the AI
  confirmed through the LangSmith API that the filter and project were right
  and explained the auto-created "Alignment" rule.
- Uploaded the 50 dev questions as the kopi-dev-set dataset (held-out set
  never uploaded) and ran 3-question experiments. Per-question scores reuse
  metrics.end_to_end, so they match run_eval --local.
- The LLM-judge option (--judge) has not been run yet.
- [Describe your own review.]

### What I kept or changed
[Record anything you kept or changed.]

## 2026-11-06 · Router scope guard and no-rule-match tracing
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py, state.py,
  tests/test_query_router.py, tests/test_graph.py, tests/test_api.py,
  tests/test_development_set_contract.py
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
How to make the rule-based router send more questions to the right place
instead of declining them, using a rules + LLM hybrid. This entry covers the
first two steps (rules only); the LLM fallback is not built yet.

### How I checked it
- The LangSmith smoke test showed OOS-06 (forecast) and OOS-07 (guarantee)
  being answered. A new scope guard now declines forecasts, future prices and
  guarantees before any other rule.
- Its first version also declined "How much will a 4-room in Bishan cost?"
  and "...? We're buying next year." The AI caught this by testing questions
  that should still be answered, and tightened the rules; both are now tests.
- Routes for all 50 dev questions were saved before and after: only OOS-06
  and OOS-07 changed. Router routing is 50/50; 412 tests pass (2 known
  flat-type gaps remain).
- Traces now show query_router:abstain:no_rule_match when no rule fired, to
  measure what an LLM fallback would see. I checked this in the frontend with
  questions with no keywords and with questions that should be declined.
- [Describe your own review.]

### What I kept or changed
[Record anything you kept or changed.]

## 2026-11-08 · Router: request-type declines and weak-match confirmation
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py,
  evaluation/fallback_eval.py, data/evaluation-data/fallback/fallback_questions.jsonl,
  tests/test_query_router.py, tests/test_intent_fallback.py
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
How to stop patching the scope guard one case at a time. Three fresh questions
("Recommend me a good mortgage broker", "Which bank gives the cheapest home
loan right now?", "Can you write my appeal letter to HDB?") were answered as
policy on "loan" / "hdb" alone.

### How I checked it
- Declines are now grouped by request type (predict, value one flat,
  guarantee, recommend a provider, investment advice, do a task), so a new
  provider or task is covered without a new rule.
- When generic keywords alone ("hdb", "loan", "block", "how long", ...) make a
  question policy, the LLM is asked to confirm. It can only veto (a confident
  "unanswerable"), never switch the intent. Without the LLM nothing changes.
- Routes for all 50 dev questions were saved before and after: none changed;
  only POL-04 now gets the confirmation call (about 1 s).
- Fixed "damage" counting as a price word on its own ("water damage").
- Fallback set grew from 21 to 38 questions. With qwen2.5:3b: 37/38 (miss:
  "What time does the HDB hub open on Saturday?" confirmed as policy). The AI
  wrote these questions alongside the rules, so they are regression checks,
  not an independent test. 528 tests pass (2 known flat-type gaps remain).
- [Describe your own review.]

### What I kept or changed
[Record anything you kept or changed.]

## 2026-11-08 · Policy relevance: answers_aspect check (shadow mode)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/answer_aspects.py (new),
  policy_guardrails.py, policy_synthesis.py, verifier.py, schemas.py,
  tests/test_answer_aspects.py
- **Outcome:** [Kept / Changed — choose after your review]

### What I asked for
score_relevance compares words, not meaning, so a quote that shares the
question's words but answers a different part of it can pass. I asked how to
check that a quote answers what was asked.

### How I checked it
- The check works out which aspects the question asks (income, lease,
  timing, ...) and requires each quote to address one, e.g. a duration for
  "how long". Known false pass now caught: "a valid HFE letter" does not
  answer "How long is an HFE letter valid for?".
- First version had the model label each quote. On the synthesis benchmark
  (12 cases, qwen2.5:3b) this made its quotes long and non-verbatim: quality
  passes 10 -> 5, over-abstentions 2 -> 7. The default is now code-only
  (generation unchanged); model labels are opt-in (KOPI_ASPECT_LABEL=model).
- Enforcing it exposed two false rejects, fixed in general ways: grant names
  ("Proximity Housing Grant") and "without adding amounts" no longer count
  as asks. With enforce, the benchmark matches the check being off.
- Default is shadow (KOPI_ASPECT_CHECK): recorded in relevance_scores, never
  blocks. The benchmark has no wrong-answer quotes, so it shows no harm, not
  benefit; enforce waits for shadow traces compared with the LangSmith judge.
  554 tests pass in shadow and enforce mode.
- [Describe your own review.]

### What I kept or changed
[Record anything you kept or changed.]
