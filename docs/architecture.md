# Architecture

The system is one LangGraph graph (`backend/kopi_keys/graph.py`). Every box on
the proposal's architecture diagram is one node and one module under
`backend/kopi_keys/components/`. All nodes read and write a single
`GraphState` (`state.py`).

## Design change from the proposal

The proposal described three LLM stages: Query Router, Discovery Agent and
Synthesiser Agent. We merged the Discovery Agent into the Synthesiser Agent.
Discovery relevance is still decided in code (topic-card matching). Only the
wording and selection of up to three suggestions moved into the Synthesiser's
single model call. This saves one model call per turn on a CPU-bound local
model, and Discovery precision and recall are still scored against
pre-labelled card IDs.

## Box, file, owner and status

| Diagram box | File | Owner | Status |
| --- | --- | --- | --- |
| Query Router (LLM) | `components/query_router.py` | Breann | Rule-based baseline; passes all 30 dev-set labels. LLM classifier not built. |
| Discovery (merged) | `components/topic_cards.py`, `data/topic_cards/` | Sandra | Placeholder: schema and loader only; matching returns nothing. |
| Policy Retrieval Tool | `components/policy_retrieval.py` | TBC | `SnapshotPolicyRetriever`: keyword (BM25) search over the ACTIVE snapshot's 849 chunks (interim, 2026-10-16). ChromaDB + EmbeddingGemma not connected yet; `DemoPolicyRetriever` kept for tests. Each retriever declares `mode` (`snapshot` or `demo`), stamped on every `ChatResponse` and on `/health`; the UI warns about fictional evidence only for `demo`. |
| Price Query Tool | `components/price_query.py` | Tasha | Interface and contract only. SQLite not connected. |
| Synthesiser Agent (LLM) | `components/synthesiser.py` | Nisha | Price summary uses a real CPU model. Policy answers are an extractive placeholder. Suggestions not built. |
| Verifier | `components/verifier.py` | Nisha | Numeric checks, citation checks, superseded sources, price provenance and topic-card IDs. |
| Abstention Output | `components/abstention.py` | Breann | Fixed messages per reason. |
| Harness | `graph.py`, `state.py` | Breann | One graph; one retry, then abstain. |
| Evaluation | `evaluation/` | TBC | Placeholder: runner, metrics and baselines not built. |
| Tracing | `trace` field on every response | Breann | Node-level trace only; LangSmith not connected. |

## Flow

1. `query_router` classifies and extracts town, flat type, age, income and
   citizenship. Missing required fields go to `synthesiser` as a clarifying
   question. Out-of-scope questions go to `abstention`.
2. Policy, discovery and mixed routes call `policy_retrieval`. Price and mixed
   routes call `price_query`. Mixed questions run retrieval first, then price.
3. `topic_cards` records which cards the Synthesiser may suggest.
4. If no tool produced usable evidence, the graph abstains before any model call.
5. `synthesiser` drafts the answer. `verifier` checks it. One failure sends the
   errors back for a single retry, and a second failure abstains. A model engine
   error abstains immediately.
6. `output` builds the user-facing message from verified parts only. Price
   headers come from the SQL result, not from the model.

## Assumptions to review

- When a price question gives no date range, the price tool uses the last 12
  months (`DEFAULT_LOOKBACK_MONTHS` in `price_query.py`).
- A mixed question whose price data is unavailable still answers the policy
  part and states that the price benchmark is unavailable.
- The required-field gate is hard-coded in `query_router.py`. It should be
  driven by the topic cards' required fields once they exist.

## Boundaries to preserve

- The model never calculates or invents a statistic. Every figure comes from an
  executed query and is checked against it to the cent.
- Citation checks are structural. Whether a claim faithfully reflects its
  source still needs manual review.
- The API is stateless. There is no conversation memory yet.
- The held-out set must not be used while tuning.
