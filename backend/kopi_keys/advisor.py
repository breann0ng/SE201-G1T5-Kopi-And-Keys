"""Replace DemoAdvisor with a Qwen/Ollama adapter behind the same contract."""

from typing import Protocol

from .schemas import AdvisorDecision, Claim
from .state import AdvisorState


class Advisor(Protocol):
    def decide(self, state: AdvisorState) -> AdvisorDecision: ...


class DemoAdvisor:
    """Scripted development fixture, not an LLM or an eligibility engine."""

    def decide(self, state: AdvisorState) -> AdvisorDecision:
        request = state["request"]
        message = request.message.lower()
        if "demo" in message:
            known = {passage.id for passage in state["passages"]}
            if "demo-programme" not in known:
                return AdvisorDecision(action="retrieve", query="demo programme")
            if "demo-condition" not in known:
                return AdvisorDecision(action="retrieve", query="demo related condition")
            return AdvisorDecision(
                action="answer",
                claims=[Claim(text=p.text, citation_ids=[p.id]) for p in state["passages"]],
            )
        if any(word in message for word in ("price", "selling", "sold", "cost")):
            if request.price_filters is None:
                return AdvisorDecision(
                    action="clarify",
                    message="Which town, flat type and transaction month range should I use?",
                )
            if state["price_result"] is None:
                return AdvisorDecision(action="price")
            return AdvisorDecision(action="answer")
        if not state["retrieval_queries"]:
            return AdvisorDecision(action="retrieve", query=request.message)
        return AdvisorDecision(
            action="abstain",
            message="Official HDB policy evidence is not connected yet. This is a demo backend.",
        )
