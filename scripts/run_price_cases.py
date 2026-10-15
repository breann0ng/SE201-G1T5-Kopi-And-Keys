"""Run the synthetic SQL price cases through the full graph, with optional live CPU inference."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from kopi_keys.cli import PriceCase, report, run_case
from kopi_keys.llm import OllamaEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = PROJECT_ROOT / "examples" / "price_cases"
CASES = (
    ("zero_transactions", "no_data", None),
    ("single_transaction", "answered", None),
    ("decimal_rounding", "answered", None),
    ("large_amounts", "answered", None),
    ("invalid_missing_median", "rejected", "Non-empty SQL results require"),
    ("invalid_price_range", "rejected", "Mean must lie within the SQL price range"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Check fixture schemas and expected rejections without calling Ollama.",
    )
    args = parser.parse_args()
    mode = "validation_only" if args.validate_only else "live_ollama"
    engine = None if args.validate_only else OllamaEngine()
    results = []
    for name, expected, expected_error in CASES:
        try:
            case = PriceCase.model_validate_json(
                (CASE_ROOT / f"{name}.json").read_text(encoding="utf-8"),
            )
        except ValidationError as error:
            passed = expected == "rejected" and expected_error in str(error)
            result = {
                "case": name, "expected": expected, "actual": "rejected",
                "passed": passed, "model_calls": 0, "validation_error": str(error),
            }
        else:
            if expected == "rejected":
                result = {"case": name, "expected": expected, "actual": "accepted", "passed": False}
            elif args.validate_only:
                result = {"case": name, "expected": "valid_input", "actual": "valid_input", "passed": True}
            else:
                print(f"Running {name} ...", flush=True)
                state = run_case(case, engine)
                output = report(state, case)
                actual = "no_data" if state.abstain_reason == "no_transactions" else output["status"]
                passed = actual == expected
                if expected == "answered":
                    passed = passed and output["verification_passed"] and not output["verification_errors"]
                if expected == "no_data":
                    passed = passed and output["model_calls"] == 0
                result = {
                    "case": name, "expected": expected, "actual": actual,
                    "passed": bool(passed), "model_calls": output["model_calls"],
                    "verification_errors": output["verification_errors"],
                    "final_response": output["final_response"], "model_usage": output["model_usage"],
                }
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark}: {name} ({result['actual']})", flush=True)

    report_path = PROJECT_ROOT / ".local" / "reports" / f"synthetic_cases_{mode}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"mode": mode, "results": results}, indent=2) + "\n", encoding="utf-8")
    passed_count = sum(result["passed"] for result in results)
    print(f"\n{passed_count}/{len(results)} checks passed. Mode: {mode}.")
    print(f"Report: {report_path}")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
