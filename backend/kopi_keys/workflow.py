"""Bounded Advisor -> tools -> Advisor -> verifier workflow."""

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from .advisor import Advisor
from .schemas import AdvisorDecision, ChatRequest, ChatResponse
from .state import AdvisorState, initial_state
from .tools.policy import PolicyRetriever
from .tools.price import PriceQueryTool, ToolUnavailableError
from .verifier import verify


@dataclass(frozen=True)
class WorkflowLimits:
    retrieval_rounds: int = 3
    price_calls: int = 1
    verification_repairs: int = 1
    advisor_steps: int = 8

    def __post_init__(self):
        if min(self.retrieval_rounds, self.price_calls, self.advisor_steps) < 1:
            raise ValueError("Tool and Advisor limits must be positive.")
        if self.verification_repairs < 0:
            raise ValueError("Verification repairs cannot be negative.")


def build_workflow(
    advisor: Advisor,
    retriever: PolicyRetriever,
    price_tool: PriceQueryTool,
    limits: WorkflowLimits = WorkflowLimits(),
):
    def abstain_decision(message: str):
        return AdvisorDecision(action="abstain", message=message)

    def advisor_node(state: AdvisorState):
        if state["advisor_steps"] >= limits.advisor_steps:
            decision = abstain_decision("The Advisor step limit was reached.")
        else:
            # Validate even adapters that return plain dicts instead of models.
            decision = AdvisorDecision.model_validate(advisor.decide(state))
        if decision.action == "retrieve":
            prior = {query.casefold() for query in state["retrieval_queries"]}
            if len(prior) >= limits.retrieval_rounds:
                decision = abstain_decision("The retrieval limit was reached without sufficient evidence.")
            elif decision.query.casefold() in prior:
                decision = abstain_decision("The Advisor repeated a retrieval query without progress.")
        if decision.action == "price":
            if state["request"].price_filters is None:
                decision = AdvisorDecision(
                    action="clarify",
                    message="Which town, flat type and transaction month range should I use?",
                )
            elif state["price_calls"] >= limits.price_calls:
                decision = abstain_decision("The price query limit was reached.")
        return {
            "decision": decision,
            "advisor_steps": state["advisor_steps"] + 1,
            "trace": [*state["trace"], f"advisor:{decision.action}"],
        }

    def retrieval_node(state: AdvisorState):
        query = state["decision"].query
        passages = retriever.search(query, limit=5)
        # Preserve evidence across searches, deduplicating by stable source ID.
        accumulated = {p.id: p for p in state["passages"]}
        accumulated.update({p.id: p for p in passages})
        return {
            "passages": list(accumulated.values()),
            "retrieval_queries": [*state["retrieval_queries"], query],
            "trace": [*state["trace"], f"retrieval:{len(passages)} passages"],
        }

    def price_node(state: AdvisorState):
        try:
            result = price_tool.query(state["request"].price_filters)
        except ToolUnavailableError as error:
            return {
                "decision": abstain_decision(str(error)),
                "price_calls": state["price_calls"] + 1,
                "trace": [*state["trace"], "price:unavailable"],
            }
        return {
            "price_result": result,
            "price_calls": state["price_calls"] + 1,
            "trace": [*state["trace"], "price:result"],
        }

    def verifier_node(state: AdvisorState):
        errors = verify(state)
        update = {
            "verification_errors": errors,
            "trace": [*state["trace"], "verifier:failed" if errors else "verifier:passed"],
        }
        if errors:
            if state["repair_count"] >= limits.verification_repairs:
                update["decision"] = abstain_decision("The answer failed verification after the allowed repairs.")
            else:
                update["repair_count"] = state["repair_count"] + 1
        return update

    def finalize_node(state: AdvisorState):
        decision = state["decision"]
        status = {"answer": "answered", "clarify": "clarifying", "abstain": "abstained"}[decision.action]
        citations = []
        price = None
        if decision.action == "answer":
            cited_ids = {source_id for claim in decision.claims for source_id in claim.citation_ids}
            citations = [p for p in state["passages"] if p.id in cited_ids]
            message = "\n\n".join(
                f"{claim.text} [{', '.join(claim.citation_ids)}]" for claim in decision.claims
            )
            price = state["price_result"]
            if price is not None:
                # Numeric output is rendered from tool data, never recomputed by the Advisor.
                benchmark = (
                    f"{price.count} transactions; median SGD {price.median:,.2f}; "
                    f"range SGD {price.minimum:,.2f}–{price.maximum:,.2f} [{price.query_id}]."
                )
                message = "\n\n".join(part for part in (message, benchmark) if part)
        else:
            message = decision.message
        return {"response": ChatResponse(
            status=status,
            message=message,
            citations=citations,
            price_result=price,
            retrieval_rounds=len(state["retrieval_queries"]),
            trace=state["trace"],
        )}

    def after_verification(state: AdvisorState):
        if state["decision"].action == "abstain" or not state["verification_errors"]:
            return "finalize"
        return "advisor"

    graph = StateGraph(AdvisorState)
    graph.add_node("advisor", advisor_node)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("price", price_node)
    graph.add_node("verify", verifier_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "advisor")
    graph.add_conditional_edges("advisor", lambda state: state["decision"].action, {
        "retrieve": "retrieve", "price": "price", "answer": "verify",
        "clarify": "finalize", "abstain": "finalize",
    })
    graph.add_edge("retrieve", "advisor")
    graph.add_conditional_edges("price", lambda state: (
        "finalize" if state["decision"].action == "abstain" else "advisor"
    ), {"finalize": "finalize", "advisor": "advisor"})
    graph.add_conditional_edges("verify", after_verification, {"finalize": "finalize", "advisor": "advisor"})
    graph.add_edge("finalize", END)
    return graph.compile()


def run_request(graph, request: ChatRequest) -> ChatResponse:
    result = graph.invoke(initial_state(request), config={"recursion_limit": 100})
    return result["response"]
