"""Run a JSONL dataset through the workflow and score the responses.

Usage:
    python eval/run_eval.py eval/dataset/smoke.jsonl
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from kopi_keys.advisor import DemoAdvisor
from kopi_keys.schemas import ChatRequest
from kopi_keys.tools.policy import DemoPolicyRetriever
from kopi_keys.tools.price import UnconfiguredPriceTool
from kopi_keys.workflow import build_workflow, run_request

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REQUIRED = {"id", "family", "message", "expected_status"}


def load_cases(path: Path) -> list[dict]:
    cases, seen = [], set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        missing = REQUIRED - case.keys()
        if missing:
            raise SystemExit(f"{path}:{line_no} missing {sorted(missing)}")
        if case["id"] in seen:
            raise SystemExit(f"{path}:{line_no} duplicate id {case['id']}")
        seen.add(case["id"])
        cases.append(case)
    return cases


def build_graph():
    # Swap in the real Advisor/retriever/price tool here once they exist.
    return build_workflow(DemoAdvisor(), DemoPolicyRetriever(), UnconfiguredPriceTool())


def score(case: dict, response) -> dict:
    cited = {p.id for p in response.citations}
    expected = set(case.get("expected_citations", []))
    forbidden = set(case.get("forbidden_citations", []))
    result = {
        "status_ok": response.status == case["expected_status"],
        "citation_recall": len(expected & cited) / len(expected) if expected else None,
        "forbidden_cited": sorted(forbidden & cited),
    }
    result["passed"] = (
        result["status_ok"]
        and result["citation_recall"] in (None, 1.0)
        and not result["forbidden_cited"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    if not cases:
        print(f"No cases in {args.dataset}.")
        return 0
    graph = build_graph()
    run_dir = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.dataset.stem}"
    run_dir.mkdir(parents=True)

    records = []
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as out:
        for case in cases:
            request = ChatRequest(
                message=case["message"],
                profile=case.get("profile", {}),
                price_filters=case.get("price_filters"),
            )
            response = run_request(graph, request)
            record = {"case": case, "response": response.model_dump(mode="json"), **score(case, response)}
            records.append(record)
            out.write(json.dumps(record) + "\n")

    recalls = [r["citation_recall"] for r in records if r["citation_recall"] is not None]
    failures = [r["case"]["id"] for r in records if not r["passed"]]
    summary = {
        "dataset": str(args.dataset),
        "cases": len(records),
        "passed": len(records) - len(failures),
        "status_accuracy": sum(r["status_ok"] for r in records) / len(records),
        "citation_recall": sum(recalls) / len(recalls) if recalls else None,
        "forbidden_citation_violations": sum(bool(r["forbidden_cited"]) for r in records),
        "mean_retrieval_rounds": sum(r["response"]["retrieval_rounds"] for r in records) / len(records),
        "failures": failures,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    for record in records:
        if not record["passed"]:
            print(f"FAIL {record['case']['id']}: expected {record['case']['expected_status']}, "
                  f"got {record['response']['status']} — {record['response']['message'][:120]}")
    print(f"Results: {run_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
