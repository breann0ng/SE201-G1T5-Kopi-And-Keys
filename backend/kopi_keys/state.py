from typing import TypedDict

from .schemas import AdvisorDecision, ChatRequest, ChatResponse, PolicyPassage, PriceResult


class AdvisorState(TypedDict):
    request: ChatRequest
    decision: AdvisorDecision | None
    passages: list[PolicyPassage]
    price_result: PriceResult | None
    retrieval_queries: list[str]
    price_calls: int
    advisor_steps: int
    repair_count: int
    verification_errors: list[str]
    trace: list[str]
    response: ChatResponse | None


def initial_state(request: ChatRequest) -> AdvisorState:
    return {
        "request": request,
        "decision": None,
        "passages": [],
        "price_result": None,
        "retrieval_queries": [],
        "price_calls": 0,
        "advisor_steps": 0,
        "repair_count": 0,
        "verification_errors": [],
        "trace": [],
        "response": None,
    }
