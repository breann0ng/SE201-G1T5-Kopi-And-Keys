# AI Use Log: H Kahfath Nisha

## 2026-11-09 - Candidate-only resale price watcher
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `backend/kopi_keys/ingest/price_watch.py`,
  `scripts/watch_resale_prices.py`, `.github/workflows/price-refresh.yml`,
  `tests/test_price_watch.py`, `docs/price-watcher.md`, `README.md`
- **Outcome:** Changed on separate branch `feat/nisha-price-watcher`

### What I asked for
Build a separate candidate-only watcher for official data.gov.sg resale prices,
similar to policy change monitoring, while keeping the tested price dataset fixed.

### How I checked it
The 39 offline watcher tests passed. Full backend regression on this branch:
610 passed, 1 skipped and 4 existing expected failures. The isolated checkout had
no policy vector index and reported keyword-fallback warnings; these results do
not claim a live hybrid retrieval evaluation or hosted Actions success.

A live official export check on 9 November downloaded 244,312 rows through
2026-11, against the frozen 242,737-row baseline through 2026-10. It found 1,586
added and 11 removed rows, including possible corrections rather than solely new
sales. The inactive database passed SQLite integrity and row-count checks. SHA-256
checks before/after confirmed that the existing active CSV and database were
unchanged. No candidate was activated, live GitHub issue published or held-out
question opened. The first hosted schedule/notification still requires checking
after merge.

### What I kept or changed
Reused Tasha's validated importer without changing price calculations. Downloads
use the fixed official dataset API, bounded polling, HTTPS destination checks,
redirect rejection and a size limit. Normalised comparisons preserve duplicate
multiplicity. Every run retains a unique candidate directory and a provenance/
comparison report. Access blocks and incomplete checks fail visibly and retain
active data. The scheduled workflow saves narrow diagnostic/candidate artifacts
for 30 days and explicitly requests review through an issue/comment. It has no
contents-write permission or automatic activation step. Notification failures
remain visible; unchanged checks do not close outstanding review issues.

The watcher needs neither a GPU nor an LLM. Separate GPU integration checks used
another frozen checkout and are not included in this watcher's test counts.

### Review follow-up — 9 November 2026
Changed automatic checks from daily to Monday approximately 10:33 SGT to limit
repeat notifications and large candidate uploads while the active dataset stays
frozen. Manual dispatch remains. Documented that unchanged-versus-last-candidate
deduplication is not implemented: a candidate still different from the active CSV
can be reported again in a later week, as can an unresolved access failure.
The 39 watcher tests still pass; workflow YAML, the weekly cron, manual trigger
and read-contents/write-issues permissions were checked. No active data, comparison
rules, notification failure handling or candidate validation were relaxed.
The follow-up CI run hit the same Gitleaks download failure before scanning.
Copied the bounded retry/timeouts already validated in PR #23, preserving its
version/hash pin and blocking checksum/scan steps. This is a CI download fix,
not a secret finding or relaxation of scanning.

## 2026-10-15 · Local CPU model, price synthesiser and numeric verifier
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** originally `backend/kopi_keys/midpoint/`, setup scripts, tests and
  midpoint documentation; now `backend/kopi_keys/llm.py`, `cli.py`,
  `components/synthesiser.py` and `components/verifier.py`
- **Outcome:** Changed

### What I asked for
My midpoint tasks: run a lightweight model locally on CPU, turn the
Stage 2 SQL statistics into a concise response, and check every generated
number against the supplied SQL result before showing the answer.

### How I checked it
I ran the CLI and the synthetic-case script in PowerShell and shared the
output for review. The local Qwen2.5:3b call returned the expected statistics
and passed verification. Codex also checked the Ollama runtime's reported
VRAM allocation and the request's CPU-only setting. These were local smoke
checks, not a general model benchmark or a validation of the resale dataset.

### What I kept or changed
Kept Qwen2.5:3b through Ollama, with `num_gpu=0`. SQL supplies the numbers;
the model only formats them. The verifier compares each named statistic,
uses Decimal rounding to two decimal places, and rejects missing labels,
extra claims and swapped values. A failed draft gets one repair attempt;
a second failure or model error withholds the answer. Zero transactions
produce a fixed message without calling the model.

## 2026-10-15 · More synthetic SQL cases
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** originally `examples/midpoint_cases/` and
  `scripts/run_midpoint_cases.py`; now `examples/price_cases/` and
  `scripts/run_price_cases.py`
- **Outcome:** Kept

### What I asked for
More tests I could run before the other components were ready, including
edge cases for SQL statistics and invalid input.

### How I checked it
I ran the script myself and got 6/6 checks passed in `live_ollama` mode:
zero transactions, a single transaction, decimal rounding, large amounts,
a missing median and an invalid range. I also ran the decimal fixture
separately: mean SGD 612,345.13, median SGD 610,000.01, IQR SGD 33,333.34,
range SGD 500,000.00 to SGD 750,000.00, and volume 7. Verification passed
after one model call. The report was saved locally.

### What I kept or changed
Kept the fixtures and batch runner, with synthetic data explicitly labelled
in the response. These check the formatter and verifier against controlled
inputs; they do not count as official resale transactions or held-out
evaluation questions. Later, the team changed the user-facing treatment of
small real transaction groups; the original single-row fixture records the
behaviour of the midpoint formatter.

## 2026-10-16 · PR reviews, local startup and LangSmith tracing
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** no PR code changed during review; local ignored `.env`,
  environments, databases and review reports
- **Outcome:** Changed

### What I asked for
Review the updated team PRs before accepting them, help run the frontend,
backend and Ollama, and explain why no traces appeared in my LangSmith
workspace.

### How I checked it
Codex reviewed PR #3 in an isolated checkout and identified issues with
chunk IDs, evaluation routing, tracked held-out questions and raw-file
checksums. Its follow-up review checked the fixes and ran the tests and
frontend build. For PR #4, it rebuilt the resale database and compared
seven filtered statistics directly with the committed CSV. I provided my
LangSmith browser hostname, `apac.smith.langchain.com`; Codex checked the
regional API and confirmed a completed application trace after the fix.

### What I kept or changed
Kept the team's component-based refactor and shared CSV. The tracing fix
set `LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com` in my local
`.env`, without committing the API key. I kept review reports local and
treated previously exposed held-out questions as unsuitable for a fresh
unseen evaluation. Running a second backend later conflicted with the
background server; Codex checked the existing health endpoint instead of
changing Windows socket permissions.

## 2026-10-16 · Fix rejected policy questions and grounded responses (PR #5)
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `components/query_router.py`, `policy_retrieval.py`,
  `policy_synthesis.py`, `synthesiser.py`, `topic_cards.py`, `verifier.py`,
  `graph.py`, `state.py`, `schemas.py`, `llm.py`, `main.py`,
  frontend profile, quick replies, API and history files,
  `tests/test_policy_advisor.py`, `docs/policy-advisor.md`, README files
  and `.env.example`
- **Outcome:** Changed

### What I asked for
Improve the app after I found that “may i know about loans” and the starter
question “Can a Singapore PR couple buy a resale flat?” were rejected.
I also shared an EHG response that mixed household conditions and a footer
incorrectly calling the official evidence fictional.

### How I checked it
I supplied the actual failing prompts and responses. Codex traced the
problems to keyword routing, placeholder policy output and integration,
then ran 184 tests and the frontend production build. Live requests
through the frontend API covered the PR-couple question, loans, personal
EHG eligibility, a broad HDB question and a price clarification followed
by “Yishun, 4-room”. The price follow-up returned 763 transactions and
passed numeric verification. The loan response took about 56 seconds on
CPU. These were API checks; Codex did not perform a browser click-through.

### What I kept or changed
Kept the routing fixes, missing-profile questions, bounded clarification
history and the corrected `snapshot` response mode. The model selects
source quotes rather than writing unrestricted policy paraphrases; table
answers retain their row and column scope and pass deterministic checks.
General PR-couple citizenship conditions use the source table directly.

I had asked about upgrading the model, but a local diagnostic comparison
found Qwen3:4b slower and still unable to interpret the citizenship table
reliably. I kept Qwen2.5:3b as the default. This comparison used one task
and does not establish that either model is generally better.

The original dev retrieval check improved from 38% to 56% Recall@5 on that
version of the dev set, below the 85% target. Those figures are historical
development checks, not final evaluation results. Sandra later replaced
the ranker with hybrid retrieval and combined the dev sets; her current
results are recorded separately. I did not create or test a fresh held-out
set in this work.

## 2026-10-18 · PR #8 review and midterm code handoff
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `ai-log/nisha.md`; local ignored PR review, suggested patch,
  validation reports and midterm source ZIP
- **Outcome:** Changed

### What I asked for
Run and review the new PR before approving it, prepare the code for the
midterm review, and write my AI-use log using the same structure as the
other three team members' logs.

### How I checked it
The checkpoint report records 225 automated tests on main, all passing
(240 including the PR under review).

Codex compared PR #8 with its base in a separate checkout. The first run
skipped a test requiring the missing vector index. After setting up
EmbeddingGemma and building the complete index, the test suites passed
on both branches, with no skips. Both frontend
production builds passed; lint had no errors and four existing warnings.
The snapshot validator passed all checks for 849 chunks and 12 topic
cards. Dev routing stayed at 30/30 and hybrid Recall@5 stayed at 12/20.

A focused check found a bug the Python tests did not cover: JavaScript
`\s+` in the new display regex consumes newlines in the real EHG income
bands. Codex initially called this blocking, then checked the actual
Markdown-rendered HTML and the structured chart's call sites. The text
already rendered as one paragraph, and the chart uses untouched source
data, so the final finding is a non-blocking formatting nit. A proposed
horizontal-whitespace-only replacement was checked separately. This review
used commands, source checks and server-rendered HTML; Codex did not
perform a browser click-through.

The live loan-income answer verified. The buying-guide example still
abstained on two full runs after both allowed attempts. A raw-response
diagnostic showed the model citing `CHUNK_RESALE_26` instead of the
supplied `CHUNK_BTO_26`; schema validation dropped the answer, and the
retry received only a generic no-claims error. This is an existing
synthesis limitation exposed by the new route, rather than unsafe output
introduced by the PR. The automated routing tests did not cover it.

### What I kept or changed
Recorded the final recommendation to request a follow-up before approving
the PR as submitted, because the advertised buying-guide answer still
fails. The proposed direction is to constrain citation IDs and give the
repair step the actual validation error, while keeping the verifier strict.
Kept the formatting patch separate from the PR and working main branch.
The final local midterm ZIP identifies the tested main commit and adds
this log, review notes and the pending PR diff without applying that diff.
The archive was checked for readable contents and excludes local credentials,
installed dependencies, generated databases and model files. No fresh
held-out set was used. The package has not been uploaded to a submission
portal, and no PR approval or merge was posted by Codex.

## 2026-10-26 · Finals policy synthesis, verifier and CPU benchmark
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `components/policy_synthesis.py`, `policy_guardrails.py`,
  `synthesiser.py`, `verifier.py`, `graph.py`, `state.py`, `llm.py`,
  `evaluation/synthesis_benchmark.py`, `data/benchmarks/synthesis_cases.json`,
  focused tests, `.env.example`, README and finals documentation
- **Outcome:** Changed

### What I asked for
Complete my finals tasks on a separate branch: multi-grant policy synthesis,
verifier relevance checks and abstention, and CPU synthesis benchmarking of
Qwen2.5:3b against a larger local model.

### How I checked it
Codex checked the current implementation and created
`feat/nisha-finals-policy-guardrails`. The existing test suite passed before
changes. New regression cases exercise complete and incomplete grant combinations,
missing prerequisites, irrelevant but genuine quotes, household scope, a bounded
repair loop, request-specific citation IDs and independent benchmark coverage.
The full suite passes with the vector index and Ollama available. Live comparison
uses the installed Qwen2.5:3b and Qwen3:4b with the same evidence, CPU settings
and generation limits; results and limitations are recorded in the finals guide.
The completed fixed-evidence comparison passed the expected outcome and quote
coverage checks on 10/12 cases for 3B and 9/12 for 4B. The larger model timed out
once; an extra diagnostic also timed out and was stopped. Memory pressure affected
timings, so these are exploratory results. A PR-couple application request passed;
the actual multi-grant application request timed out during CPU prompt processing
and safely abstained. I do not treat that request as a successful live demo.

### What I kept or changed
Kept source-excerpt policy answers, deterministic SQL numeric checks, and the
single repair before abstaining. Added explicit grant coverage and combination
requirements, lexical relevance scoring, household-scope checks, and actual JSON
validation details in the repair prompt. Formatting-only emphasis can be omitted
without treating changed words, numbers or stitched lists as supported quotes.

The synthesis benchmark has 12 labelled development cases with fixed official
snapshot evidence. It is separate from the team's expanded evaluation set and
does not read fresh held-out questions. Its automatic checks measure outcome and
quote coverage, not legal correctness or independently reviewed writing quality.
The relevance threshold is a development heuristic, not a calibrated probability.
These changes do not replace the team's router, backtracking, RAG optimisation,
price-tool, topic-card or UI work. The default model remains Qwen2.5:3b.

## 2026-10-27 · Prepare allocated GPU inference and cluster benchmarks
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `llm.py`, `evaluation/synthesis_benchmark.py`, GPU regression tests,
  `scripts/start_cluster_ollama.sh`, `.env.example`, `.gitattributes`, README
  and `docs/gpu-cluster.md`
- **Outcome:** Changed

### What I asked for
Check the supplied SCIS cluster guide and node inventory, identify practical
larger models, and prepare the project to use a GPU allocation. I confirmed VPN
and login access and shared the cluster's GPU/environment menus and launch output.

### How I checked it
Codex read the inventory and official cluster/Ollama documentation, then created
`feat/gpu-cluster-inference`. The local suite passed 282 tests. Mock HTTP tests
check that CPU remains the default, GPU mode removes the CPU override, policy
cloning retains device selection, and GPU benchmark setup rejects a runtime
that reports no GPU offload. The Linux launcher's Bash syntax passed inspection.
These are local checks, not evidence that a model has run on the cluster GPU.

### What I kept or changed
Added explicit CPU/GPU selection and GPU loading records in benchmark reports.
The cluster launcher requires an allocated Slurm GPU job and approved model
storage, preserves the scheduler's visible devices, and binds only to loopback.
I selected the Blackwell option and Python-only notebook environment. The notebook
job reported running on the Blackwell node. Opening it requires the printed SSH
tunnel to remain running in a separate local terminal.

The inventory and model pages suggest larger candidates, including a quantized
122B model, but actual VRAM, driver support, job RAM, storage quota and answer
quality must be checked before claiming a fit or an improvement. The notebook
URL token and password are not committed. CPU results remain historical CPU
results; no GPU benchmark scores have been recorded yet.

## 2026-10-27 - Run the allocated MIG GPU model and reconnect the app
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `components/policy_index.py`, GPU regression tests,
  `scripts/start_cluster_ollama.sh`, `.env.example`, `docs/gpu-cluster.md`,
  `docs/finals-nisha.md`, `docs/benchmarks/2026-10-27-gpu-summary.json`
- **Outcome:** Changed

### What I asked for
Use the available cluster GPU for a larger synthesis model, then resume the
session after my laptop shut down and connect it to the application.

### How I checked it
The notebook showed a 24,192 MiB MIG slice of the 96 GB Blackwell card, four CPU
cores and 32 GB allocated host RAM. Codex found the course-provided Ollama runtime
and model pool and started a private loopback server inside the GPU allocation,
preserving the scheduler's MIG identifier. No shared models were downloaded,
deleted or changed. The provided `qwen3.8:latest` tag reported 27.3B Q4_K_M;
its reported loaded size equalled its GPU-memory footprint at 4K context.

The actual 12-case fixed-evidence development run passed 11/12 automatic
outcome/coverage checks, answered all ten answerable cases, correctly withheld
both insufficient-evidence cases, and had no engine errors. Median wall time
was 2.825 seconds; the first case took 23.546 seconds. Three additional real
application-graph questions answered and passed verification, including the
multi-grant request that previously timed out on the laptop CPU.

After the laptop restarted, Codex checked that the notebook kernel and private
server survived, verified the compute-node SSH host fingerprint through the
authenticated notebook, and confirmed the second SSH model tunnel responded.
Local embeddings, backend and frontend were restarted. The complete Python suite
passed 285 tests after the local embedding server was available, and the updated
cluster launcher's Bash syntax passed. A first test run while that embedding
server was stopped had one retrieval failure; it passed after restoring it.
The multi-grant question then answered and verified in 12.637 seconds through
the frontend's real HTTP proxy, backend and direct GPU tunnel. The remote server
again reported the full loaded model footprint in GPU memory. This was an HTTP
integration check, not a browser click-through.

### What I kept or changed
Added a separate embedding-server URL so generation can use the GPU while the
existing EmbeddingGemma/Chroma index stays local. Added tests for default,
inherited and separate embedding endpoints. The launcher can discover the
approved shared binary and choose an unused loopback port. CPU remains the
default, and cluster credentials, notebook tokens, raw outputs and session
addresses stay outside committed artifacts.

The GPU score is not held-out policy accuracy. Human quality review is pending,
and hardware, model and runtime differ from the historical CPU comparison.
SYN-08 asks only for the family loan-income ceiling but its gold also requires
extended-family and singles ceilings; the model's family quote verified. This
is recorded for label review without altering labels or upgrading the 11/12
score. The provided model tag is recorded as reported, without claiming it is
the newest upstream release. Shared filesystem free space is not personal quota.

## 2026-11-06 - Finals adversarial policy checks and responsible-AI record
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** policy verifier/guardrails, `llm.py`, `evaluation/policy_safety.py`,
  `data/benchmarks/policy_safety_cases.json`, safety tests, `.env.example`,
  Settings privacy wording, README, finals guide, responsible-AI record and
  curated live-result summary
- **Outcome:** Changed

### What I asked for
Finish my policy/verifier responsible-AI work after discussing MCP, mutation
testing, feedback, privacy and system evaluation with the team. Codex created
`feat/nisha-finals-safety-evaluation` from the latest merged main, including
Tasha's CI changes. The separate policy-refresh fix is not part of this branch.

### How I checked it
The full suite passed 429 tests with four existing expected router failures.
Thirty-four focused safety/oracle tests require no Ollama or external tracing.
They exercise malicious quoted instructions, changed nonnumeric eligibility
wording, empty quotes, invented citations, malformed drafts, bounded repair,
safe claim pruning, outage detection and positive controls. A real local SDK
span checks content redaction; network calls are prohibited in that test. The
benchmark's selected model also wins over an unrelated application environment
override, preventing misleading model labels.

The actual CPU Qwen2.5:3b run used 16 fictional development cases through the
production graph: 16/16 automatic checks passed, all eight answerable cases were
answered, the other eight abstained, and all three clean positive controls passed.
There were no engine outages. Eight CPU threads, 4K context, 850 output tokens,
temperature zero, seed 42 and at most one repair were used. Median case time was
9.692 seconds, including two no-inference preflight cases, with 21 model calls.
Raw outputs stay in `.local/reports/`; the curated summary records the model
digest, case hash, per-case outcomes and pending independent human review.

Frontend lint passed with four pre-existing fast-refresh warnings. The production
build passed with the existing large-bundle warning. Stored-generation replay
across 36 historical records gave zero outcome differences between baseline-main
and the new verifier. Five already need an unrecorded repair on baseline with
current evidence, so this does not reproduce old benchmark accuracy scores.

### What I kept or changed
Added narrowly targeted detection of assistant-control and credential-disclosure
instructions in displayed claims, even when those words appear in retrieved
evidence. Non-table model-selected text must preserve its supporting quote;
table output retains canonical source-cell validation. Recognised injection
patterns are a containment heuristic, not complete protection against poisoned
facts, obfuscation or all adversarial prompts.

Ollama trace inputs/outputs now exclude prompts, profiles, passages and answer
text while retaining counts and typed usage/timing data. The example configuration
starts with both tracing flags disabled; existing real .env files are untouched.
The Settings notice now covers configured model services, temporary answer caches
and optional monitoring. It does not promise that browser clearing removes cloud
traces or service caches. Other integrations, metadata and errors still need review.

The responsible-AI record describes controls, ownership, feedback limitations,
privacy, evaluation scope and deployment follow-up. Browser votes do not train
the model. No MCP server, shell tool or scraper activation permission was added
to chat. Bare "Explain PHG conditions." exposed a current router gap; SAFE-16 uses
the full grant name to exercise synthesis, and the gap is documented for Breann.
The team's held-out questions were not read or run. Independent human review,
branch protection/audit triage and the frozen final held-out evaluation remain
team activities; the development pass count is not general safety or accuracy.

## 2026-11-06 - Chat editing, source copying and cancellation follow-up
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** chat components/adapter/API, `answerText.ts`, cancellation context,
  model engine, streaming endpoint, policy evidence selection, focused tests,
  frontend CI test step and `docs/chat-ux.md`
- **Outcome:** Changed

### What I asked for
Check the slow/failed grant answers, add editing and resending after stopping a
response, and include sources when copying an answer. I clarified that old saved
questions were welcome, and asked who added saved chats. Git history attributes
that feature to Sandra's `1fa9f84`; Codex preserved the existing saved history.

### How I checked it
Codex created `fix/chat-edit-copy-and-responsiveness` from the safety-evaluation
branch. All 440 backend tests passed with four existing expected router failures.
Five new frontend clipboard tests passed; lint/build passed with existing warnings.
Cancellation tests cover both prefill and partial tokens, complete-draft assembly,
timeout, per-request isolation and prevention of partial-response caching.

A new HTTP request using my multiline first-timer EHG/PHG combination question
answered and passed verification in 26.903 seconds, using a fictional profile
and real dated retrieval. Both reported query variants route to policy in the
current code. A stopped HTTP stream closed after 0.214 seconds, followed by an
answered deterministic PR-couple request in 0.149 seconds. These are individual
observations, not controlled model-latency comparisons.

Visual browser automation was attempted. The browser host was unavailable, and
native Edge app access timed out. The feature has build/API/unit verification;
manual Stop/Edit/Copy click-through remains explicitly pending.

### What I kept or changed
Added the assistant-ui edit composer and a clear stopped-response message.
Copy now includes numbered sources, URLs, dates, overview/income notes and demo
warnings. A disconnected streamed request cancels its internal model HTTP call,
including while waiting for headers; tokens remain private until the complete
draft is verified. Interrupted responses are not cached. The runtime controls
how quickly its compute stops after HTTP cancellation.

Narrow stacking questions can use a single complete source that states the grant
relationship and prerequisite, subject to household-scope checks. Broader amount,
income, eligibility and new-flat questions retain their wider evidence. Tests
cover those boundaries, and explicit missing-evidence errors still force repair
or abstention. No policy facts, snapshots, numeric-price logic or stored chats
were rewritten. The loading message now reflects possible multi-minute CPU work.
## 2026-11-08 - Policy mutation checks and final readiness
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `scripts/mutation_test_policy.py`, `tests/test_policy_mutation_runner.py`,
  `tests/test_profile_scope.py`, `.github/workflows/ci.yml`, mutation/readiness docs,
  the responsible-AI record and curated benchmark summary
- **Outcome:** Changed on `test/nisha-policy-mutations`, based on the UI/profile fixes

### What I asked for
Check what remains before finals, whether GPU use/public deployment is worthwhile,
and strengthen Nisha's mutation/security evaluation using the pasted AI checklist
as context. The user has not decided on public hosting. Codex recommended a local
final demo and private GPU tunnelling; no deployment or cluster session was started.

### How I checked it
Reviewed the existing safety suite, price mutation runner, CI and outstanding PRs.
PR #16/#17/#18 heads were unchanged from the prior review, so their fixes remain
pending. The pasted checklist was not installed as AGENTS.md or treated as proof
of course requirements, external enforcement or an immutable audit log.

The new runner's 108-test unmodified baseline passed. It injected 20 documented
faults in private code copies; all 20 were detected, with no survivors or runner/
setup errors/timeouts. At least one assertion or explicit pytest failure is required;
runtime-only exceptions cannot count. Some retry mutants also exhaust scripted
test responses, and those runtime exceptions are recorded separately. The first
baseline attempt found a missing copied chunk fixture and scored zero mutants;
the fixture-copy boundary was corrected before the reported run.

Fifteen runner tests cover error/timeout classification, no credentials/held-out
path in the child environment, copy-only mutation and cleanup. One existing
profile test gained an explicit non-null assertion before tuple indexing. The
final full suite passed: 493 passed, 1 skipped (no vector index in this isolated
checkout), 4 existing expected failures. Workflow YAML and whitespace checks pass.
The official upload-artifact v6 tag was resolved and pinned to its immutable SHA.

### What I kept or changed
No production verifier/model/profile logic was changed for the score. The runner
uses existing behavioural tests, copies selected public fixtures and code into
checked temporary directories, strips inherited service/cloud keys, disables
tracing/plugins and blocks real HTTPX transports in tests. It creates no symbolic
links to the live checkout and never opens the private held-out split. No GPU,
live model calls, new Python packages or external records were used.

Added CI execution after pytest and a 14-day JSON artifact, plus a curated summary
without local paths or per-test payloads. The docs separate development controls
from runtime safeguards, list remaining PR/integration/privacy/redirect checks,
and put live dev evaluation before a versioned freeze and fresh held-out run.
They explicitly note that logs are Git-versioned, dependency audit is report-only,
branch protection is unverified, and public hosting needs separate safeguards.
Human review, pushing, hosted CI, PR merges and final live/held-out evaluation
remain pending. This is not a claim of complete security or independent assurance.

### Integration refresh — 9 November 2026
Merged main through PR #22 without rewriting the published branch. All 20 exact
mutation anchors still match current code. Reran 109 baseline tests and all 20
mutants: 20 killed, no survivors and no errors/timeouts. The 15 runner tests pass;
full pytest reports 700 passed, 1 skipped and 2 existing expected failures. This
checkout has no built vector index, so applicable tests use keyword fallback;
no live model, GPU or held-out evaluation was used. Added a separate dated summary
in `docs/benchmarks/2026-11-09-policy-mutation-summary.json`, preserving the earlier
108-test result as historical evidence. Updated readiness notes to reflect merged
PRs and retained unresolved runtime/manual checks. CI keeps the blocking offline
mutation check and includes the bounded Gitleaks download retry from PR #23.
Then merged Sandra's #21 results/documentation update. Mutation source, runner
and selected test hashes are unchanged, and the final full pytest rerun again
passed 700 tests (1 skipped, 2 expected failures). The branch is pushed; the
GitHub integration rejects PR creation with HTTP 403, so a prepared comparison
link is supplied for submission. No held-out questions or active data changed.

## 2026-11-07 - Profile scope, source tables and scrolling follow-up
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** BuyerProfile/state/profile controls and `profile_context.py` from the saved
  profile commit; follow-up changes in `graph.py`, `policy_synthesis.py`,
  `policy_guardrails.py`, frontend layout/thread/source formatting, new regression
  tests, and `docs/chat-ux.md`
- **Outcome:** Changed on `fix/chat-edit-copy-and-responsiveness`

### What I asked for
Resume the second-timer profile, blank-space scrolling and grant chart/formatting
fixes after the laptop shut down. Keep the policy watcher on its separate branch.

### How I checked it
Confirmed the profile edits survived in commit `eb73bbe`, despite its misleading
"policy watching" message. Added 18 profile regressions, including a production
graph check that a second-timer personal EHG request stops before retrieval/model
execution, mixed-household distinctions, missing/contradictory inputs, current
profile precedence over history, specialised PDF scope, and unrelated price queries.
A real local HTTP request returned the second-timer scope explanation with no
citations or model step. The frontend's 12 tests pass, including every range and
amount from the actual committed non-resident-spouse PDF chunk, half-income labels,
clipboard provenance and refusing to reconstruct partial/altered number lists.
Lint passes with four existing React refresh warnings; production build passes
with the existing large-bundle warning.

The first full backend run found an unavailable local embedding dependency after
shutdown. Restarted the existing local Ollama server, reran the affected retrieval
test successfully, and completed full regression testing. No GPU cluster was used.
Final backend result: 479 passed and 4 existing expected failures. This count is
for the UI/profile branch; the isolated watcher branch has its own test additions.
Tried browser inspection using the computer-use skill: the native helper worked,
but user input interrupted the navigation; the separate browser host was unavailable.
Visual scrolling/mobile/chart checks remain manual and are listed in the guide.
No real personal profile or trace data was submitted for these tests.

### What I kept or changed
The profile distinguishes first-timer, second-timer and mixed households. Personal
"like me" questions request required inputs or explain a source-scope limitation.
First-timer ceiling comparisons are withheld for second/mixed profiles. The
verifier checks specialised PDF opening qualifications even when page titles are
generic. A general hypothetical cohort can differ from the sidebar without
contradictory subsidy fields reaching the model. Pure price queries remain usable
without fixing unrelated eligibility details.

Replaced the live sidebar-based historical chart highlight with clearly labelled
source tables and optional collapsed charts. Half-household-income tables retain
that basis and explicit household scope, without implying a personal grant award.
Complete verified source-band blocks are formatted as tables for display/copy;
surrounding conditions, source values and citations remain. Historical response
metadata is rendered through the same formatter without rewriting saved chats.
Constrained outer page overflow and bounded the chat viewport/footer to address
the blank-space scrolling. No policy facts, snapshot files, active version or
price calculations were changed. Clarifications/charts are code; policy excerpts
are selected by the LLM and verified against source text.

## 2026-11-07 - Reviewed policy website watcher
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `.github/workflows/policy-refresh.yml`, `scripts/policy_watch.py`,
  `scripts/scraping/refresh.py`, `scripts/scraping/verify.py`,
  `tests/test_policy_watch.py`, `tests/test_policy_refresh.py`,
  `docs/policy-watcher.md`, `data/README.md`, `README.md`
- **Outcome:** Changed on `feat/nisha-policy-watcher`

### What I asked for
Look into a watcher for changes on our HDB/CPF policy sources, using the team call
as context, then implement it alongside Tasha's separate user-feedback workflow.

### How I checked it
Codex inspected the existing monthly refresh and diff scripts before extending
them. The watcher/refresh checks pass: 54 tests, including a real text diff with
changed household conditions but identical dollar-amount sets. Temporary snapshots
exercise missing pages/PDFs, failed extraction, missing figures, unsafe/mismatched
dates, blocked access, pending PRs, duplicate alerts and GitHub permissions errors.
A real Git commit/push test uses only a temporary local bare repository; GitHub
responses are simulated. It checks the published branch contains inactive data
and excludes unrelated files, with no push to main or change to ACTIVE.
The final full suite passed: 493 passed, 1 skipped (the isolated checkout has no
vector index), and 4 expected failures. No held-out evaluation was run.

The Windows sandbox initially blocked Git's local transport process in that test;
the test passed with the process restriction lifted. A regex-only diff test also
exposed an unnecessary eager BeautifulSoup import; that import now occurs only
when the HTML verifier runs. This keeps offline CI checks independent of scraping
dependencies. Workflow YAML parsing and whitespace checks were performed too.

### What I kept or changed
Created an isolated worktree from current main so unfinished profile/chat changes
remain untouched. Changed polling to Monday 10:17 SGT plus maintainer-triggered
runs on the default branch. The watcher records changed, unchanged, blocked,
incomplete and failed states, and source-check/report-analysis timestamps.
Complete changes prepare a draft snapshot PR instead of pushing directly to main.
Repeated problems update one attention issue. An existing candidate is preserved;
new evidence stays in the workflow artifacts rather than overwriting its review.
Missing pages/figures hold candidate publication for investigation. Refreshing the
active or an older dated snapshot is refused before fetching.

ACTIVE, chunks, topic cards, deterministic income rules, prices, model settings,
the vector index and held-out data were not changed. Activation remains a separate
review with regeneration, validation, index building and backend restart. The guide
explains GitHub PR permissions/CI approval, monitoring limitations and the frozen
evaluation boundary. No live scrape, issue, PR, external push or activation was run
for implementation testing. A hosted run is still needed to verify actual GitHub
permissions and current website accessibility. Feedback collection and LangSmith
annotation remain Tasha's work; existing privacy filters were not relaxed.

### Integration refresh ? 9 November 2026
Merged main through PR #22 and resolved the workflow conflict by retaining
Sandra's inactive chunk/card build and validation step. Successful candidates
include their new date folders and registry updates in the draft PR; failed
builds include only snapshot/seeds with an explicit warning. ACTIVE, served
chunks/cards, prices and the index stay unchanged. Added three regression cases
for successful/missing/failed build artifacts. All 57 watcher/refresh checks and
the full suite passed: 721 passed, 1 skipped and 2 existing expected failures.
The checkout has no built vector index; these counts do not claim live hybrid
retrieval or held-out evaluation. The Sources page now says weekly to match the
schedule. Pinned workflow actions match the existing CI pins, and CI includes
PR #23's bounded Gitleaks download retries. Publication tests still use mocks
and a local bare Git remote; no live scrape, notification or activation was run.
A hosted schedule remains necessary to verify actual source access and bot PR
permissions after merge.
Then integrated #21's results/documentation changes and reran full pytest:
721 passed, 1 skipped, 2 expected failures. Frontend tests (12), lint and build
pass with the existing warnings. The branch is pushed; PR submission through the
GitHub connector is unavailable (HTTP 403), so a prepared comparison link is
provided. No live watcher publication or policy activation was performed.

## 2026-11-01 - Policy refresh deprecation and blocked-source handling
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `.github/workflows/policy-refresh.yml`, `scripts/scraping/fetch.py`,
  `scripts/scraping/refresh.py`, `tests/test_policy_refresh.py`, `data/README.md`
- **Outcome:** Changed

### What I asked for
Investigate the failed scheduled policy refresh, then address both the deprecated
GitHub Actions warning and HDB access-denied handling on a separate branch.

### How I checked it
Codex read job 124800881060 in run 41290607456. HDB robots.txt returned HTTP 403,
and the sitemap step stopped before any snapshot commit or review issue. The
Node.js and Ubuntu notices were separate from the failure. The official action
definitions confirm Node24 for checkout v5, setup-python v6 and upload-artifact v6.

The new regression tests simulate inaccessible robots, explicit disallow rules,
challenge pages, ordinary network failures, incomplete block diagnostics, stale
block records and successful completion without fetching live policy websites.
All 21 refresh tests passed within the full suite: 372 passed and 4 expected
failures. The first full run had one unrelated retrieval failure while local
EmbeddingGemma was stopped; it passed after restoring that dependency. Workflow
YAML, publication conditions and extracted shell syntax were also checked.

### What I kept or changed
Created `fix/policy-refresh-node24`, upgraded the actions, and introduced explicit
ready, blocked and failed outcomes. Fetcher access blocks have a dedicated exit
code and structured reason. GitHub mode handles a confirmed block with a notice,
a job summary and a diagnostic artifact; it skips publication and retains ACTIVE.
Local mode still exits nonzero for a block. Other errors continue to fail the job.
Only ready can reach the existing commit/push step. Diagnostics contain the
explicitly named status and fetch-log JSON files, with 14-day artifact retention.

No access restrictions were bypassed, no policy snapshot was refreshed or
activated, and the old failed run was not rerun. This handles a blocked refresh
honestly; it does not restore HDB access or make the existing data newly verified.
Publishing and activation still require a complete run and the existing review.

## 2026-11-09 - New chat selection and title
- **Tool (model):** OpenAI Codex (GPT-6)
- **Files:** `frontend/src/components/Layout.tsx`, `frontend/src/lib/history.ts`,
  `frontend/src/lib/chat.tsx`, `frontend/tests/history.test.ts`,
  `frontend/tests/sourceContent.test.ts`, `docs/chat-ux.md`
- **Outcome:** Changed on separate branch `fix/new-chat-selection`

### What I asked for
Fix New chat showing the welcome screen while retaining an earlier chat's name
or selection. The user supplied a screenshot from the GPU-connected test app.

### How I checked it
Added six regression tests covering fresh selection, first-question naming,
reopening old messages, intermediate reset notifications, composer clearing,
repeated empty drafts, active-chat deletion and resuming saves after errors.
All 18 frontend tests passed. Lint passed with four existing React refresh
warnings; the production build passed with the existing large-bundle warning.
The first test run exposed outdated EHG fixture IDs in main's existing source
table tests. Included the same two-line fixture correction already present in
Breann's pending router PR; no policy text or source values changed.
Browser click-through remains a manual check; these counts are frontend tests,
not a repeat of GPU model quality or backend evaluation.

### What I kept or changed
Empty drafts now appear as one selected New chat row without accumulating saved
empty chats. The first sent question supplies the title, including the browser
tab title. Conversation switching pauses saves during replacement, cancels the
client request and clears the composer. Clicking the current conversation does
not discard its draft. Earlier saved conversations and profile values remain.
The source changes were also applied to the isolated local GPU frontend preview;
no model restart, database change, automatic main merge or backend change was
needed. Stopping the client is not a claim of immediate remote GPU cancellation.

### Follow-up: Gitleaks download reliability
PR #23's CI run 42568039899 passed backend, frontend and audit jobs, but GitHub
returned HTTP 504 while downloading Gitleaks. The scanner did not run. Added four
bounded curl retries, connection/transfer timeouts and a retry time budget to the
existing install step, using curl's documented transient-error handling. The
pinned version/hash, SHA-256 verification, scan range and blocking exit code remain.

Exercised the actual YAML install shell with Git Bash against a localhost fault
server and an inert archive: two 504s then success recovered on request three;
permanent 504 stopped after five total attempts; HTTP 404 failed after one;
an incorrect checksum failed before extraction. All four checks passed. A new
hosted run is triggered by pushing this follow-up; local checks do not establish
that the GitHub release endpoint has recovered or that the secret scan has passed.

### Review follow-up — 9 November 2026
Documented that switching chats during generation cancels the client request and
can leave the old question without a completed reply. Added two integration
regressions using the installed assistant-ui runtime rather than mocked reset
events. Each deliberately releases an old stream after cancellation, checking
that it cannot alter a new draft or an existing saved conversation. Both pass;
no late-update leak was reproduced in these scenarios, so no speculative runtime
rewrite was added. Frontend tests now total 20 passed. Browser tab titles also
follow Sources and Settings instead of showing the current conversation there.
Lint/build are checked again; GPU execution and held-out evaluation are outside
these tests. PR descriptions are prepared separately for review.

## 2026-11-09 — Integrated finals gap review

- **Tool (model):** OpenAI Codex (GPT-6)
- **Branch/base:** `fix/finals-integration-gaps`, from merged main `19eeaec`
- **Scope:** Policy prompt/verifier, bounded graph retrieval, price-filter
  extraction/provenance, reproducible dev evaluation, HTTP redirect validation,
  feedback export, Windows mutation portability, dependency audit and handoff.

### What I asked for

After PRs #23–#26 merged, review and address the remaining gaps. Keep main and the
reviewed data/evaluation labels intact; prepare changes separately for review.

### What I kept or changed

Preserved the one-repair limit, 0.20 relevance threshold, quote/numeric checks and
read-only price data. Mixed prompts now separate policy questions from SQL prices.
Footnote markup is normalised without dropping its reference number; verified
table scope and explicit age/percentage aspects contribute to relevance.
Missing policy evidence can use one rewritten local search inside the existing
repair. Existing SQL results are reused. This is not an unrestricted agent loop.

Purchase-target flat/town extraction, lease/floor propagation and verifier checks
address lost/misapplied SQL filters. Partial date coverage is disclosed instead of
silently appearing complete. Removed two strict expected-failure markers only
after the unchanged Stage 1 labels passed. No label, snapshot or SQL figure was
edited to improve a score. Local eval dates are pinned, scripted follow-ups are
consistent, and initial-response/final routes remain separately inspectable.

The scheduled HTTP fetcher now checks redirect hops before contacting them. CSV
review exports escape formula prefixes. Windows price mutations copy tracked
inputs without administrator/symlink privileges. The frontend lockfile has
compatible updates plus a scoped TypeScript-ESLint minimatch override. CI audits
the RAG extra as well and retains JSON findings; it remains report-only.

The actual laptop environment had advisories missed by a fresh core/dev audit.
Recorded versions, then updated pip/setuptools/certifi/oauthlib. Chroma 1.5.9 has
unpatched advisory records; they are not ignored. The app uses a local persistent
store without a Chroma HTTP service or user-defined embedding configuration.
This exposure assessment does not patch the library or approve public hosting.

### How I checked it

- Full laptop suite with the index: **828 passed** after the package updates.
- Separate fresh core/dev environment: **827 passed, 1 skipped** (no Chroma/index).
- Frontend: **20 passed**, lint/build pass with four existing refresh warnings
  and the bundle-size warning. `npm audit`: zero entries after fixes.
- Validated **898 chunks / 12 cards**, including raw-source checksums and quotes.
- Policy mutations: **20/20 detected**, 109-test baseline, no errors/timeouts.
- Price mutations: **374/390 (95.9%)**, 16 survivors. Its legacy runner counts
  nonzero test exits as kills; this is not the stricter policy-runner assertion
  classification or a whole-project security score.
- Read-only dev routing/filter/SQL checks: **50/50**, **23/23**, **23/23**.
- GPU 50-dev run: final-route 47/50, initial-response-route 49/50, 0/8 labelled
  unsafe answers, 5/42 over-abstentions, zero uncited answers/availability errors,
  and 19/19 answered price cases matching figures **and** filters. The single raw
  staleness screen remains for human cohort/context review. Recorded source
  hashes match the retained runtime; historical diagnostic attempts stay separate.
- Live synthetic safety: default Qwen2.5:3b CPU **16/16**, including **3/3**
  positive controls. Shared 27.3B GPU tag **14/16**, with **1/3** positive controls;
  no availability errors. The larger model over-refused two clean cases. A prompt
  experiment did not fix those misses and was reverted; its run is not reported
  as the retained implementation. No broad safety/accuracy guarantee follows.

### Remaining review

Retrieval/card targets and five development abstentions still need component
review. Browser interaction, root/node tracing privacy, retention, hosted watcher
permissions/access and independent semantic/held-out evaluation remain explicit
team actions. The active GitHub ruleset requires a PR but zero approvals and no
required-status rule; Breann must verify/update server-enforced controls.
Cross-component changes expand my tuning involvement, so held-out author
independence assignments need review. No held-out file was opened. Raw outputs,
fictional profiles and local runtime details remain under ignored `.local/`.
See `docs/finals-readiness.md`, `docs/dependency-audit.md` and the dated curated
integration summary. These changes still need teammate review before main.

## 9 November 2026 — Follow-up to PR #25/#26 review

Kept the merged reviewed-candidate policy workflow. Limited the policy mutation
step to pull requests targeting the default branch and manual CI runs, avoiding
a duplicate mutation run on the subsequent main push. Full pytest still runs on
main pushes. A blocked HTTPX request now leaves an isolation marker and makes
the mutation result an error, even if a test catches the exception or later times
out; it cannot inflate the detected-fault score. This is an HTTPX guard, not an
operating-system network sandbox.

The policy watcher records the pushed candidate branch before attempting PR
creation and retains the prepared PR body as an artifact. Documented recovery,
bot-workflow approval/manual CI on the exact candidate branch, reviewer ownership,
and repeated candidates while ACTIVE remains unchanged. No automatic branch
deletion or snapshot activation was added. The earlier monthly workflow also
required separate activation; its automatic archive commit did not update the
served policy. Repository Actions permissions still require owner verification.

Validation: the laptop suite passed **834 tests**; the fresh core/dev environment
passed **833 with 1 expected skip** without Chroma/index. The sandbox first blocked
the temporary local Git publication test; rerunning with local subprocess access
passed. The stricter mutation runner
detected **20/20** curated faults with a passing **109-test** baseline and no
errors/timeouts. Added regressions include a real subprocess whose test catches
a blocked HTTP request; the runner still rejects the result. No GPU rerun was
needed for these CI/tooling/documentation changes. No hosted watcher run, issue,
or candidate PR was published as part of this follow-up. These results do not
establish whole-project security or replace independent held-out evaluation.

## 9 November 2026 — Exact-floor and period follow-up regression

Reproduced the user's three-turn price/floor/2027 conversation. Exact floors
cannot be represented by the existing SQL floor bands. The router now requests
a supported band and disambiguates the lease question, instead of attempting a
policy answer that the verifier rejects. It does not silently treat floor 16 as
all high-floor transactions. An explicit band choice can proceed with a scope
notice. Clarification preserves the original price context for later period
questions, but an unrelated standalone policy question resets that context.
Scope guards still take precedence over follow-up inheritance.

Added 11 regression cases. Full backend suite: **845 passed**. The live API on
the GPU-connected integration checkout returned the correct 3-room Tampines
result, then a floor/lease clarification in 0.126 seconds and a database-coverage
explanation for 2027 in 0.106 seconds. These two follow-ups need no model call.
The shared model was verified loaded entirely in the new job's GPU memory;
embeddings and SQLite remain local, with tracing disabled. Timing is a single
development observation, not a controlled speed or accuracy benchmark. Earlier
broader benchmark reports retain their prior source hashes and were not rerun
or relabelled as results for this follow-up commit.

Used the computer-use skill to inspect Edge. The recent-sales disclosure was
closed, and expanding it visibly displayed all five populated transaction rows
and column headings. No frontend/SQL rewrite was needed: the pasted blank grid
was the collapsed table's copy representation. Confirmed the app already running
on port 8000 caused the duplicate-server error; restarted that single backend to
load the fix. Main and the root checkout remain unchanged.
