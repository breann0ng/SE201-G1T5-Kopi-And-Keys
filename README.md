# Kopi & Keys

HDB Resale Policy & Price Benchmark Advisor — SE201 G1T5.

The original `/chat` backend runs with a **demo advisor and fictional policy
passages**. Person 3's revised midpoint implementation is available separately:
real CPU Ollama inference, a SQL-result Synthesizer and a numeric verifier.

## Person 3 midpoint (Nisha)

```powershell
# One-time download; subsequent runs restart/reuse the project-local server.
.\scripts\setup_ollama.ps1

# Run Stage 3 -> Stage 4 with clearly labelled synthetic SQL statistics.
.\.venv\Scripts\python.exe -m kopi_keys.midpoint.cli --input examples\midpoint_sql_result.json

# Confirm installation and inspect loaded model CPU/GPU status.
.\.venv\Scripts\python.exe -m kopi_keys.midpoint.cli --check-engine
```

On this workspace Ollama and `qwen2.5:3b` have already been downloaded under the
ignored `.local/` directory. The setup script starts a background server on
`127.0.0.1:11434`; it does not add a Windows startup service. Every synthesis
request sets `num_gpu=0`.

Read [Person 3 setup and team handoff](docs/person3-midpoint.md) for the SQL
contract, node integration, verifier rules and observed smoke-test results.
The existing `/chat` endpoint still uses the original demo graph; Breann can
connect the new Stage 3/4 subgraph after Tasha's SQL node.

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
backend/kopi_keys/
  main.py           FastAPI entry point and dependency wiring
  schemas.py        Validated request, decision, evidence and response models
  state.py          Shared LangGraph state
  workflow.py       Advisor/tool/verifier graph and budgets
  advisor.py        Advisor interface and temporary demo implementation
  verifier.py       Citation and source-metadata checks
  tools/
    policy.py       Retrieval interface and fictional demo retriever
    price.py        Price-tool interface; currently reports unconfigured
tests/              Workflow and API checks
docs/architecture.md  Integration plan and current boundaries
data/README.md      Planned policy and transaction data layout
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
