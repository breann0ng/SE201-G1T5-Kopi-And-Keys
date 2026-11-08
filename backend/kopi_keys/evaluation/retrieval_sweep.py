"""Tune the hybrid retriever's settings on the dev set (Recall@5, MRR@10).

Usage (repo root, project venv, Ollama and the policy index running):
    python -m kopi_keys.evaluation.retrieval_sweep

Each dev question is embedded once; its keyword and dense rankings are cached,
then every combination below is scored with policy_retrieval.fuse, the code the
app runs. Each setting also gets the mean Recall@5 of its grid neighbours (one
parameter one step away): choose from a stable region, not a single lucky point.
The dev set has about 30 questions with evidence, so a difference of one or two
hits is noise. Dev questions only; never run this on the held-out set.
Reports go to .local/reports/ (gitignored).
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

from ..components import policy_index, policy_retrieval
from ..components.policy_retrieval import HybridPolicyRetriever, fuse
from .dataset import ROOT, load_questions

REPORTS = ROOT / ".local" / "reports"
DEPTH = 60  # ranking depth cached per question (>= the largest CANDIDATES below)

GRID = {
    "dense_weight": [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0],
    "rrf_k": [10, 20, 40, 60, 100],
    "candidates": [20, 30, 45, 60],
    "heading_bonus": [0.0, 0.3, 0.6, 1.0],
    "k1": [1.2, 1.5, 2.0],
    "b": [0.5, 0.75, 0.9],
}
CURRENT = {"dense_weight": policy_retrieval.DENSE_WEIGHT, "rrf_k": policy_retrieval.RRF_K,
           "candidates": policy_retrieval.CANDIDATES, "heading_bonus": policy_retrieval.HYBRID_HEADING_BONUS,
           "k1": 1.5, "b": 0.75}


def scores(questions: list[dict], ranked: dict[str, list[str]]) -> tuple[int, float]:
    """(hits in the top 5, mean reciprocal rank in the top 10)."""
    hits, rr = 0, 0.0
    for q in questions:
        got, want = ranked[q["id"]], set(q["expected_chunk_ids"])
        hits += bool(set(got[:5]) & want)
        rr += next((1 / (i + 1) for i, c in enumerate(got[:10]) if c in want), 0.0)
    return hits, rr / len(questions)


def main() -> int:
    questions = [q for q in load_questions("dev") if q.get("expected_chunk_ids")]
    retriever = HybridPolicyRetriever()
    try:
        retriever.require_dense()  # a partial index would make dense rankings look worse than they are
    except policy_index.IndexUnavailableError as error:
        raise SystemExit(f"Needs the full policy index and Ollama: {error}")
    keyword = retriever.keyword
    print(f"{len(questions)} dev questions with evidence; embedding each once")

    dense = {}
    for q in questions:
        vector = policy_index.embed([policy_index.query_text(q["question"])], timeout=60)[0]
        hits = retriever.collection.query(query_embeddings=[vector], n_results=DEPTH, where={"superseded": False})
        dense[q["id"]] = hits["ids"][0]

    kw_keys = ("heading_bonus", "k1", "b")
    kw_cache: dict[tuple, dict[str, list[str]]] = {}
    for values in itertools.product(*(GRID[k] for k in kw_keys)):
        setting = dict(zip(kw_keys, values))
        keyword.k1, keyword.b = setting["k1"], setting["b"]
        kw_cache[values] = {q["id"]: keyword.ranked_ids(q["question"], DEPTH, heading_bonus=setting["heading_bonus"])
                            for q in questions}
    keyword.k1, keyword.b = CURRENT["k1"], CURRENT["b"]

    def evaluate(setting: dict) -> tuple[int, float]:
        kw = kw_cache[tuple(setting[k] for k in kw_keys)]
        ranked = {q["id"]: fuse(keyword.by_id, q["question"], kw[q["id"]], dense[q["id"]], 10,
                                dense_weight=setting["dense_weight"], rrf_k=setting["rrf_k"],
                                candidates=setting["candidates"]) for q in questions}
        return scores(questions, ranked)

    names = list(GRID)
    results = {}
    for values in itertools.product(*(GRID[k] for k in names)):
        results[values] = evaluate(dict(zip(names, values)))

    def neighbours(values: tuple) -> list[tuple]:
        out = []
        for i, name in enumerate(names):
            j = GRID[name].index(values[i])
            for step in (-1, 1):
                if 0 <= j + step < len(GRID[name]):
                    out.append(values[:i] + (GRID[name][j + step],) + values[i + 1:])
        return out

    rows = []
    for values, (hits, mrr) in results.items():
        near = [results[n][0] for n in neighbours(values)]
        rows.append({**dict(zip(names, values)), "recall_at_5": hits, "mrr_at_10": round(mrr, 3),
                     "neighbour_mean_recall": round(sum(near) / len(near), 2)})
    rows.sort(key=lambda r: (-r["recall_at_5"], -r["neighbour_mean_recall"], -r["mrr_at_10"]))

    keyword_only = scores(questions, {q["id"]: fuse(keyword.by_id, q["question"],
                                                    kw_cache[(policy_retrieval._HEADING_BONUS, 1.5, 0.75)][q["id"]],
                                                    None, 10) for q in questions})
    dense_only = scores(questions, {q["id"]: dense[q["id"]][:10] for q in questions})
    current = evaluate(CURRENT)
    n = len(questions)
    report = {"questions": n, "embed_model": policy_index.EMBED_MODEL, "snapshot": keyword.snapshot,
              "keyword_only": {"recall_at_5": keyword_only[0], "mrr_at_10": round(keyword_only[1], 3)},
              "dense_only": {"recall_at_5": dense_only[0], "mrr_at_10": round(dense_only[1], 3)},
              "current": {**CURRENT, "recall_at_5": current[0], "mrr_at_10": round(current[1], 3)},
              "top": rows[:25], "grid": GRID}
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_retrieval_sweep.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"keyword only   Recall@5 {keyword_only[0]}/{n}  MRR@10 {keyword_only[1]:.3f}")
    print(f"dense only     Recall@5 {dense_only[0]}/{n}  MRR@10 {dense_only[1]:.3f}")
    print(f"current hybrid Recall@5 {current[0]}/{n}  MRR@10 {current[1]:.3f}  {CURRENT}")
    print("best settings (recall, neighbour mean, MRR):")
    for r in rows[:10]:
        print(f"  {r['recall_at_5']}/{n}  near {r['neighbour_mean_recall']:<5}  MRR {r['mrr_at_10']:<5}  "
              + "  ".join(f"{k}={r[k]}" for k in names))
    print(f"Report: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
