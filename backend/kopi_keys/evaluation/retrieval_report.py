"""Retrieval metrics on the DEV set: Hit@5, Recall@5, Recall@20, MRR@20, per slice.

Usage (repo root, project venv; dense and hybrid need Ollama and the policy index):
    python -m kopi_keys.evaluation.retrieval_report --mode hybrid   # bm25 | dense | hybrid

Slices: all questions with evidence, policy retrieval (every category except
discovery) and discovery only. Discovery answers take their evidence from the
matched topic cards' supporting chunks as well as from search, so their Recall@5
is reported separately rather than mixed into the retrieval figure.

Writes data/evaluation-data/results/<timestamp>_retrieval_<mode>_dev.json and
prints a summary and the per-question miss table. Dev split only.

Strict scores use the labels as written. The same search results are also scored
"relaxed" (report["relaxed"]): evidence items also accept the alternatives in
data/evaluation-data/development/accepted_evidence.json, which states its rule.
Both are always reported.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from time import perf_counter

from . import metrics
from .dataset import DATA, load_chunks, load_questions

RESULTS = DATA / "evaluation-data" / "results"


def searcher(mode: str):
    """fn(query, k) -> chunk IDs, and the set of chunk IDs that mode can return."""
    from ..components import policy_index
    from ..components.policy_retrieval import HybridPolicyRetriever, KeywordPolicyRetriever

    if mode == "bm25":
        r = KeywordPolicyRetriever()
        return (lambda query, k: r.ranked_ids(query, k)), set(r.by_id)
    r = HybridPolicyRetriever()
    try:
        r.require_dense()  # never report keyword-only search as dense or hybrid
    except policy_index.IndexUnavailableError as error:
        raise SystemExit(f"{mode} needs the full policy index and Ollama: {error}")
    indexed = set(r.collection.get(include=[])["ids"])
    if mode == "dense":
        return (lambda query, k: r._dense(query)[:k]), indexed
    return (lambda query, k: [p.id for p in r.search(query, limit=k, strict=True)]), indexed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    ap.add_argument("--tag", default="", help="label added to the output file name")
    args = ap.parse_args()

    questions = load_questions("dev")
    search, indexed = searcher(args.mode)
    times = []

    cache: dict[str, list[str]] = {}

    def timed(query, k):
        if query not in cache:  # searched once, scored strict and relaxed
            t = perf_counter()
            cache[query] = search(query, k)
            times.append(perf_counter() - t)
        return cache[query]

    chunks = load_chunks()
    report = metrics.retrieval_ranked(questions, timed, chunks, indexed)
    report["relaxed"] = metrics.retrieval_ranked(questions, timed, chunks, indexed, accepted=metrics.load_accepted())
    report["mode"] = args.mode
    report["mean_latency_ms"] = round(1000 * sum(times) / len(times), 1) if times else None
    RESULTS.mkdir(parents=True, exist_ok=True)
    tag = f"_{args.tag}" if args.tag else ""
    path = RESULTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_retrieval_{args.mode}{tag}_dev.json"
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"mode={args.mode}  latency {report['mean_latency_ms']} ms/query")
    print(f"{'slice':18} {'n':>3} {'Hit@5':>6} {'Rec@5':>6} {'Rec@20':>6} {'MRR@20':>6} {'NOT_IN_INDEX':>12}")
    for label, rep in (("", report), (" relaxed", report["relaxed"])):
        for name in ("all", "policy_retrieval", "discovery"):
            s = rep[name]
            print(f"{name + label:18} {s['n']:>3} {s['hit_at_5']:>6.1%} {s['recall_at_5']:>6.1%} "
                  f"{s['recall_at_20']:>6.1%} {s['mrr_at_20']:>6.3f} {s['not_in_index']:>12}")
    print("\nqid      cat              n_gold found@5 best  miss_type")
    for r in report["cases"]:
        if r["miss_type"] != "hit" or r["found_at_5"] < r["n_gold"]:
            print(f"{r['id']:8} {r['category']:16} {r['n_gold']:>6} {r['found_at_5']:>7} {str(r['best_rank']):>5}  "
                  f"{r['miss_type']}  item_ranks={r['item_ranks']}")
    print(f"\nReport: {path.relative_to(DATA.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
