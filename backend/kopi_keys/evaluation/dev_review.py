"""Diagnose development answers, retaining verifier reasons for human review.

No held-out option. Reports contain fictional dev questions/quotes; keep them local.
Run with the same model/index/database as the app, e.g. --case-ids MIX-01 POL-02.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .dataset import AS_OF, DEV_FILE, ROOT, active_snapshot, load_questions
from .metrics import end_to_end, router_today


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def review_case(graph, question: dict) -> dict:
    from ..graph import run_graph
    from ..schemas import BuyerProfile, ChatRequest
    from .run_baselines import user_turns

    profile = {k: v for k, v in question["profile"].items() if k in BuyerProfile.model_fields}
    history, attempts = [], []
    with router_today(AS_OF):
        for text in user_turns(question):
            state = run_graph(graph, ChatRequest(message=text, profile=profile, history=history))
            response = state.response.model_dump(mode="json")
            attempts.append({"response": response, "verification_errors": state.verification_errors,
                             "synthesis_errors": state.synthesis_errors, "relevance_scores": state.relevance_scores,
                             "draft": state.draft.model_dump(mode="json") if state.draft else None,
                             "retrieved_ids": [p.id for p in state.passages], "model_usage": state.model_usage})
            if response["status"] != "clarifying":
                break
            history += [{"role": "user", "content": text}, {"role": "assistant", "content": response["message"]}]
    response["initial_route"] = attempts[0]["response"].get("route")
    return {"id": question["id"], "question": question["question"], "response": response,
            "attempts": attempts, "human_review": {"correct_scope": None, "complete_answer": None,
                                                   "source_qualification": None, "notes": ""}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/reports/dev-review.json")
    args = parser.parse_args(argv)
    # Do this BEFORE importing the app/engine. Never upload dev questions or drafts.
    os.environ.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", KOPI_WARM_UP="0")
    questions = load_questions("dev")
    if args.case_ids:
        unknown = set(args.case_ids) - {q["id"] for q in questions}
        if unknown:
            parser.error("Unknown development case IDs: " + ", ".join(sorted(unknown)))
        questions = [q for q in questions if q["id"] in args.case_ids]
    from ..components.policy_retrieval import HybridPolicyRetriever
    from ..components.price_query import DEFAULT_DB, SqlitePriceTool
    from ..graph import build_graph
    from ..main import router_fallback
    from ..llm import OllamaEngine

    retriever = HybridPolicyRetriever()
    retriever.require_dense()  # no silent keyword-only run labelled as hybrid
    graph = build_graph(retriever=retriever, price_tool=SqlitePriceTool(), intent_classifier=router_fallback())
    engine = OllamaEngine()
    hardware = None
    if engine.settings.device == "gpu":
        engine.for_policy({}).warm_up()
        loaded = engine.for_policy({}).verify_gpu_loaded()
        hardware = {k: loaded.get(k) for k in ("name", "digest", "size", "size_vram", "details")}
    report = {"completed": False, "started_at": datetime.now(timezone.utc).isoformat(),
              "split": "dev", "snapshot": active_snapshot(), "router_as_of": AS_OF,
              "dataset_sha256": hashlib.sha256(DEV_FILE.read_bytes()).hexdigest(),
              "inference": {"model": engine.settings.model, "device": engine.settings.device,
                            "threads": engine.settings.num_threads, "temperature": 0, "seed": 42,
                            "gpu_loaded_before_run": hardware},
              "evidence_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [ROOT / "data/policy_chunks" / active_snapshot() / "chunks.jsonl",
                                            *(ROOT / "data/topic_cards" / active_snapshot()).glob("*.json"),
                                            *(ROOT / "data/policy_index" / active_snapshot()).glob("vectors.*")]
                                  if p.exists()},
              "price_database_sha256": file_hash(Path(os.getenv("KOPI_RESALE_DB", str(DEFAULT_DB))))
                                        if Path(os.getenv("KOPI_RESALE_DB", str(DEFAULT_DB))).exists() else None,
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "backend/kopi_keys").rglob("*.py"))},
              "planned_ids": [q["id"] for q in questions], "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    save()
    for q in questions:
        try:
            row = review_case(graph, q)
        except Exception as error:
            # Exceptions remain explicit failures, never successful safe refusals.
            row = {"id": q["id"], "response": {"error": type(error).__name__}}
        report["cases"].append(row)
        save()
        print(q["id"], row["response"].get("status", row["response"].get("error")), flush=True)
    report["metrics"] = end_to_end(questions, {row["id"]: row["response"] for row in report["cases"]})
    report["metrics"].pop("ragas", None)
    report["completed"] = True
    save()
    print("Report:", args.output)
    return int(any("error" in row["response"] for row in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
