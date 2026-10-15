"""Run Person 3's handoff independently of the database, gateway and frontend."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from .contracts import SynthesisState
from .engine import ModelEngineError, OllamaEngine, OllamaSettings
from .pipeline import build_price_summary_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize and verify a Stage 2 SQL result using local CPU Ollama.")
    parser.add_argument("--input", type=Path, help="JSON containing user_query and sql_result.")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination.")
    parser.add_argument("--check-engine", action="store_true", help="Inspect local model installation and loaded CPU/GPU state.")
    args = parser.parse_args()
    try:
        engine = OllamaEngine(OllamaSettings.from_env())
        if args.check_engine:
            report = engine.inspect()
        else:
            if args.input is None:
                parser.error("--input is required unless --check-engine is used")
            source = json.loads(args.input.read_text(encoding="utf-8"))
            # Runtime fields cannot be supplied by the caller to bypass checks.
            allowed = {"user_query", "sql_result", "data_origin"}
            if not isinstance(source, dict) or set(source) - allowed:
                raise ValueError("Input may contain only user_query, sql_result and data_origin.")
            state = SynthesisState.model_validate(source)
            output = build_price_summary_graph(engine).invoke(state.model_dump())
            report = {name: output.get(name) for name in (
                "status", "data_origin", "final_response", "verification_passed",
                "verification_errors", "model_calls", "model_usage",
            )}
            report["query_id"] = state.sql_result.query_id
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if args.check_engine or report["status"] in {"answered", "no_data"} else 1
    except (ModelEngineError, ValidationError, ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
