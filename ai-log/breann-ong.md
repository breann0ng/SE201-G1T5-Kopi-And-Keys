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
- **Outcome:** Kept

### What I asked for
Merge the old Advisor workflow, the Stage 1 gateway graph and the midpoint
subgraph into one LangGraph graph and one state. Move the gateway and
router into query_router.py, the midpoint synthesiser into synthesiser.py,
and the numeric verifier into verifier.py. Add placeholders for topic cards
and the evaluation runner, which other team members will build.

### How I checked it
- The test suite went from 59 to 62 passing tests. All 30 development-set routing labels pass without any change to the label file.
- Nisha's numeric verifier tests were kept and now run through the full
  graph rather than a separate subgraph.
- The six synthetic price cases pass through the new graph, with a real model

### What I kept or changed
The AI made behaviour choices that the team still needs to confirm:
- price questions with no dates default to the last 12 months 
- mixed questions still answer the policy part when price data is missing
- the old "demo" shortcut in the API was removed
- the owners for Policy Retrieval and Evaluation are marked TBC in docs/architecture.md.

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
- **Outcome:** Kept

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

### What I kept or changed
The AI left scripts/build_resale_db.py and scripts/build_policy_index.py as thin wrappers, so the commands in the README and docs work unchanged. The team needs to know that data/evaluation/ is now data/evaluation-data/ before merging, because open branches that touch the dev set will conflict.

## 2026-11-06 · LangSmith evaluators and dev-set experiments
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/evaluation/langsmith_eval.py (new), pyproject.toml
- **Outcome:** Changed

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

### What I kept or changed
- Kept the LLM as a judge on LangSmith, future work to run on dev set 

## 2026-11-06 · Router scope guard and no-rule-match tracing
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py, state.py,
  tests/test_query_router.py, tests/test_graph.py, tests/test_api.py,
  tests/test_development_set_contract.py
- **Outcome:** Kept 

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

### What I kept or changed
Kept the scope guard and no rule match as possible path (query_router:abstain:no_rule_match), over original router path of classifying all failures as query_router:abstain. 

## 2026-11-08 · Router: request-type declines and weak-match confirmation
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py,
  evaluation/fallback_eval.py, data/evaluation-data/fallback/fallback_questions.jsonl,
  tests/test_query_router.py, tests/test_intent_fallback.py
- **Outcome:** Kept

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

### What I kept or changed
Kept strong vs weak question intent to filter unanswerable questions. 

## 2026-11-08 · Policy relevance: answers_aspect check (shadow mode)
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/answer_aspects.py (new),
  policy_guardrails.py, policy_synthesis.py, verifier.py, schemas.py,
  tests/test_answer_aspects.py
- **Outcome:** Changed 

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

### What I kept or changed
- Removed shadow mode after moving test on to dev set in Langsmith

## 2026-11-08 · PR review: provider rule declined valid questions; merge with main
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/components/query_router.py, graph.py (merge),
  tests/test_query_router.py, tests/test_intent_fallback.py
- **Outcome:** Kept

### What I asked for
Fixes for two review comments on the PR: a merge conflict in graph.py that
had to keep both the profile/subsidy-status fix from main and the LLM
fallback, and "Which bank loan documents are required for buying a resale
flat?" being declined as a provider recommendation, with no LLM appeal.

### How I checked it
- Conflict resolved by keeping both: the subsidy-status check now runs on
  the final routing, after any LLM decision. A new test sends an LLM-routed
  question with a contradicting sidebar and checks both behaviours.
- The rule fired on "which ... bank" even when "bank" only described
  something else. It now requires the provider to be what is chosen: not
  followed by a noun it modifies (loan, documents, fees, ...) or a
  possessive ("the agent's commission"). One structural rule, not a list
  of cases.
- Regression tests: 5 such questions are no longer declined by a rule;
  5 real provider requests still are. Routes for the dev set and fallback
  set are unchanged. 676 tests pass (2 known flat-type gaps remain).
- Found while testing, not fixed: "first-timers" (plural) is not extracted
  as first_timer; only the singular is.

### What I kept or changed
Kept both profile/subsidy-status fix and LLM router hybrid for routing questions. profile/subsidy-status fix still takes precedence, LLM router acts as a fallback.

## 2026-11-09 · CI failure: frontend test used chunk IDs from before re-chunking
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** frontend/tests/sourceContent.test.ts
- **Outcome:** Changed

### What I asked for
Why "Frontend lint and build" failed on the router PR when the PR changed no
frontend code.

### How I checked it
- Ran the CI steps locally: lint and build passed; npm test failed because
  sourceContent.test.ts looks up CHUNK_EHG_32 and CHUNK_EHG_30, which no
  longer exist. The re-chunking commit (738c3e0) renumbered the chunks a day
  before the test was added, so main was failing too.
- Found the same two tables by content (non-resident spouse; first-timer and
  second-timer couple) and switched the test to CHUNK_EHG_48 and
  CHUNK_EHG_46. 12/12 frontend tests pass.
- Note for the team: tests that look up chunks by ID break whenever the PDFs
  are re-chunked.

### What I kept or changed
Kept the ID change as suggested. I chose to fix it on the router PR branch
rather than in a separate PR to main, so the PR could go green; main was fixed
when the PR merged.

## 2026-11-09 · LLM-as-judge (answer relevance): fix, calibrate, run on the dev set
- **Tool (model):** Claude Code (Claude Opus 5.5); judge model in LangSmith:
  Gemini 3.6 Flash, then Gemini 3.5 Flash-Lite
- **Files:** backend/kopi_keys/evaluation/langsmith_eval.py,
  tests/test_langsmith_eval.py (new); LangSmith evaluator settings (prompt,
  variable mapping, filters) changed through the API
- **Outcome:** Kept

### What I asked for
Whether our LangSmith "Answer Relevance" judge actually scores our answers,
whether to move to a stronger model, and whether a 0/1 score is too harsh.
Then: fix it, test it on deliberately wrong answers, and run it on the dev set.

### How I checked it
- It was not judging answers. The evaluator mapped `output.message`, which on
  our LangGraph trace is the user's question, not the answer
  (`output.response.message`). All 8 scores so far were 0, with comments
  saying the output "repeats the question". It also still used the generic
  prompt, which penalises quoting neighbouring sentences.
- Fixed in LangSmith: our HDB prompt from langsmith_eval.py, mapping
  `input.message` / `output.response.message`, and a filter so only answered
  runs are judged (declines are not "irrelevant" answers). The suggested filter
  syntax `outputs.response.status` was rejected by LangSmith; the working form
  is `output_key` / `output_value`, tested on real runs before saving.
- Mapping is stored on the evaluator, not per rule, so the live-trace rule and
  the dataset rule must see the same output shape. Experiments returned the
  response directly; langsmith_eval.py now returns `{"response": ...}` like a
  live trace. New test checks the shape and that the code metrics still score
  it. 939 tests pass.
- Calibration: 10 question/answer pairs, 3 correct and 7 deliberately wrong
  (wrong scheme, wrong buyer x2, wrong town, wrong period, missing half of a
  two-part question, off topic). Flash: 6/6 correct where it ran, but 4 calls
  failed with 429 quota errors that LangSmith records as score 0. Flash-Lite:
  10/10 correct, no errors. Quota errors are excluded from every average
  (comment contains `ChatGoogleGenerativeAIError`).
- Found and fixed on the way: the local Chroma index was missing 195 of 898
  chunks (stale after merges); rebuilt with scripts/build_policy_index.py.
  An earlier dev run was stopped because it mixed two judge models and used
  the incomplete index.
- Dev-set run judge-dev-lite (50 questions) vs pre-merge: over-abstention
  31% -> 19%, price correct 76% -> 94%, route 98% both, unsafe 0/8 both, but
  stale 0/7 -> 3/7. Judge: 70% relevant (21/30 answered), 0 errors. Of the 9
  judged irrelevant, about 8 are real misses that passed every code check
  (e.g. LTV "now" answered with the pre-August-2024 80% footnote; HFE validity
  answered with processing time). The Bidadari price answer looks like a judge
  false negative (Bidadari is in Toa Payoh). One run, different commit from
  pre-merge, so differences are indicative only.
- Kept the score binary: pass/fail judgements are more consistent across runs
  than a 1-5 scale; the average over many questions gives the detail.
- Manually checked all 21 of the 21 answers judged as relevant, to ensure scoring was not done wrongly.

### What I kept or changed
- Replaced the generic relevance prompt with our HDB prompt. My first edit
  in the LangSmith UI did not save correctly (the answer variable became
  `{{var1}}` and the mapping could only be set to the whole output), so I
  had the prompt, mapping and filters set through the API instead.
- Moved the judge rule from the dataset I had uploaded through the UI
  (dev_set_questions, which lost the question text) to kopi-dev-set.
- Replaced the Google API key after the quota errors, then switched the
  judge from Gemini 3.6 Flash to Gemini 3.5 Flash-Lite: it has higher free
  limits and scored 10/10 on the calibration pairs.
- Kept the binary score rather than a 1-5 scale.
- Changed how errors are counted: quota errors are left out of every
  average (comment contains `ChatGoogleGenerativeAIError`), not scored as 0.
- Chose one shared output shape for experiments and live traces instead of
  two separate evaluators, since the mapping is stored on the evaluator.
- Did not use the first judge-dev run: it was stopped because it mixed two
  judge models and used the incomplete index.

## Reflection (Use of AI)
### What I learned about using these tools effectively
The tools worked best when I gave them a way to check their own work. 

For example, before changing the router, I saved the routes for all 50 dev questions and compared them afterwards. That showed exactly which answers a change affected (for example, only OOS-06 and OOS-07 changed after the scope guard). 

I also learned to ask for general fixes rather than single patches. Early router changes fixed one question at a time. When I asked how to stop doing that, we grouped declines by request type, and a new provider or task was covered without a new rule. 

I learned to question a result that looks too clean, too. Every LangSmith relevance score being 0 was a sign of a setup problem, not of bad answers. Finally, I learned to say up front what a result would and wouldn't prove. The fallback questions were written by the same AI that wrote the rules, so I recorded them as regression checks, not as an independent test.

### Where the tools were strong, and where they were weak
The tools were strongest at large, mechanical changes and at finding causes. They merged three graphs into one without changing any dev-set routing labels. They also traced a frontend CI failure to chunk IDs renumbered by an earlier re-chunking commit, and found that our LLM judge was scoring the user's question instead of the answer. When something unexpected happened, such as the evaluation folder being renamed during a session, the tool stopped and asked instead of guessing, which pleasantly surprised me. 

Their weakness was suggesting things that sounded right but didn't work. The LangSmith filter syntax it suggested was rejected, and the first scope guard declined valid questions like "How much will a 4-room in Bishan cost?". It also didn't account for our small local model. Asking qwen2.5:3b to label each quote cut benchmark quality passes from 10 to 5 of 12, which a larger model may not have done. It assumed our proposal's design too, including a separate Discovery Agent our team had already merged. I had to check its claims against our code, our decisions and real runs.

### What went wrong, and what I would do differently
Several problems stayed hidden because no check s were in place for the setup itself: 
1) The LLM judge mapped the wrong field, so it produced scores that meant nothing. 

2) The local Chroma index was missing 195 of 898 chunks after merges, which would have made retrieval results look worse than they were. 

3) A frontend test looked up chunks by ID, so it broke when the PDFs were re-chunked. 

4) The biggest miss was out-of-date answers. The judge run on 9 November showed the system answering "What is the LTV limit now?" with the pre-August-2024 80% footnote. 

We froze the dev evaluation before fixing it, and three policy-change questions still quote historical rules. Next time I would add setup checks to the evaluation itself (index complete, judge reading the answer) before trusting any score. I would also turn every real failure found in a trace into a test and fix it before freezing, rather than noting it for later.