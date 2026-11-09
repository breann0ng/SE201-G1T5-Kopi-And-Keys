"""Run the dev set as a LangSmith experiment, so runs can be compared side by side in the UI.

Usage (repo root, project venv, LangSmith key in .env):
    python -m kopi_keys.evaluation.langsmith_eval upload                 # create/refresh the dataset
    python -m kopi_keys.evaluation.langsmith_eval run --prefix hybrid-k5 # code metrics only (free)
    python -m kopi_keys.evaluation.langsmith_eval run --limit 3          # quick smoke test
    python -m kopi_keys.evaluation.langsmith_eval run --judge anthropic:claude-haiku-5-5
    python -m kopi_keys.evaluation.langsmith_eval run --router rules --prefix rules-only

Scores per question come from metrics.end_to_end, the same code run_eval --local uses, so
LangSmith's averages match our reports: route_correct, unsafe_answering (abstain questions only),
over_abstention (answerable questions only), uncited, stale (policy_changed only), price_ok and
has_current (where labelled). Lower is better for unsafe/over-abstention/uncited/stale.

Each experiment output is {"response": ChatResponse}, the same shape as a live trace's output, so
the LangSmith UI evaluator maps inputs -> input.message and outputs -> output.response.message
for both, filtered to answered runs with
and(eq(output_key, "response.status"), eq(output_value, "answered")).

--judge adds an LLM-judged answer_relevance score on answered questions (prompt below). It
needs `pip install -e ".[judge]"` and the provider's key (OPENAI_API_KEY / ANTHROPIC_API_KEY)
in .env. Judge scores are softer evidence than the code metrics: calibrate before reporting.

The held-out set is never uploaded: it stays private for the final run_eval.
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from . import metrics
from .dataset import active_snapshot, load_questions

DATASET = "kopi-dev-set"

# Kept in the repo so the judge prompt we report is under version control.
RELEVANCE_PROMPT = """You are grading a Singapore HDB housing assistant. Its answers are built from
verbatim quotes of official HDB/CPF policy, each followed by citation IDs in [brackets], and
optionally a resale price summary computed from transaction data.

Judge ONLY whether the answer addresses the user's question:
- true if the quoted policy and/or price figures directly answer what was asked (the right
  scheme, the right buyer situation, the right town/flat type/period).
- false if the quotes are accurate but about a different scheme, buyer type or period than the
  user asked about, or if the answer misses the main part of a two-part question.

Do NOT penalise:
- verbatim, formal policy wording or citation brackets
- brevity, if the question is answered
- a note saying data for a period is unavailable, if it is accurate

<question>
{inputs}
</question>

<answer>
{outputs}
</answer>
"""

# Which end_to_end case fields become LangSmith feedback, and when they apply.
# (feedback key, case field, applies to question?)
SCORES = [
    ("route_correct", None, lambda q: True),
    ("unsafe_answering", "unsafe", lambda q: q["should_abstain"]),
    ("over_abstention", "over_abstained", lambda q: not q["should_abstain"]),
    ("uncited", "uncited", lambda q: True),
    ("stale", "stale", lambda q: q["category"] == "policy_changed"),
    ("has_current", "has_current", lambda q: q.get("current_value") is not None),
    ("price_ok", "price_ok", lambda q: True),
]


def _request(q: dict) -> dict:
    """The same request run_eval sends to /chat: the question plus its profile."""
    from ..schemas import BuyerProfile

    fields = BuyerProfile.model_fields
    return {"message": q["question"], "profile": {k: v for k, v in q["profile"].items() if k in fields}}


def upload(client) -> None:
    """Create the dataset, or bring it in line with the dev set file (keyed by question id)."""
    questions = load_questions("dev")
    if client.has_dataset(dataset_name=DATASET):
        dataset = client.read_dataset(dataset_name=DATASET)
    else:
        dataset = client.create_dataset(DATASET, description=(
            "Kopi & Keys development questions (data/evaluation-data/development). "
            "Synced by kopi_keys.evaluation.langsmith_eval upload; edit the JSONL, not this dataset."))
    existing = {(e.metadata or {}).get("id"): e for e in client.list_examples(dataset_id=dataset.id)}
    created = updated = 0
    for q in questions:
        inputs = _request(q)
        outputs = {k: q.get(k) for k in ("expected_route", "should_abstain", "expected_answer",
                                         "current_value", "superseded_value")}
        metadata = {"id": q["id"], "category": q["category"], "snapshot": active_snapshot()}
        if q["id"] in existing:
            client.update_example(existing.pop(q["id"]).id, inputs=inputs, outputs=outputs, metadata=metadata)
            updated += 1
        else:
            client.create_example(inputs=inputs, outputs=outputs, metadata=metadata, dataset_id=dataset.id)
            created += 1
    for stale in existing.values():  # questions removed from the dev set
        client.delete_example(stale.id)
    print(f"{DATASET}: {created} created, {updated} updated, {len(existing)} removed "
          f"({len(questions)} questions, snapshot {active_snapshot()})")


def run(client, prefix: str, judge_model: str | None, limit: int | None, concurrency: int,
        router: str = "hybrid") -> None:
    from langsmith import evaluate

    from ..components.policy_retrieval import TOP_K, HybridPolicyRetriever
    from ..components.price_query import SqlitePriceTool
    from ..graph import build_graph, run_graph
    from ..llm import OllamaSettings
    from ..schemas import ChatRequest

    by_id = {q["id"]: q for q in load_questions("dev")}
    from ..main import router_fallback

    classifier = router_fallback() if router == "hybrid" else None
    graph = build_graph(retriever=HybridPolicyRetriever(), price_tool=SqlitePriceTool(),
                        intent_classifier=classifier)  # as main.py

    def target(inputs: dict) -> dict:
        state = run_graph(graph, ChatRequest(**inputs))
        # Same shape as a live LangGraph trace's output ({"response": ...}), so one LangSmith
        # evaluator mapping (output.response.message) serves experiments and live traces alike.
        return {"response": state.response.model_dump(mode="json")}

    def code_metrics(outputs: dict, example) -> dict:
        q = by_id[example.metadata["id"]]
        case = metrics.end_to_end([q], {q["id"]: outputs["response"]})["cases"][0]
        if "error" in case:
            return {"key": "error", "score": 1, "comment": case["error"]}
        results = []
        for key, field, applies in SCORES:
            value = case["route"] == case["expected_route"] if field is None else case[field]
            if applies(q) and value is not None:
                results.append({"key": key, "score": int(bool(value))})
        return {"results": results}

    evaluators = [code_metrics]
    if judge_model:
        try:
            from openevals.llm import create_llm_as_judge
        except ImportError:
            raise SystemExit('--judge needs the judge extra: pip install -e ".[judge]"')
        judge = create_llm_as_judge(prompt=RELEVANCE_PROMPT, model=judge_model,
                                    feedback_key="answer_relevance")

        def answer_relevance(inputs: dict, outputs: dict) -> dict:
            response = outputs["response"]
            if response.get("status") != "answered":
                return {"results": []}  # abstentions and clarifications have nothing to judge
            return judge(inputs=inputs["message"], outputs=response["message"])

        evaluators.append(answer_relevance)

    data = client.list_examples(dataset_name=DATASET, limit=limit) if limit else DATASET
    settings = OllamaSettings.from_env()
    evaluate(
        target, data=data, evaluators=evaluators, experiment_prefix=prefix,
        max_concurrency=concurrency, client=client,
        metadata={"model": settings.model, "device": settings.device, "top_k": TOP_K,
                  "retriever": "hybrid", "snapshot": active_snapshot(), "judge": judge_model,
                  "router": "hybrid" if classifier else "rules"},
    )


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("upload", help=f"create or sync the {DATASET} dataset")
    r = sub.add_parser("run", help="run the graph on the dataset as a LangSmith experiment")
    r.add_argument("--prefix", default="dev", help="experiment name prefix, e.g. hybrid-k5")
    r.add_argument("--judge", metavar="PROVIDER:MODEL", help="add an LLM-judged answer_relevance score")
    r.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    r.add_argument("--router", choices=["hybrid", "rules"], default="hybrid",
                   help="hybrid: rules + LLM fallback, as the app runs (default); rules: no fallback")
    r.add_argument("--concurrency", type=int, default=1,
                   help="questions at once (default 1: a CPU Ollama is the bottleneck)")
    args = ap.parse_args()

    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        raise SystemExit("Set LANGCHAIN_API_KEY (or LANGSMITH_API_KEY) in .env first.")
    from langsmith import Client

    client = Client()
    if args.command == "upload":
        upload(client)
    else:
        if not client.has_dataset(dataset_name=DATASET):
            raise SystemExit(f"No {DATASET} dataset yet: run the upload command first.")
        run(client, args.prefix, args.judge, args.limit, args.concurrency, args.router)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
