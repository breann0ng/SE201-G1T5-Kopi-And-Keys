# AI Use Log: H Kahfath Nisha

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
