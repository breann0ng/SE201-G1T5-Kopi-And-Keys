"""Run a labelled question set and score it (proposal section 4, Appendix E).

Usage (repo root, project venv):
    python -m kopi_keys.evaluation.run_eval                      # dev set: routing, discovery, Recall@5 (bm25)
    python -m kopi_keys.evaluation.run_eval --retriever hybrid   # Recall@5 with the hybrid retriever
    python -m kopi_keys.evaluation.run_eval --local              # + end to end through the app in-process
    python -m kopi_keys.evaluation.run_eval --api http://127.0.0.1:8000   # + end to end over HTTP
    python -m kopi_keys.evaluation.run_eval --split heldout --final       # final results only

The held-out set is private: set KOPI_HELDOUT_DIR to the folder holding
heldout_questions.jsonl (outside the repository). Never run it while tuning.
Reports go to .local/reports/ (gitignored); end-to-end runs also write a
Ragas-format JSONL for LLM-judged metrics.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from datetime import date

from . import baselines, metrics
from ..components.price_query import SqlitePriceTool, ToolUnavailableError, latest_month
from .dataset import AS_OF, ROOT, EvalError, active_snapshot, load_questions

REPORTS = ROOT / ".local" / "reports"


def chat_responses(questions: list[dict], api: str | None) -> dict[str, dict]:
    """Use scripted turns consistently; pin the in-process router to the label date."""
    from .run_baselines import run_full

    if api:
        from ..components.query_router import extract_month_range

        year, month = map(int, AS_OF.split("-"))
        dependent = [q["id"] for q in questions if any(
            extract_month_range(t["user"], today=date(year, month, 1)) !=
            extract_month_range(t["user"], today=date.today())
            for t in q.get("turns", []) if "user" in t)]
        if dependent:
            raise SystemExit("Remote API dates cannot be pinned to the evaluation labels (as of " + AS_OF +
                             "). Use --local for a reproducible comparison. Affected IDs: " + ", ".join(dependent))
        import httpx
        client = httpx.Client(base_url=api, timeout=180)
    else:
        from fastapi.testclient import TestClient

        from ..main import app
        client = TestClient(app)
    out = {}
    with client:
        for q in questions:
            out[q["id"]] = run_full(client, q, as_of=None if api else AS_OF)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev")
    ap.add_argument("--final", action="store_true", help="required for the held-out split")
    ap.add_argument("--retriever", default="bm25", help="bm25 (default), hybrid, or module:function")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true", help="end to end through the app in-process")
    mode.add_argument("--api", help="end to end against a running backend, e.g. http://127.0.0.1:8000")
    args = ap.parse_args()
    if args.split == "heldout" and not args.final:
        raise SystemExit("Held-out questions are for final reported results only; add --final to confirm.")

    try:
        questions = load_questions(args.split)
    except EvalError as error:
        raise SystemExit(str(error))
    search, retriever_name = baselines.retriever(args.retriever)
    price_tool = SqlitePriceTool()
    try:
        data_month = latest_month(price_tool)
    except ToolUnavailableError:
        data_month = None  # no database: price_figures reports n/a
    report = {
        "split": args.split, "questions": len(questions), "snapshot": active_snapshot(),
        "retriever": retriever_name,
        "router_as_of": AS_OF if not args.api else None,
        "remote_clock_uncontrolled": bool(args.api),
        "stage1": metrics.stage1_routing(questions),
        "discovery": metrics.discovery(questions),
        "retrieval": metrics.retrieval_recall_at_k(questions, search, k=5),
        "price_filters": metrics.price_filters(questions, AS_OF, data_month),
        "price_figures": metrics.price_figures(questions, price_tool, AS_OF),
    }
    if args.local or args.api:
        e2e = metrics.end_to_end(questions, chat_responses(questions, args.api))
        report["end_to_end"] = {k: v for k, v in e2e.items() if k != "ragas"}

    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{args.split}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if "end_to_end" in report:
        stem.with_name(stem.name + "_ragas.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in e2e["ragas"]), encoding="utf-8")

    d, r, s = report["discovery"], report["retrieval"], report["stage1"]
    print(f"split={args.split}  questions={len(questions)}  snapshot={report['snapshot']}")
    print(f"Stage 1     routing (router only) {s['routing_accuracy']}")
    print(f"Discovery   precision {d['precision']}  recall {d['recall']}  ask-next {d['ask_next_accuracy']}")
    print(f"Discovery   shown only: precision {d['precision_shown']}  recall {d['recall_shown']}")
    print(f"Retrieval   Recall@5 {r['recall_at_5']}  ({retriever_name})")
    print(f"Price       filters {report['price_filters']['accuracy']}  (router as of {AS_OF}, data to {data_month})")
    print(f"Price       figures {report['price_figures']['accuracy']}  (tool vs SQL expected_price)")
    if "end_to_end" in report:
        e = report["end_to_end"]
        print(f"End-to-end  routing {e['routing_accuracy']}  unsafe {e['unsafe_answering']}  "
              f"over-abstain {e['over_abstention']}  uncited {e['uncited_answers']}  "
              f"stale {e['staleness_errors']}  price {e['price_figures']}  errors {e['errors']}")
    print(f"Report: {stem.with_suffix('.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
