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

from . import baselines, metrics
from ..components.price_query import SqlitePriceTool, ToolUnavailableError, latest_month
from .dataset import AS_OF, ROOT, EvalError, active_snapshot, load_questions

REPORTS = ROOT / ".local" / "reports"


def chat_responses(questions: list[dict], api: str | None) -> dict[str, dict]:
    """POST each question (with its profile) to /chat, over HTTP or in-process."""
    from ..schemas import BuyerProfile

    if api:
        import httpx
        client = httpx.Client(base_url=api, timeout=180)
    else:
        from fastapi.testclient import TestClient

        from ..main import app
        client = TestClient(app)
    fields = BuyerProfile.model_fields
    out = {}
    with client:
        for q in questions:
            profile = {k: v for k, v in q["profile"].items() if k in fields}
            r = client.post("/chat", json={"message": q["question"], "profile": profile})
            out[q["id"]] = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
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
