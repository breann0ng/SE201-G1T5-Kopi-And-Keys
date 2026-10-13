# Kopi & Keys

HDB Resale Policy & Price Benchmark Advisor — SE201 G1T5.

This is the backend starting point. It runs the proposed control flow with a
**demo advisor and fictional policy passages**. It does not give HDB advice or
connect to an LLM yet.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn kopi_keys.main:app --reload
```

Open http://127.0.0.1:8000/docs for the API playground.

`POST /chat` example:

```json
{
  "message": "Explain the demo programme and its related condition."
}
```

This deliberately retrieves a programme passage, discovers a reference to a
second condition, retrieves again, then verifies the cited answer. Responses
include `mode: "demo"` and a small execution trace. Real HDB questions abstain
until official evidence and a model adapter are connected.

Other requests:

- `{"message": "What are resale prices?"}` demonstrates clarification.
- `{"message": "What grants can we get?"}` demonstrates abstention without official evidence.
- `GET /health` reports service health and demo mode.

## Architecture

```mermaid
flowchart TD
    U[POST /chat: message and optional profile] --> V[Validate request]
    V --> A[Advisor: discovery and synthesis]
    A -->|Search or reformulate| R[Policy retrieval tool]
    R -->|Passages and metadata| A
    A -->|Validated filters| S[Price query tool]
    S -->|Executed query results| A
    A -->|Missing buyer information| C[Clarifying question]
    A -->|Insufficient evidence or budget exhausted| X[Abstention]
    A -->|Draft claims and citation IDs| G[Deterministic verifier]
    G -->|Pass| O[Answer with sources and query results]
    G -->|Repairable: one retry| A
    G -->|Second failure| X
```

The Advisor sees one shared state: the request, buyer profile, accumulated
passages, price result, previous queries, verification errors and call counts.
Tool results return to the Advisor, so it can request missing evidence. Code
enforces three retrieval calls, one price call, one verification repair and an
overall Advisor-step limit. Repeated identical policy queries stop the turn.

## Project layout

```text
backend/kopi_keys/      Application package (installed via pyproject)
  main.py               FastAPI entry point and dependency wiring
  schemas.py            Validated request, decision, evidence and response models
  state.py              Shared LangGraph state
  workflow.py           Advisor/tool/verifier graph and budgets
  advisor.py            Advisor interface and temporary demo implementation
  verifier.py           Citation and source-metadata checks
  tools/
    policy.py           Retrieval interface and fictional demo retriever
    price.py            Price-tool interface and read-only SQLite adapter
policy/
  sources.yaml          Registry of official policy snapshots (URL, dates, supersession)
  topic_cards/          Reviewed topic cards (versioned JSON)
scripts/
  build_resale_db.py    CSV -> data/processed/resale.db with indexes and import metadata
data/                   Raw downloads and generated indexes (mostly gitignored)
eval/                   Labelled datasets, run_eval.py, dated results
tests/                  Deterministic workflow and API checks (pytest)
docs/architecture.md    Integration plan and current boundaries
.env.example            Model names, data paths, optional LangSmith settings
```

Rebuild the resale database after downloading a new CSV into `data/raw/`
(pass the download date for provenance). The import is rejected, leaving any
existing database untouched, if any row fails validation. Exact duplicate rows
are kept and counted; see the script docstring for why.

```powershell
.\.venv\Scripts\python.exe scripts\build_resale_db.py --downloaded-on 2026-10-13
```

Once built, `POST /chat` with `price_filters` answers from the database
(`SqlitePriceTool`); without it, price questions abstain. Override the location
with `RESALE_DB_PATH`.

Run the evaluation smoke set:

```powershell
.\.venv\Scripts\python.exe eval\run_eval.py eval\dataset\smoke.jsonl
```

## Check the foundation

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The API is stateless between requests. A supplied buyer profile is shared within
that request; conversation memory and profile extraction will be added later.
The verifier checks citation presence, known source IDs and superseded flags.
It cannot establish semantic entailment or certify eligibility.

The graph follows the [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
The API follows [FastAPI's application pattern](https://fastapi.tiangolo.com/tutorial/first-steps/).
