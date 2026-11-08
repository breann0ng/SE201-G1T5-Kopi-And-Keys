"""Relaxed retrieval scoring: accepted alternatives widen an item, never replace labels."""
import pytest

from kopi_keys.evaluation import metrics
from kopi_keys.evaluation.dataset import load_chunks, load_questions

CHUNKS = [
    {"chunk_id": "A", "superseded": False, "source_slug": "hdb-x", "content": "you must be 35"},
    {"chunk_id": "B", "superseded": False, "source_slug": "hdb-y", "content": "aged 35 and above"},
    {"chunk_id": "C", "superseded": True, "source_slug": "hdb-y", "content": "aged 35 and above"},
]
Q = {"id": "Q1", "category": "policy", "question": "q", "evidence": [{"source": "hdb-x", "quote": "must be 35"}]}


def test_alternative_adds_to_the_item_and_skips_superseded_chunks():
    accepted = {"Q1": [{"item": 0, "source": "hdb-y", "quote": "aged 35 and above"}]}
    assert metrics.gold_chunk_sets(Q, CHUNKS) == [{"A"}]
    assert metrics.gold_chunk_sets(Q, CHUNKS, accepted) == [{"A", "B"}]


def test_alternative_quote_that_matches_nothing_fails_loudly():
    with pytest.raises(ValueError, match="accepted quote"):
        metrics.gold_chunk_sets(Q, CHUNKS, {"Q1": [{"item": 0, "source": "hdb-y", "quote": "not there"}]})


def test_relaxed_scoring_never_lowers_a_score():
    def search(query, k):
        return ["B"]
    strict = metrics.retrieval_ranked([Q], search, CHUNKS)
    relaxed = metrics.retrieval_ranked([Q], search, CHUNKS, accepted={
        "Q1": [{"item": 0, "source": "hdb-y", "quote": "aged 35 and above"}]})
    assert strict["all"]["hit_at_5"] == 0 and relaxed["all"]["hit_at_5"] == 1


def test_repo_accepted_evidence_resolves_against_the_snapshot():
    accepted = metrics.load_accepted()
    questions = {q["id"]: q for q in load_questions("dev")}
    chunks = load_chunks()
    for qid in accepted:
        strict = metrics.gold_chunk_sets(questions[qid], chunks)
        relaxed = metrics.gold_chunk_sets(questions[qid], chunks, accepted)
        assert all(s <= r for s, r in zip(strict, relaxed)) and strict != relaxed
