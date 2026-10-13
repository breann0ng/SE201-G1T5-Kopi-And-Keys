# Architecture starting point

## Implemented now

- FastAPI validates `/chat` input and returns a structured result.
- One Advisor contract handles discovery, evidence gaps and answer drafting.
- LangGraph returns tool results to the Advisor through shared per-request state.
- Policy searches accumulate evidence and are capped at three calls.
- The Advisor may clarify, answer, retrieve, query prices or abstain.
- Deterministic verification sends errors back for one repair, then abstains.
- API responses expose source records and simple stage traces for development.

The demo workflow uses a scripted Advisor and fictional policy evidence. The
price adapter deliberately reports that no transaction database is connected.
No model downloads, API keys, external tracing or official policy ingestion are
required to run the starting point.

## Next integrations, in order

1. Implement an Ollama/Qwen Advisor using `Advisor.decide(state)`. Give it the
   complete state and require an `AdvisorDecision` structured output. Handle
   model timeouts and invalid structured outputs explicitly; never let them
   bypass graph budgets or output verification.
2. Implement `PolicyRetriever.search(query, limit)` using ChromaDB and
   EmbeddingGemma. Preserve provenance and version metadata. Add date and
   applicability handling before calling any source current or authoritative.
3. Implement `PriceQueryTool.query(filters)` over an imported official resale
   dataset in SQLite. Use fixed parameterised queries, stable query IDs and
   defined statistics; never execute model-supplied SQL directly.
4. Add reviewed topic cards as an Advisor input/tool. Keep policy-dependent
   thresholds and supporting source IDs in versioned data.
5. Add conversation storage and profile extraction, then connect a frontend.
6. Add the reviewed evaluation dataset and optional LangSmith tracing. Keep
   development/test scenario families separate.

## Boundaries to preserve

- The Advisor requests tools; the graph validates the action and owns execution.
- Missing buyer information leads to clarification; missing evidence leads to
  another search or abstention.
- Evidence is accumulated across searches instead of replacing previous results.
- The price result is rendered from tool output. The model does not calculate
  the displayed benchmark.
- Citation existence and metadata checks are structural checks, not proof that
  a free-text claim follows from its source. Semantic faithfulness needs review.
- No cross-request memory exists yet. Clarification returns a normal response;
  resuming a conversation requires an explicit storage design later.
- Demo keyword matching does not represent the future routing or LLM behaviour.

## Team ownership aligned with the proposal

| Area | Starting files | Owner |
| --- | --- | --- |
| Architecture and harness | `workflow.py`, `state.py`, `main.py`, `advisor.py` | Sandra |
| RAG and policy indexing | `tools/policy.py`, policy evidence schema | Tasha |
| SQL and guardrails | `tools/price.py`, `verifier.py` | Nisha |
| Evaluation and dataset curation | `tests/`, future reviewed evaluation data | Breann |

Ownership is guidance for the existing proposal responsibilities; interfaces
should be agreed together before implementing the real adapters.
