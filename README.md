# Kopi & Keys

HDB Resale Policy & Price Benchmark Advisor — SE201 G1T5.

The app combines an official HDB/CPF policy snapshot, deterministic resale
statistics from SQLite, and a local Ollama model in one LangGraph workflow.
The React frontend shows answers, sources, price comparisons and clarification
questions. It explains published conditions and past transactions; it does not
confirm personal eligibility or value an individual flat.

## What is implemented

- **Query routing:** rules and regex classify policy, price, mixed and discovery
  questions, with an optional constrained LLM intent fallback for weak/unmatched
  rules. Extraction includes the purchase target, supported lease/floor bands,
  profile values and dates; missing information produces a clarification.
- **Policy retrieval:** keyword ranking fused with EmbeddingGemma vectors in
  ChromaDB, with keyword fallback when the index or embedding service is
  unavailable. The ACTIVE snapshot currently contains 898 chunks.
- **Prices:** a connected, read-only SQLite tool calculates mean, median, IQR,
  range and volume from the shared resale CSV. Filters include town, flat type,
  dates, remaining lease and floor band. Fewer than five matching sales are
  listed instead of summarised with a median.
- **Topic cards:** 12 JSON cards support suggestions, source overviews, profile
  hints and verified income-ceiling notes. Some card inputs are not collected yet.
- **Synthesis and verification:** Qwen2.5:3b selects cited policy excerpts and
  formats price statistics. Deterministic checks validate quotes, citations,
  table scope and generated price figures. A failed draft gets one repair
  attempt, which may first retry a local search for explicitly missing policy
  evidence; an unverifiable answer is withheld. Clarifications and some scoped
  citizenship-table responses use code directly.
- **Safety and scope:** forecasts, guarantees, single-flat valuations, eligibility
  confirmations and instruction-like text are declined with a reason. Policy
  guardrails limit answers to in-scope official sources.
- **Frontend:** profile sidebar, clarification buttons, live graph progress,
  source tables/charts, price refinement ("Narrow it down") and browser-local
  recent chats.
- **Feedback loop:** thumbs up/down with optional reasons under every answer,
  stored write-only for human review and attached to the LangSmith trace when
  tracing is on. Feedback never changes prompts, retrieval or the model; confirmed
  problems become a code or data fix with a regression test. See
  [the feedback guide](docs/feedback-loop.md).
- **Data freshness:** weekly [policy](docs/policy-watcher.md) and
  [price](docs/price-watcher.md) watchers prepare inactive candidates for review.
  They never activate data automatically; a person switches `ACTIVE`.

See [the architecture guide](docs/architecture.md) for the component map and
[the data guide](data/README.md) for sources and provenance.

## Requirements

- Python **3.11 or newer**.
- Node.js **22 or newer** and npm for the frontend.
- Ollama with `qwen2.5:3b` for text generation and `embeddinggemma` for hybrid
  retrieval. The Windows script can install a project-local runtime.
- Disk space for the runtime, models and generated databases. By default text
  generation requests set `num_gpu=0`; CPU responses can take tens of seconds or
  longer. Allocated GPU inference is opt-in.

Run setup commands from the repository root. Policy data, topic cards and the
resale CSV are committed. Each laptop builds its own SQLite database and vector
index; generated data and models are ignored by Git.

## First-time setup

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,rag]"

# Starts project-local Ollama and downloads the models.
.\scripts\setup_ollama.ps1
.\scripts\setup_ollama.ps1 -Model embeddinggemma

# Build from the team's committed snapshots. Wait for both scripts to finish.
.\.venv\Scripts\python.exe scripts\build_resale_db.py --downloaded-on 2026-10-14
.\.venv\Scripts\python.exe scripts\build_policy_index.py

cd frontend
npm ci
cd ..
```

The Ollama script keeps its runtime, models and logs in `.local/` and leaves the
local server running. If a system Ollama server is already running, use that
installation to run `ollama pull qwen2.5:3b` and `ollama pull embeddinggemma`
instead of the project-local setup script.

### macOS / Linux

Install and start Ollama first, using its desktop app or `ollama serve` in a
separate terminal. Then:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,rag]"
ollama pull qwen2.5:3b
ollama pull embeddinggemma
.venv/bin/python scripts/build_resale_db.py --downloaded-on 2026-10-14
.venv/bin/python scripts/build_policy_index.py
cd frontend
npm ci
cd ..
```

The editable install is required to import `kopi_keys`. The `rag` extra installs
ChromaDB. Rebuild the vector index when the ACTIVE snapshot or its chunks change.
Without a built resale database, prices are unavailable. Without working vector
retrieval, policy search falls back to keywords.

## Run the app

Keep Ollama running on `http://127.0.0.1:11434`.

**Terminal 1 — backend, from the repository root:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn kopi_keys.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

On macOS/Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

**Terminal 2 — frontend:**

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

- App: http://127.0.0.1:5173
- API playground: http://127.0.0.1:8000/docs
- Backend health: http://127.0.0.1:8000/health

Vite proxies `/api/*` to the backend on port 8000. The backend is Python, so
`npm run dev` belongs in `frontend/`. If port 8000 is already occupied by your
running backend, use that instance or stop its terminal with Ctrl+C before
starting another.

User messages support **Edit** after generation stops, and **Copy answer and sources**
retains citation URLs and dates. See [chat behaviour and checks](docs/chat-ux.md)
for cancellation, saved-history behaviour and manual verification steps.

### Optional configuration and tracing

Local use does not require LangSmith or `.env`. To configure model options or
tracing, use a local `.env`; see [.env.example](.env.example). The API, CLI and
synthetic-case runner load this file. Keep tracing disabled until a real API key
and the correct region are configured.

For an APAC LangSmith account:

```dotenv
LANGCHAIN_API_KEY=your-own-key
LANGCHAIN_TRACING_V2=true
LANGSMITH_TRACING=true
LANGCHAIN_PROJECT=kopi-and-keys
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
```

Never commit the real `.env`. Tracing needs network access when enabled; tests
disable it. Settings include `KOPI_OLLAMA_MODEL` (default `qwen2.5:3b`),
`KOPI_OLLAMA_NUM_THREADS` (default 4), `KOPI_POLICY_MODEL` (optional separate
policy model), warm-up and response caching.

The Ollama trace span records message count and timing/token usage, with message,
profile, evidence and answer contents removed before tracing. Other integrations,
caller-supplied metadata, errors and historical traces require separate review.
Keep tracing opt-in; see the [responsible-AI record](docs/responsible-ai.md) for
data handling, limitations and the development safety checks.

## API and examples

`POST /chat` accepts `message` plus optional `profile`, `price_filters` and up
to 12 recent `history` turns. `POST /chat/stream` returns graph-step events and
the final answer as newline-delimited JSON; the frontend uses this endpoint.

| Message | Expected path |
| --- | --- |
| `What is the resale price?` | Ask for town and flat type; `Yishun, 4-room` can resume the request. |
| `What is the resale price of a 4-room flat in Yishun?` | Query SQLite, format and verify the statistics. |
| `may i know about loans` | Retrieve policy evidence and attempt a verified answer. |
| `Am I eligible for the Enhanced CPF Housing Grant?` | Ask for missing topic-card profile inputs before attempting an answer. |
| `Can a Singapore PR couple buy a resale flat?` | Retrieve and explain the relevant scoped citizenship conditions. |
| `Tell me a joke.` | Abstain as out of scope. |

Responses include `status` (`answered`, `clarifying` or `abstained`), `mode`,
`route`, `message`, `citations`, optional price results and UI fields, and a
node `trace`. The default app reports `mode: "snapshot"`; fictional test graphs
use `demo`. History helps with clarification follow-ups, never as policy evidence.

## Checks and development evaluation

From the root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\scraping\validate.py
.\.venv\Scripts\python.exe scripts\run_price_cases.py --validate-only
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --retriever hybrid
cd frontend
npm run build
npm run lint
cd ..
```

Use `.venv/bin/python` and forward slashes on macOS/Linux. Most tests use local
fixtures; the real vector-retrieval test needs the index and embedding service
and skips when the index is absent. `--validate-only` checks the six price
fixtures and intentional rejections **without model inference**. Omit the flag
for live model checks. The standalone price CLI is:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.cli --input tests\fixtures\price_sql_result.json
```

The backend suite collects 1,100 pytest tests and the frontend has 32 tests
(`npm test`); lint/build retain four React Refresh warnings and the large-bundle
warning. Test counts are tied to their checkout and available services.

Further checks, each with its own guide:

| Check | Command | Guide |
| --- | --- | --- |
| Full system and baselines (no-tools, naive RAG) on the dev set | `python -m kopi_keys.evaluation.run_baselines --system full` (or `no-tools`, `naive-rag-dense`) | [evaluation results](docs/evaluation-results.md) |
| Paired comparison with 95% Wilson intervals and exact McNemar tests | `python -m kopi_keys.evaluation.compare <results files>` | [evaluation guide](backend/kopi_keys/evaluation/README.md) |
| Retrieval report (Hit@5, Recall@5/20, MRR; strict and relaxed labels) | `python -m kopi_keys.evaluation.retrieval_report --mode hybrid` | [evaluation results](docs/evaluation-results.md) |
| Mutation testing: price tool, policy guardrails, retrieval/evaluation | `scripts/mutation_test.py`, `scripts/mutation_test_policy.py`, `scripts/mutation_test_retrieval_eval.py` | [price tool](docs/testing-price-tool.md), [policy](docs/policy-mutation-testing.md), [retrieval/eval](docs/testing-retrieval-and-evaluation.md) |
| Live safety suite (16 prompt-injection and scope cases) | `python -m kopi_keys.evaluation.policy_safety --live` (omit `--live` for the offline check) | [responsible AI](docs/responsible-ai.md) |
| LangSmith experiment, optional LLM-as-judge | `python -m kopi_keys.evaluation.langsmith_eval run` | [evaluation guide](backend/kopi_keys/evaluation/README.md) |

CI (`.github/workflows/ci.yml`) runs on every pull request: backend pytest plus
the offline policy mutation check, frontend lint, tests and build, a report-only
dependency audit (pip-audit and npm audit) and a gitleaks secret scan. CI never
reads held-out questions.

## Evaluation results

The committed development set has **50 questions** across six categories
(policy 7, price 13, mixed 8, discovery 7, changed policy 7, unanswerable 8). It
was used while tuning, so its scores are optimistic. Price labels are computed
with plain SQL on the database, independent of the app. The **held-out set** has
40 questions. Each member drafted the questions for their assigned categories,
outside the parts they built, using a fresh AI chat that had not seen the dev set
or the code; the questions were compiled into one file and checked by a script
that fills expected prices with plain SQL. They were never shown to the coding
assistants. The set is kept outside the repository and was run once on the GPU
against the frozen system (`finals-frozen`), with no changes afterwards
(see [the held-out guide](docs/heldout-guide.md)). Archived, previously exposed
questions are retired, not an unseen test set.

**Final development comparison** (50 questions, qwen2.5:3b, GPU-assisted, commit
`1c4d87c`, 10 November 2026; 95% Wilson intervals, paired exact McNemar tests
against no-tools):

| Metric (population) | Kopi & Keys | No-tools | Naive RAG |
| --- | --- | --- | --- |
| Correct route (50) | 94.0% (47/50) | N/A | N/A |
| Correct price figures (21) | 85.7% (18/21), CI 65.4–95.0% | 0/21 | 0/21 |
| Cited answers (42) | 71.4% (30/42); p = 1.9×10⁻⁹ vs no-tools, 0.557 vs naive RAG | 0/42 | 61.9% (26/42) |
| Answered, not declined (42) | 73.8% (31/42): 30 completed + 1 clarification; p = 0.383, not significant | 61.9% (26/42) | 61.9% (26/42) |
| Not flagged stale (7) | 57.1% (4/7) | 71.4% | 85.7% |
| Safe on should-decline (8) | 100% (8/8) | 87.5% | 87.5% |
| Mean latency | 2.41 s | 0.38 s | 1.01 s |

**Held-out results** (40 questions, same scorer for both columns):

| Metric | Dev (50) | Held-out (40) | Target |
| --- | --- | --- | --- |
| Correct route | 94% (47/50) | 80% (32/40) | ≥ 90% |
| Evidence Hit@5 (policy and discovery questions) | 69% (20/29) | 58% (15/26) | — |
| Answerable but declined | 26% (11/42) | 50% (17/34) | ≤ 10% |
| Should-decline but replied (includes clarifying questions) | 0% (0/8) | 33% (2/6) | ≤ 5% |
| Uncited answers | 0 | 0 | 0 |
| Stale (automatic screen) | 43% (3/7) | 0% (0/6) | 0% |
| Price figures (returned, scored responses) | 100% (18/18) | 88% (7/8) | — |
| Discovery precision / recall | 54% / 93% | 60% / 71% | ≥ 80% / ≥ 70% |

The held-out run shows that grounding held up on new questions but coverage did
not: the rules-first router and the strict relevance check fail closed, so an
unfamiliar phrasing gets a decline rather than a guess. Per-question logs for the
final and held-out runs are in the team's submitted supporting documents;
earlier committed runs (8–9 November) and the retrieval experiments are in
`data/evaluation-data/results/` and [evaluation results](docs/evaluation-results.md).
Manual review of whether every policy claim is fully supported is not finished.

Other development evidence: the price tool's mutation score rose from 66.4% to
95.9% ([testing-price-tool.md](docs/testing-price-tool.md)); all selected policy
guardrail faults are detected ([policy-mutation-testing.md](docs/policy-mutation-testing.md));
the retrieval and evaluation modules rose from 35.7% to 54.3%
([testing-retrieval-and-evaluation.md](docs/testing-retrieval-and-evaluation.md));
and the live safety suite passed 16/16 ([responsible-ai.md](docs/responsible-ai.md)).
Nisha's [implementation and benchmark guide](docs/finals-nisha.md) covers the
12-case fixed-evidence model benchmark used to choose the model.

For an allocated SCIS GPU, see the [GPU cluster guide](docs/gpu-cluster.md).
GPU inference is opt-in; CPU remains the default. GPU benchmark runs check actual
model offload and stop if Ollama falls back to CPU.

## Current limitations

- **Over-cautious on new phrasings.** Held-out routing was 80% and half of the
  answerable held-out questions were declined. Field extraction is rule-based, so
  each new phrasing needs a rule and a test.
- **Old and current rules in one passage.** Some official pages keep a previous
  rule next to the current one; the system can quote the old wording (3 of 7
  changed-policy dev cases). Splitting dated clauses into their own chunks is the
  planned fix.
- **Strict relevance check.** The word-overlap check rejects some correct quotes
  (17 of 42 in the dev audit). Meaning-based checks were tested but let too many
  wrong quotes through to be used as a gate.
- **Targets not met.** Retrieval Recall@5 (74% strict / 83% relaxed vs 85%) and
  discovery precision (54% dev, 60% held-out vs 80%) remain below target.
- **Verification is not full correctness.** Quote, citation, figure, relevance,
  scope and coverage checks establish specific properties; they do not prove that
  every dated condition applies to the user. Manual claim review is unfinished.
- **CPU latency.** Earlier laptop-CPU runs averaged about 87 seconds per question;
  long multi-grant contexts can reach the model timeout and safely abstain.
- Clarification history is bounded and some topic-card inputs are unsupported.
  Chats stay in the browser, with no login or server conversation store. The
  backend records feedback question/answer/rating context in local SQLite for
  human review; optional LangSmith tracing/feedback is separate. Clearing browser
  history does not delete those server/cloud records.
- Prices describe past sales. Block-specific lookups, individual-flat valuations,
  predictions and final eligibility decisions are not provided.

## Project layout

```text
backend/kopi_keys/
  main.py               FastAPI, streaming, response cache, feedback route, warm-up
  graph.py, state.py    One workflow and shared GraphState
  schemas.py            Request, response and tool contracts
  llm.py                Ollama client (CPU default, optional SCIS GPU), redacted tracing
  feedback.py           Write-only answer feedback store and LangSmith feedback
  cli.py                Synthetic price-result runner
  components/
    query_router.py     Rules, extraction and clarification gate
    intent_fallback.py  Constrained LLM intent fallback for unmatched/weak rules
    profile_context.py  Sidebar/message profile merging and conflict checks
    policy_retrieval.py Hybrid/keyword retrieval from the ACTIVE snapshot
    policy_index.py     ChromaDB and EmbeddingGemma index
    price_query.py      Read-only SQLite queries and deterministic statistics
    price_display.py    User-facing verified price summaries
    topic_cards.py      Graph adapter, suggestions and income-note wiring
    policy_synthesis.py Structured quote selection and scoped table facts
    synthesiser.py      Policy/price synthesis and clarification wording
    answer_aspects.py   Coverage of each part of multi-part questions
    verifier.py         Quote, citation, relevance, scope and numeric checks
    policy_guardrails.py Scope and instruction-like text guards
    abstention.py       Fixed abstention messages
  topic_cards.py        JSON card loader and rule-based matcher
  rules/                Income ceiling data and pure Python checks
  ingest/               Resale database, policy index and price watcher
  evaluation/           Dataset, metrics, runners, baselines, statistics,
                        retrieval report, freshness, safety and LangSmith
frontend/               React/Vite chat, profile, sources, feedback and settings
data/                   Policy snapshots, chunks, vectors, cards, resale CSV,
                        benchmarks, dev questions and committed results
scripts/                Setup, builders, validators, watchers, go-live,
                        mutation runners and feedback review
tests/                  Component, graph, API, evaluation and data-contract tests
docs/                   Architecture, evaluation, testing and safety guides
ai-log/                 Team AI-use records
.github/workflows/      CI and the weekly policy and price refresh jobs
```

Further details: [frontend](frontend/README.md),
[policy advisor](docs/policy-advisor.md), and
[price synthesis and verification](docs/price-synthesis-and-verification.md),
[responsible AI](docs/responsible-ai.md) and the
[finals readiness record](docs/finals-readiness.md).
