"""Retrieval regression floor: keyword search on the DEV set must not get worse.

Keyword (BM25) search needs no Ollama or index, so it runs offline in a few seconds and in
CI. Strict Hit@5 at the time of writing (2026-11-09, snapshot 2026-10-15): 14 of 22 policy
questions and 15 of 29 questions with evidence. Each floor is one question below that, so a
real drop fails while the floor never sits exactly on today's score.

If a change improves retrieval, raise the floors to one below the new counts. If the dev set
or the snapshot changes, re-measure with:
    python -m kopi_keys.evaluation.retrieval_report --mode bm25
Dev split only; the held-out set is never read here.
"""
from kopi_keys.components.policy_retrieval import KeywordPolicyRetriever
from kopi_keys.evaluation import metrics
from kopi_keys.evaluation.dataset import load_chunks, load_questions

FLOOR_POLICY_HITS = 13  # of 22 policy-retrieval questions (today 14)
FLOOR_ALL_HITS = 14     # of 29 questions with evidence (today 15)


def hits(rows):
    return sum(r["best_rank"] is not None and r["best_rank"] <= 5 for r in rows)


def test_keyword_search_hit_at_5_stays_above_the_floor():
    retriever = KeywordPolicyRetriever()
    report = metrics.retrieval_ranked(load_questions("dev"), retriever.ranked_ids, load_chunks(),
                                      set(retriever.by_id))
    rows = report["cases"]
    policy = [r for r in rows if r["category"] != "discovery"]
    misses = sorted(r["id"] for r in rows if not (r["best_rank"] and r["best_rank"] <= 5))
    assert hits(policy) >= FLOOR_POLICY_HITS, f"policy Hit@5 {hits(policy)}/{len(policy)}; misses: {misses}"
    assert hits(rows) >= FLOOR_ALL_HITS, f"all Hit@5 {hits(rows)}/{len(rows)}; misses: {misses}"
