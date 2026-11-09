"""retrieval_report: the search adapter and the report it writes (no Ollama needed).

Added after mutation testing found this module had no tests. main() is run with a fake
search and two hand-made questions, writing into a temp folder, never into data/.
"""
import json
import sys

import pytest

from kopi_keys.components import policy_index
from kopi_keys.evaluation import retrieval_report as rr

CHUNKS = [
    {"chunk_id": "A", "superseded": False, "source_slug": "hdb-x", "content": "you must be 35"},
    {"chunk_id": "B", "superseded": False, "source_slug": "hdb-y", "content": "aged 35 and above"},
    {"chunk_id": "C", "superseded": False, "source_slug": "hdb-z", "content": "grants for families"},
]
QUESTIONS = [
    {"id": "Q1", "category": "policy", "question": "how old", "evidence": [{"source": "hdb-x", "quote": "must be 35"}]},
    {"id": "Q2", "category": "discovery", "question": "how old",
     "evidence": [{"source": "hdb-z", "quote": "grants for families"}]},
]
ACCEPTED = {"Q1": [{"item": 0, "source": "hdb-y", "quote": "aged 35 and above"}]}


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    """run(mode, ranked_ids) -> (report dict, printed text, number of searches)."""
    def go(mode, ranked, tag=""):
        calls = []

        def search(query, k):
            calls.append((query, k))
            return list(ranked)

        data = tmp_path / "data"
        monkeypatch.setattr(rr, "DATA", data)
        monkeypatch.setattr(rr, "RESULTS", data / "results")
        monkeypatch.setattr(rr, "load_questions", lambda split: QUESTIONS)
        monkeypatch.setattr(rr, "load_chunks", lambda: CHUNKS)
        monkeypatch.setattr(rr.metrics, "load_accepted", lambda: ACCEPTED)
        monkeypatch.setattr(rr, "searcher", lambda m: (search, {"A", "B", "C"}))
        argv = ["retrieval_report", "--mode", mode] + (["--tag", tag] if tag else [])
        monkeypatch.setattr(sys, "argv", argv)
        assert rr.main() == 0
        files = list((data / "results").glob("*.json"))
        assert len(files) == 1
        return files[0], json.loads(files[0].read_text(encoding="utf-8")), capsys.readouterr().out, calls
    return go


def test_report_file_name_mode_and_both_scorings(run):
    path, report, out, calls = run("bm25", ["B", "C"], tag="synonyms")
    assert path.name.endswith("_retrieval_bm25_synonyms_dev.json") and len(path.name) == len(
        "20261108T003805Z_retrieval_bm25_synonyms_dev.json")
    assert report["mode"] == "bm25"
    # Strict: Q1's gold is only A (missed); relaxed also accepts B (hit at rank 1).
    assert report["all"]["n"] == 2 and report["policy_retrieval"]["hit_at_5"] == 0
    assert report["relaxed"]["policy_retrieval"]["hit_at_5"] == 1
    assert report["discovery"]["hit_at_5"] == 1
    assert f"Report: {path.relative_to(path.parents[2]).as_posix()}" in out.replace("\\", "/")


def test_each_query_is_searched_once_and_latency_is_reported(run):
    _, report, _, calls = run("hybrid", ["A"])
    assert len(calls) == 1  # both questions share one query; strict and relaxed reuse it
    assert calls[0][0] == "how old"
    assert isinstance(report["mean_latency_ms"], float) and report["mean_latency_ms"] >= 0


def test_summary_prints_both_scorings_and_lists_only_misses(run):
    _, _, out, _ = run("dense", ["C"])
    lines = out.splitlines()
    assert lines[0].startswith("mode=dense  latency ")
    assert any(line.startswith("policy_retrieval ") for line in lines)
    assert any(line.startswith("policy_retrieval relaxed") for line in lines)
    assert any(line.startswith("Q1 ") and "not_in_top20" in line for line in lines)
    assert not any(line.startswith("Q2 ") for line in lines)  # Q2 was a full hit


def test_bm25_searcher_returns_keyword_ranks_and_every_chunk(monkeypatch):
    from kopi_keys.components import policy_retrieval

    class NoHybrid:  # the keyword baseline must never touch the hybrid retriever
        def __init__(self, *a, **k):
            raise AssertionError("bm25 mode built a HybridPolicyRetriever")

    monkeypatch.setattr(policy_retrieval, "HybridPolicyRetriever", NoHybrid)
    search, indexed = rr.searcher("bm25")
    ids = search("enhanced cpf housing grant", 5)
    assert 0 < len(ids) <= 5 and set(ids) <= indexed and len(indexed) > 100


class FakeHybrid:
    """Stands in for HybridPolicyRetriever: records how each search was called."""
    calls: list = []

    class collection:
        @staticmethod
        def get(include):
            return {"ids": ["A", "B", "C"]}

    def require_dense(self):
        pass

    def _dense(self, query):
        FakeHybrid.calls.append(("dense", query))
        return ["C", "B", "A"]

    def search(self, query, limit, strict):
        FakeHybrid.calls.append(("hybrid", query, limit, strict))

        class P:
            def __init__(self, i):
                self.id = i
        return [P("B"), P("A")]


def test_dense_mode_uses_vectors_only_and_hybrid_mode_is_strict(monkeypatch):
    from kopi_keys.components import policy_retrieval

    monkeypatch.setattr(policy_retrieval, "HybridPolicyRetriever", FakeHybrid)
    FakeHybrid.calls = []
    dense, indexed = rr.searcher("dense")
    assert dense("q", 2) == ["C", "B"] and indexed == {"A", "B", "C"}
    hybrid, _ = rr.searcher("hybrid")
    assert hybrid("q", 5) == ["B", "A"]
    assert FakeHybrid.calls == [("dense", "q"), ("hybrid", "q", 5, True)]


def test_dense_searcher_refuses_to_run_keyword_only(monkeypatch):
    from kopi_keys.components import policy_retrieval

    class NoDense:
        def require_dense(self):
            raise policy_index.IndexUnavailableError("no index")

    monkeypatch.setattr(policy_retrieval, "HybridPolicyRetriever", NoDense)
    with pytest.raises(SystemExit, match="hybrid needs the full policy index"):
        rr.searcher("hybrid")
