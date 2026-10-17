"""The LangGraph harness. One node per box on the architecture diagram.

    query_router ─┬─ clarify ──────────────────────────────► synthesiser
                  ├─ abstain ──────────────────────────────► abstention
                  ├─ policy / discovery ─► policy_retrieval ─┐
                  ├─ mixed ──► policy_retrieval ─► price_query ┤
                  └─ price ─────────────────────► price_query ┤
                                                              ▼
                                  topic_cards ─► (evidence?) ─► synthesiser
                                                    └─ none ─► abstention
    synthesiser ─► verifier ─┬─ pass ─────────────► output
                             ├─ fail, first time ─► synthesiser (with errors)
                             └─ fail again / engine error ─► abstention
"""

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .components.abstention import abstention_message
from .components.policy_retrieval import TOP_K, PolicyRetriever, KeywordPolicyRetriever
from .components.price_query import (
    PriceQueryTool, ToolUnavailableError, UnconfiguredPriceTool, filters_from_state,
)
from .components.query_router import EXTRACTED_FIELDS, route_query
from .components.synthesiser import Synthesiser, SynthesiserAgent
from .components.topic_cards import (
    TopicCard, discovery_question_field, income_ceiling_checks, load_cards, match_cards,
    personal_eligibility_fields, suggestion_cards,
)
from .topic_cards import OVERVIEW_TOPICS, overview_topic
from .components.verifier import verify
from .llm import OllamaEngine
from .schemas import ChatRequest, ChatResponse, DataOrigin, IncomeNote, OverviewItem, Suggestion
from .state import GraphState, initial_state


MAX_REPAIRS = 1  # Proposal: one retry, then abstain.
POLICY_ROUTES = {"policy", "discovery", "mixed"}
PRICE_ROUTES = {"price", "mixed"}


def evidence_problem(state: GraphState) -> tuple[str, str | None] | None:
    """Return (reason, detail) if the tools produced nothing usable to answer with."""
    has_policy = any(not passage.superseded for passage in state.passages)
    has_price = state.price_result is not None and state.price_result.volume > 0
    if has_policy or has_price:
        return None
    if state.route in PRICE_ROUTES:
        if state.price_error:
            return "no_evidence", state.price_error
        if state.price_result is not None:
            return "no_transactions", None
    return "no_evidence", None


def build_graph(
    retriever: PolicyRetriever | None = None,
    price_tool: PriceQueryTool | None = None,
    synthesiser: SynthesiserAgent | None = None,
    cards: list[TopicCard] | None = None,
    max_repairs: int = MAX_REPAIRS,
    data_mode: str | None = None,
):
    retriever = retriever or KeywordPolicyRetriever()
    # Stamped on every response: the retriever declares its evidence ("snapshot" or "demo");
    # data_mode overrides it (tests with stub retrievers). Undeclared stubs count as demo.
    mode = data_mode or getattr(retriever, "mode", "demo")
    price_tool = price_tool or UnconfiguredPriceTool()
    synthesiser = synthesiser or Synthesiser(OllamaEngine())
    cards = load_cards() if cards is None else cards

    # --- Nodes --------------------------------------------------------------

    def query_router(state: GraphState):
        known = {field: getattr(state, field) for field in (*EXTRACTED_FIELDS, "start_month", "end_month")}
        routed = route_query(state.message, known, context_question=state.followup_question)
        return {**routed.model_dump(), "trace": [f"query_router:{routed.route}"]}

    def policy_retrieval(state: GraphState):
        query = state.followup_question or state.message
        if state.household_type == "single":
            query += " singles"
        elif state.household_type in {"couple_family", "fiance", "extended_family"}:
            query += " families"
        passages = retriever.search(query, limit=TOP_K)
        accumulated = {p.id: p for p in state.passages}
        accumulated.update({p.id: p for p in passages})
        return {
            "passages": list(accumulated.values()),
            "retrieval_queries": [*state.retrieval_queries, query],
            "trace": [f"policy_retrieval:{len(passages)} passages"],
        }

    def price_query(state: GraphState):
        try:
            result = price_tool.query(filters_from_state(state))
        except (ToolUnavailableError, ValidationError) as error:
            return {"price_error": str(error), "trace": ["price_query:unavailable"]}
        return {"price_result": result, "trace": [f"price_query:{result.volume} transactions"]}

    def topic_cards(state: GraphState):
        missing = personal_eligibility_fields(state, cards)
        if missing:
            return {"route": "clarify", "missing_fields": missing,
                    "trace": ["topic_cards:needs_profile"]}
        card_ids = match_cards(state, cards)
        update = {"candidate_card_ids": card_ids, "trace": [f"topic_cards:{len(card_ids)} matched"]}
        # Discovery questions are answered straight away; when a missing profile detail would
        # unlock more topic cards, the answer carries a hint to fill in "Your situation".
        if discovery_question_field(state, cards):
            update["profile_hint"] = True
        # Broad questions ("what grants are there?") also get an overview table: each scheme's
        # verbatim official sentence from its card, cited to its chunk. Needs a retriever that
        # can fetch named chunks (the real snapshot retrievers can; test stubs can't).
        topic = overview_topic(state.followup_question or state.message)
        if topic and state.route in POLICY_ROUTES and hasattr(retriever, "get"):
            by_id = {card.card_id: card for card in cards}
            passages = {p.id: p for p in state.passages}
            items = []
            for card_id in OVERVIEW_TOPICS[topic]:
                card = by_id.get(card_id)
                if card is None or card.overview is None:
                    continue
                found = retriever.get([card.overview.chunk_id])
                if found:
                    passages.setdefault(found[0].id, found[0])
                    items.append(OverviewItem(card_id=card_id, title=card.topic_name,
                                              quote=card.overview.quote, citation_id=found[0].id))
            if items:
                update.update(overview=items, passages=list(passages.values()))
                update["trace"] = [f"topic_cards:{len(card_ids)} matched, overview:{topic} ({len(items)})"]
        # Matched cards the answer didn't cover become cited suggestions (not with an overview,
        # which already lists the schemes).
        if card_ids and "overview" not in update and state.route in POLICY_ROUTES and hasattr(retriever, "get"):
            passages = {p.id: p for p in update.get("passages", state.passages)}
            seeds = []
            for card in suggestion_cards(card_ids, cards, state.followup_question or state.message):
                found = retriever.get([card.overview.chunk_id])
                if found:
                    passages.setdefault(found[0].id, found[0])
                    seeds.append(Suggestion(card_id=card.card_id, text=card.topic_name, citation_ids=[found[0].id]))
            if seeds:
                update.update(suggestion_seeds=seeds, passages=list(passages.values()))
        notes = income_ceiling_checks(state, card_ids, topic)
        if notes:
            update["income_notes"] = [IncomeNote(
                scheme=c.scheme, label=c.label, ceiling=f"{c.ceiling:,.0f}", within_ceiling=c.within_ceiling,
                message=c.message, source_url=c.source_url, conditions=list(c.conditions)) for c in notes]
        return update

    def synthesiser_node(state: GraphState):
        result = synthesiser.synthesise(state)
        usage = [{"model": g.model, **g.usage} for g in result.generations]
        return {
            "draft": result.draft,
            "generation_error": result.error,
            "model_calls": state.model_calls + result.model_calls,
            "model_usage": [*state.model_usage, *usage],
            "trace": ["synthesiser:error" if result.error else f"synthesiser:{result.draft.kind}"],
        }

    def verifier_node(state: GraphState):
        if state.generation_error:
            return {
                "verification_errors": [state.generation_error],
                "verification_passed": False,
                "abstain_reason": "engine_unavailable",
                "trace": ["verifier:engine_error"],
            }
        errors = verify(state)
        update = {
            "verification_errors": errors,
            "verification_passed": not errors,
            "trace": ["verifier:failed" if errors else "verifier:passed"],
        }
        if errors:
            # Added 2026-10-17: keep the quotes that pass every check on their own, if the
            # trimmed answer then passes in full, instead of a ~60 s repair or declining everything.
            # E.g. a genuine EHG quote was lost because a second quote stitched worked-example table
            # cells into a sentence that is not in the source. A repair still runs when no quote passes.
            if state.draft is not None and state.draft.claims:
                kept = [c for c in state.draft.claims
                        if not verify(state.model_copy(update={"draft": state.draft.model_copy(update={"claims": [c]})}))]
                if kept and len(kept) < len(state.draft.claims):
                    trimmed = state.draft.model_copy(update={"claims": kept})
                    if not verify(state.model_copy(update={"draft": trimmed})):
                        return {
                            "draft": trimmed,
                            "verification_errors": [],
                            "verification_passed": True,
                            "trace": [f"verifier:passed after dropping {len(state.draft.claims) - len(kept)} unverified quote(s)"],
                        }
            if state.repair_count >= max_repairs:
                update["abstain_reason"] = "verification_failed"
            else:
                update["repair_count"] = state.repair_count + 1
        return update

    def abstention(state: GraphState):
        if state.abstain_reason:
            reason, detail = state.abstain_reason, None
        elif state.route == "abstain":
            reason, detail = "unsupported", None
        else:
            reason, detail = evidence_problem(state) or ("no_evidence", None)
        trace = [*state.trace, f"abstention:{reason}"]
        return {
            "abstain_reason": reason,
            "trace": [f"abstention:{reason}"],
            "response": ChatResponse(
                status="abstained",
                mode=mode,
                route=state.route,
                message=abstention_message(reason, detail),
                retrieval_rounds=len(state.retrieval_queries),
                trace=trace,
            ),
        }

    def output(state: GraphState):
        draft = state.draft
        trace = [*state.trace, "output"]
        if draft.kind == "clarify":
            return {"trace": ["output"], "response": ChatResponse(
                status="clarifying", mode=mode, route=state.route, message=draft.message, trace=trace,
                asking_for={"user_age": "age", "income": "household_income"}.get(
                    state.missing_fields[0], state.missing_fields[0])
                    if state.missing_fields and state.missing_fields[0] in {
                        "user_age", "income", "citizenship", "first_timer", "household_type"} else None,
            )}
        parts = [f"{claim.text} [{', '.join(claim.citation_ids)}]" for claim in draft.claims]
        price = state.price_result
        if price is not None and price.volume > 0:
            f = price.filters
            header = f"{f.flat_type} flats in {f.town}, {f.start_month} to {f.end_month} [query: {price.query_id}]"
            if state.data_origin == "synthetic_fixture":
                header = "SYNTHETIC TEST DATA - not actual market statistics.\n" + header
            parts.append(header + "\n" + draft.price_text.strip())
        elif state.route in PRICE_ROUTES:
            parts.append(abstention_message("no_transactions") if price is not None
                         else f"Price benchmark unavailable: {state.price_error}")
        if draft.suggestions:
            parts.append("You may also want to look into:\n" + "\n".join(
                f"- {s.text} [{', '.join(s.citation_ids)}]" for s in draft.suggestions
            ))
        cited = {cid for claim in draft.claims for cid in claim.citation_ids}
        cited |= {cid for s in draft.suggestions for cid in s.citation_ids}
        cited |= {item.citation_id for item in state.overview}
        return {"trace": ["output"], "response": ChatResponse(
            status="answered",
            mode=mode,
            route=state.route,
            message="\n\n".join(parts),
            citations=[p for p in state.passages if p.id in cited],
            price_result=price,
            suggestions=draft.suggestions,
            overview=state.overview,
            profile_hint=state.profile_hint,
            income_notes=state.income_notes,
            related=[p for p in state.passages if p.id not in cited and not p.superseded],
            retrieval_rounds=len(state.retrieval_queries),
            trace=trace,
        )}

    # --- Edges --------------------------------------------------------------

    def after_router(state: GraphState) -> str:
        if state.route == "clarify":
            return "synthesiser"
        if state.route == "abstain":
            return "abstention"
        return "policy_retrieval" if state.route in POLICY_ROUTES else "price_query"

    def after_retrieval(state: GraphState) -> str:
        return "price_query" if state.route in PRICE_ROUTES else "topic_cards"

    def after_topic_cards(state: GraphState) -> str:
        if state.route == "clarify":
            return "synthesiser"
        return "abstention" if evidence_problem(state) else "synthesiser"

    def after_verifier(state: GraphState) -> str:
        if state.abstain_reason:
            return "abstention"
        return "synthesiser" if state.verification_errors else "output"

    graph = StateGraph(GraphState)
    graph.add_node("query_router", query_router)
    graph.add_node("policy_retrieval", policy_retrieval)
    graph.add_node("price_query", price_query)
    graph.add_node("topic_cards", topic_cards)
    graph.add_node("synthesiser", synthesiser_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("abstention", abstention)
    graph.add_node("output", output)

    graph.add_edge(START, "query_router")
    graph.add_conditional_edges("query_router", after_router, [
        "synthesiser", "abstention", "policy_retrieval", "price_query",
    ])
    graph.add_conditional_edges("policy_retrieval", after_retrieval, ["price_query", "topic_cards"])
    graph.add_edge("price_query", "topic_cards")
    graph.add_conditional_edges("topic_cards", after_topic_cards, ["synthesiser", "abstention"])
    graph.add_edge("synthesiser", "verifier")
    graph.add_conditional_edges("verifier", after_verifier, ["synthesiser", "output", "abstention"])
    graph.add_edge("abstention", END)
    graph.add_edge("output", END)
    compiled = graph.compile()
    compiled.evidence_mode = mode  # read by /health in main.py
    return compiled


def run_graph(graph, request: ChatRequest, data_origin: DataOrigin = "database") -> GraphState:
    """Run one request and return the full final state (for tests and evaluation)."""
    result = graph.invoke(initial_state(request, data_origin), config={"recursion_limit": 50})
    return GraphState.model_validate(result)


def run_chat(graph, request: ChatRequest) -> ChatResponse:
    return run_graph(graph, request).response
