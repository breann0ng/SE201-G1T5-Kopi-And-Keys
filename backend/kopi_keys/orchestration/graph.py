"""LangGraph orchestration for the Stage 1 request gateway."""

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic import Field

from ..midpoint.contracts import SQLPriceResult, SynthesisState
from ..schemas import GraphState
from .gateway import missing_fields, parse_gateway
from .router import route_for_intent


class IntegratedGraphState(GraphState):
    """Stage 1 state extended with the Stage 2 -> Stage 3/4 handoff fields."""

    sql_result: SQLPriceResult | None = None
    midpoint_status: str | None = None
    final_response: str | None = None
    verification_passed: bool = False
    verification_errors: list[str] = Field(default_factory=list)


def build_stage1_graph(
    sql_provider: Callable[[GraphState], SQLPriceResult] | None = None,
    midpoint_graph: Any | None = None,
):
    """Build the Stage 1 gateway graph with explicit short-circuit edges."""

    def gateway_node(state: GraphState):
        parsed = parse_gateway(state.message)
        for field in ("user_age", "income", "citizenship", "town", "flat_type"):
            if getattr(parsed, field) is None:
                parsed = parsed.model_copy(update={field: getattr(state, field)})
        return parsed.model_dump()

    def gate_node(state: GraphState):
        missing = missing_fields(state)
        if missing:
            return {
                "missing_fields": missing,
                "status": "clarify",
                "route": "clarify",
                "response": f"Please provide: {', '.join(missing)}.",
            }
        return {"missing_fields": [], "status": "continue"}

    def route_node(state: GraphState):
        return {"route": route_for_intent(state.intent or "unanswerable")}

    def sql_node(state: IntegratedGraphState):
        if sql_provider is None:
            return {
                "midpoint_status": "abstained",
                "final_response": "No SQL price provider is configured.",
            }
        return {"sql_result": SQLPriceResult.model_validate(sql_provider(state))}

    def midpoint_node(state: IntegratedGraphState):
        if state.sql_result is None or midpoint_graph is None:
            return {
                "midpoint_status": "abstained",
                "final_response": "The price summary workflow is not configured.",
            }
        synthesis = SynthesisState(
            user_query=state.message,
            sql_result=state.sql_result,
            data_origin="stage2",
        )
        result = midpoint_graph.invoke(synthesis.model_dump())
        return {
            "midpoint_status": result["status"],
            "final_response": result["final_response"],
            "verification_passed": result["verification_passed"],
            "verification_errors": result["verification_errors"],
        }

    def after_gate(state: GraphState) -> str:
        return "finish" if state.status != "continue" else "route"

    def finish_node(state: GraphState):
        if state.route == "abstain" and state.response is None:
            return {
                "status": "abstain",
                "response": "I can help with HDB policy and resale price questions.",
            }
        return {}

    integrated = sql_provider is not None or midpoint_graph is not None
    state_schema = IntegratedGraphState if integrated else GraphState
    builder = StateGraph(state_schema)
    builder.add_node("gateway", gateway_node)
    builder.add_node("gate", gate_node)
    builder.add_node("route", route_node)
    builder.add_node("finish", finish_node)
    if integrated:
        builder.add_node("stage2_sql", sql_node)
        builder.add_node("stage3_stage4_midpoint", midpoint_node)
    builder.add_edge(START, "gateway")
    builder.add_edge("gateway", "gate")
    builder.add_conditional_edges("gate", after_gate, {"finish": "finish", "route": "route"})
    if integrated:
        builder.add_conditional_edges(
            "route",
            lambda state: "stage2_sql" if state.route in {"price", "mixed"} else "finish",
            {"stage2_sql": "stage2_sql", "finish": "finish"},
        )
        builder.add_edge("stage2_sql", "stage3_stage4_midpoint")
        builder.add_edge("stage3_stage4_midpoint", "finish")
    else:
        builder.add_edge("route", "finish")
    builder.add_edge("finish", END)
    return builder.compile()


def run_stage1(message: str) -> GraphState:
    result = build_stage1_graph().invoke({"message": message})
    return GraphState.model_validate(result)
