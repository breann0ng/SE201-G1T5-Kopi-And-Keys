"""Run one price question through the full graph with a supplied SQL result.

Useful before the SQLite adapter exists: the JSON file's `sql_result` stands in
for the Price Query Tool, and everything else (router, synthesiser, verifier)
runs for real, including the local CPU Ollama model.
"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .components.synthesiser import Synthesiser
from .graph import build_graph, run_graph
from .llm import ModelEngineError, OllamaEngine, OllamaSettings
from .schemas import ChatRequest, DataOrigin, PriceFilters, PriceResult


class PriceCase(BaseModel):
    """Input file format: a user question and the SQL result to answer it from."""

    model_config = ConfigDict(extra="forbid")
    user_query: str
    sql_result: PriceResult
    data_origin: DataOrigin = "synthetic_fixture"


class FixedPriceTool:
    def __init__(self, result: PriceResult):
        self.result = result

    def query(self, filters: PriceFilters) -> PriceResult:
        return self.result


def run_case(case: PriceCase, engine=None):
    """Ask a plain price question for the case's filters.

    `user_query` describes the case for humans; it is not sent as the message,
    because extra wording could change the router's classification.
    """
    filters = case.sql_result.filters
    graph = build_graph(
        price_tool=FixedPriceTool(case.sql_result),
        synthesiser=Synthesiser(engine or OllamaEngine()),
        cards=[],
    )
    message = f"What is the resale price for a {filters.flat_type} flat in {filters.town}?"
    request = ChatRequest(message=message, price_filters=filters)
    return run_graph(graph, request, data_origin=case.data_origin)


def report(state, case: PriceCase) -> dict:
    return {
        "status": state.response.status,
        "route": state.route,
        "data_origin": state.data_origin,
        "final_response": state.response.message,
        "verification_passed": state.verification_passed,
        "verification_errors": state.verification_errors,
        "model_calls": state.model_calls,
        "model_usage": state.model_usage,
        "query_id": case.sql_result.query_id,
        "trace": state.response.trace,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesise and verify a supplied SQL price result using local CPU Ollama.")
    parser.add_argument("--input", type=Path, help="JSON containing user_query, sql_result and data_origin.")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination.")
    parser.add_argument("--check-engine", action="store_true", help="Inspect local model installation and loaded CPU/GPU state.")
    args = parser.parse_args()
    try:
        engine = OllamaEngine(OllamaSettings.from_env())
        if args.check_engine:
            result = engine.inspect()
        else:
            if args.input is None:
                parser.error("--input is required unless --check-engine is used")
            case = PriceCase.model_validate_json(args.input.read_text(encoding="utf-8"))
            result = report(run_case(case, engine), case)
        rendered = json.dumps(result, indent=2, ensure_ascii=False, default=str)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if args.check_engine or result["status"] == "answered" else 1
    except (ModelEngineError, ValidationError, ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
