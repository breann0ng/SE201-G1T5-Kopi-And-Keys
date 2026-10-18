# Kopi & Keys

HDB Resale Policy & Price Benchmark Advisor — SE201 G1T5.

The app combines an official HDB/CPF policy snapshot, deterministic resale
statistics from SQLite, and a local Ollama model in one LangGraph workflow.
The React frontend shows answers, sources, price comparisons and clarification
questions. It explains published conditions and past transactions; it does not
confirm personal eligibility or value an individual flat.

## What is implemented

- **Query routing:** rules and regex classify policy, price, mixed and discovery
  questions, extract profile/filter values, and ask for missing information.
- **Policy retrieval:** keyword ranking fused with EmbeddingGemma vectors in
  ChromaDB, with keyword fallback when the index or embedding service is
  unavailable. The ACTIVE snapshot currently contains 849 chunks.
- **Prices:** a connected, read-only SQLite tool calculates mean, median, IQR,
  range and volume from the shared resale CSV. Filters include town, flat type,
  dates, remaining lease and floor band. Fewer than five matching sales are
  listed instead of summarised with a median.
- **Topic cards:** 12 JSON cards support suggestions, source overviews, profile
  hints and verified income-ceiling notes. Some card inputs are not collected yet.
- **Synthesis and verification:** Qwen2.5:3b selects cited policy excerpts and
  formats price statistics. Deterministic checks validate quotes, citations,
  table scope and generated price figures. A failed draft gets one repair
  attempt; an unverifiable answer is withheld. Clarifications and some scoped
  citizenship-table responses use code directly.
- **Frontend:** profile sidebar, clarification buttons, live graph progress,
  source tables/charts, price refinement and browser-local recent chats.

See [the architecture guide](docs/architecture.md) for the component map and
[the data guide](data/README.md) for sources and provenance.

## Requirements

- Python **3.11 or newer**.
- Node.js **22 or newer** and npm for the frontend.
- Ollama with `qwen2.5:3b` for text generation and `embeddinggemma` for hybrid
  retrieval. The Windows script can install a project-local runtime.
- Disk space for the runtime, models and generated databases. Text generation
  requests set `num_gpu=0`; CPU responses can take tens of seconds or longer.

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

### Optional configuration and tracing

Local use does not require LangSmith or `.env`. To configure model options or
tracing, use a local `.env`; see [.env.example](.env.example). The API, CLI and
synthetic-case runner load this file. Keep tracing disabled until a real API key
and the correct region are configured.

For an APAC LangSmith account:

```dotenv
LANGCHAIN_API_KEY=your-own-key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=kopi-and-keys
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
```

Never commit the real `.env`. Tracing needs network access when enabled; tests
disable it. Settings include `KOPI_OLLAMA_MODEL` (default `qwen2.5:3b`),
`KOPI_OLLAMA_NUM_THREADS` (default 4), `KOPI_POLICY_MODEL` (optional separate
policy model), warm-up and response caching.

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

Checks on **18 October 2026**: 248 tests passed with no skips, snapshot/card
validation and six fixture validations passed, and the frontend built. Lint has
no errors and four existing React Refresh warnings; the production build also
reports a large-bundle warning.

Current development metrics use the committed 30-question set:

| Metric | Result | Target |
| --- | --- | --- |
| Router labels | 100% (30/30) | ≥ 90% |
| Hybrid Recall@5 | 60% (12/20) | ≥ 85% |
| Discovery precision / recall | 38% / 89% | ≥ 80% / ≥ 70% |
| Ask-next accuracy | 67% (2/3) | No target set |

These are development checks, not held-out results or a new full end-to-end
evaluation. Hybrid scores assume the index and embedding service are available.
See [the evaluation guide](backend/kopi_keys/evaluation/README.md) for previous
end-to-end runs and limitations. A fresh held-out set stays outside the repo;
archived, previously exposed questions are retired, not an unseen test set.

## Current limitations

- Correct routing does not guarantee an answer. In the 18 October live review,
  `how do I buy a resale flat?` reached retrieval but abstained after invalid
  model citation IDs. Schema validation currently gives the repair step only a
  generic no-claims error for this failure. The strict verifier remains in place.
- A verified quote can still be incomplete or irrelevant. Household scope,
  retrieval relevance and source-table quality need review.
- Retrieval recall and discovery precision remain below target. The answer-level
  no-tools and naive-RAG baselines are not implemented yet.
- Clarification history is bounded and some topic-card inputs are unsupported.
  Chats and feedback stay in the browser, with no login or server conversation
  store. Optional LangSmith tracing can record runs.
- Prices describe past sales. Block-specific lookups, individual-flat valuations,
  predictions and final eligibility decisions are not provided.

## Project layout

```text
backend/kopi_keys/
  main.py               FastAPI, streaming, response cache and model warm-up
  graph.py, state.py    One workflow and shared GraphState
  schemas.py, llm.py    Contracts and CPU Ollama generation client
  cli.py               Synthetic price-result runner
  components/
    query_router.py     Rules, extraction and clarification gate
    policy_retrieval.py Hybrid/keyword retrieval from the ACTIVE snapshot
    policy_index.py     ChromaDB and EmbeddingGemma index
    price_query.py      Read-only SQLite queries and deterministic statistics
    price_display.py    User-facing verified price summaries
    topic_cards.py      Graph adapter, suggestions and income-note wiring
    policy_synthesis.py Structured quote selection and scoped table facts
    synthesiser.py      Policy/price synthesis and clarification wording
    verifier.py         Quote, citation, table-scope and numeric checks
    abstention.py       Fixed abstention messages
  topic_cards.py        JSON card loader and rule-based matcher
  rules/                Income ceiling data and pure Python checks
  evaluation/           Dev loader, metrics and evaluation runner
frontend/               React/Vite chat, profile, sources and settings
data/                   Policy snapshot, cards, dev data and resale CSV
scripts/                Ollama setup, database/index builders and validators
tests/                  Component, graph, API and data-contract tests
docs/                   Architecture and implementation guides
ai-log/                 Team AI-use records
```

Further details: [frontend](frontend/README.md),
[policy advisor](docs/policy-advisor.md), and
[price synthesis and verification](docs/price-synthesis-and-verification.md).
