"""Composable Stage 3/4 nodes plus a small handoff graph for midpoint testing."""

from langgraph.graph import END, START, StateGraph

from .contracts import SQLPriceResult, SynthesisState
from .engine import ModelEngineError, OllamaEngine, TextEngine
from .numeric_verifier import verify_generated_numbers
from .synthesizer import PriceSynthesizer


def make_synthesizer_node(engine: TextEngine):
    synthesizer = PriceSynthesizer(engine)

    def synthesizer_node(state: SynthesisState) -> dict:
        sql = SQLPriceResult.model_validate(state.sql_result)
        if sql.volume == 0:
            return {"draft_response": "", "generation_error": None}
        try:
            generation = synthesizer.generate(state.user_query, sql, state.verification_errors)
        except ModelEngineError as error:
            return {
                "draft_response": "", "generation_error": str(error),
                "model_calls": state.model_calls + 1,
            }
        return {
            "draft_response": generation.text,
            "generation_error": None,
            "model_calls": state.model_calls + 1,
            "model_usage": [*state.model_usage, {"model": generation.model, **generation.usage}],
        }

    return synthesizer_node


def verifier_node(state: SynthesisState) -> dict:
    sql = SQLPriceResult.model_validate(state.sql_result)
    if sql.volume == 0:
        return {
            "status": "no_data", "verification_passed": False, "verification_errors": [],
            "final_response": "No matching resale transactions were found for the requested filters.",
        }
    if state.generation_error:
        return {
            "status": "abstained", "verification_passed": False,
            "verification_errors": [state.generation_error],
            "final_response": "I could not generate a verified price summary because the model engine was unavailable.",
        }
    result = verify_generated_numbers(state.draft_response, sql)
    if not result.passed:
        return {
            "status": "needs_repair", "verification_passed": False,
            "verification_errors": list(result.errors), "final_response": "",
        }
    filters = sql.filters
    header = (
        f"{filters.flat_type} flats in {filters.town}, "
        f"{filters.start_month} to {filters.end_month} [query: {sql.query_id}]"
    )
    if state.data_origin == "synthetic_fixture":
        header = "SYNTHETIC TEST DATA - not actual market statistics.\n" + header
    return {
        "status": "answered", "verification_passed": True, "verification_errors": [],
        "final_response": header + "\n" + state.draft_response.strip(),
    }


def build_price_summary_graph(engine: TextEngine | None = None, max_retries: int = 1):
    """Person 3 subgraph; Stage 1 and the SQL node remain team integration points."""
    if not 0 <= max_retries <= 3:
        raise ValueError("max_retries must be between zero and three.")
    graph = StateGraph(SynthesisState)
    graph.add_node("stage3_synthesizer", make_synthesizer_node(engine or OllamaEngine()))
    graph.add_node("stage4_verifier", verifier_node)

    def abstain_node(state: SynthesisState):
        return {
            "status": "abstained", "verification_passed": False,
            "final_response": "I could not verify the generated statistics against the SQL result.",
        }

    def next_step(state: SynthesisState):
        if state.status != "needs_repair":
            return "end"
        return "repair" if state.model_calls <= max_retries else "abstain"

    graph.add_node("abstain", abstain_node)
    graph.add_edge(START, "stage3_synthesizer")
    graph.add_edge("stage3_synthesizer", "stage4_verifier")
    graph.add_conditional_edges("stage4_verifier", next_step, {
        "end": END, "repair": "stage3_synthesizer", "abstain": "abstain",
    })
    graph.add_edge("abstain", END)
    return graph.compile()
