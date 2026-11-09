"""Paired comparison tables (evaluation/compare.py): which questions count, and how.

Written after mutation testing showed most of compare.py could change without a test failing.
All inputs are small hand-made result dicts; nothing here needs Ollama or the dev set.
"""
import json

import pytest

from kopi_keys.evaluation import compare

OK = {"route": "policy", "expected_route": "policy", "status": "answered", "unsafe": False,
      "over_abstained": False, "uncited": False, "stale": False, "price_ok": None}


def case(qid, **changes):
    return {"id": qid, **OK, **changes}


def question(qid, category="policy", should_abstain=False, **extra):
    return {"id": qid, "category": category, "should_abstain": should_abstain, **extra}


# --- answer_outcomes: one rule per metric ------------------------------------

def test_clean_answer_succeeds_on_every_metric_it_belongs_to():
    out = compare.answer_outcomes({"cases": [case("A")]}, [question("A")])
    assert out["routing"] == {"A": True}
    assert out["answers_answerable"] == {"A": True}
    assert out["cited_answer"] == {"A": True}
    # A policy question with no price and no policy change is not in those populations.
    assert out["not_stale"] == {} and out["price_correct"] == {} and out["safe_when_should_abstain"] == {}


def test_wrong_route_fails_routing_only():
    out = compare.answer_outcomes({"cases": [case("A", route="price")]}, [question("A")])
    assert out["routing"] == {"A": False}
    assert out["answers_answerable"] == {"A": True}


def test_should_abstain_question_is_scored_on_safety_not_answering():
    qs = [question("S", should_abstain=True), question("U", should_abstain=True)]
    out = compare.answer_outcomes({"cases": [case("S"), case("U", unsafe=True)]}, qs)
    assert out["safe_when_should_abstain"] == {"S": True, "U": False}
    assert out["answers_answerable"] == {} and out["cited_answer"] == {}


def test_over_abstaining_fails_answering_and_citation():
    out = compare.answer_outcomes(
        {"cases": [case("A", over_abstained=True, status="abstained")]}, [question("A")])
    assert out["answers_answerable"] == {"A": False}
    assert out["cited_answer"] == {"A": False}


def test_uncited_answer_still_answers_but_fails_citation():
    out = compare.answer_outcomes({"cases": [case("A", uncited=True)]}, [question("A")])
    assert out["answers_answerable"] == {"A": True}
    assert out["cited_answer"] == {"A": False}


def test_policy_changed_questions_are_scored_on_staleness():
    qs = [question("F", "policy_changed"), question("S", "policy_changed")]
    out = compare.answer_outcomes({"cases": [case("F"), case("S", stale=True)]}, qs)
    assert out["not_stale"] == {"F": True, "S": False}


def test_price_correct_counts_only_questions_with_an_expected_volume():
    qs = [question("P", "price", expected_price={"volume": 12}),
          question("N", "price", expected_price={"volume": 3}),
          question("X", "price", expected_price={"volume": 0}),
          question("Y", "price", expected_price={})]
    cases = [case("P", price_ok=True), case("N", price_ok=None), case("X", price_ok=True), case("Y", price_ok=True)]
    out = compare.answer_outcomes({"cases": cases}, qs)
    assert out["price_correct"] == {"P": True, "N": False}


def test_missing_or_errored_case_fails_every_metric_it_is_in():
    qs = [question("A", "policy_changed", expected_price={"volume": 5}), question("B", should_abstain=True)]
    out = compare.answer_outcomes({"cases": [case("B", error="timeout")]}, qs)
    assert out["routing"] == {"A": False, "B": False}
    assert out["answers_answerable"] == {"A": False} and out["cited_answer"] == {"A": False}
    assert out["not_stale"] == {"A": False} and out["price_correct"] == {"A": False}
    assert out["safe_when_should_abstain"] == {"B": False}


# --- retrieval_outcomes ------------------------------------------------------

def test_retrieval_outcomes_split_policy_and_discovery():
    report = {"cases": [{"id": "P1", "category": "policy", "found_at_5": 1},
                        {"id": "P2", "category": "eligibility", "found_at_5": 0},
                        {"id": "D1", "category": "discovery", "found_at_5": 2}]}
    out = compare.retrieval_outcomes(report)
    assert out == {"hit@5 all": {"P1": True, "P2": False, "D1": True},
                   "hit@5 policy": {"P1": True, "P2": False},
                   "hit@5 discovery": {"D1": True}}


# --- labels, loading and the Markdown table ----------------------------------

def test_label_prefers_system_name_then_mode_and_file_stamp():
    assert compare.label({"system": "full", "_file": "x"}) == "full"
    assert compare.label({"mode": "bm25", "_file": "20261108T003805Z_retrieval_bm25_dev.json"}) \
        == "bm25 (20261108T003805Z)"  # the 16-character run timestamp
    assert compare.label({"_file": "abc"}) == "? (abc)"


def test_load_reads_a_path_or_a_name_in_the_results_folder(tmp_path, monkeypatch):
    (tmp_path / "r.json").write_text(json.dumps({"mode": "bm25"}), encoding="utf-8")
    monkeypatch.setattr(compare, "RESULTS", tmp_path)
    assert compare._load(str(tmp_path / "r.json")) == {"mode": "bm25", "_file": "r.json"}
    assert compare._load("r.json") == {"mode": "bm25", "_file": "r.json"}


def retrieval_result(mode, hits, relaxed_hits=None):
    rows = [{"id": qid, "category": cat, "found_at_5": f} for qid, cat, f in hits]
    out = {"mode": mode, "_file": f"{mode}.json", "cases": rows}
    if relaxed_hits is not None:
        out["relaxed"] = {"cases": [{"id": q, "category": c, "found_at_5": f} for q, c, f in relaxed_hits]}
    return out


REF = [("Q1", "policy", 1), ("Q2", "policy", 0), ("Q3", "discovery", 1)]
NEW = [("Q1", "policy", 1), ("Q2", "policy", 1), ("Q3", "discovery", 0)]


def test_table_rates_and_paired_rows_for_retrieval_reports():
    md = compare.table([retrieval_result("bm25", REF), retrieval_result("hybrid", NEW)])
    lines = md.splitlines()
    assert lines[0] == "| metric | bm25 (bm25.json) | hybrid (hybrid.json) |"
    assert lines[1] == "|---|---|---|"
    assert lines[2] == "| hit@5 all | 66.7% (2/3), 95% CI 20.8-93.9% | 66.7% (2/3), 95% CI 20.8-93.9% |"
    assert lines[3] == "| hit@5 policy | 50.0% (1/2), 95% CI 9.5-90.5% | 100.0% (2/2), 95% CI 34.2-100.0% |"
    assert lines[4] == "| hit@5 discovery | 100.0% (1/1), 95% CI 20.7-100.0% | 0.0% (0/1), 95% CI 0.0-79.3% |"
    assert "Paired vs **bm25 (bm25.json)**" in md
    assert "| hit@5 all | hybrid (hybrid.json) | 3 | 1 | 1 | 1 |" in lines
    assert "| hit@5 policy | hybrid (hybrid.json) | 2 | 0 | 1 | 1 |" in lines
    assert lines[-1] == "Files: bm25.json, hybrid.json"


def test_table_relaxed_uses_the_relaxed_cases_and_renames_the_mode():
    md = compare.table([retrieval_result("bm25", REF, relaxed_hits=NEW)], relaxed=True)
    assert md.splitlines()[0] == "| metric | bm25 relaxed (bm25.json) |"
    assert "| hit@5 policy | 100.0% (2/2), 95% CI 34.2-100.0% |" in md


def test_table_relaxed_refuses_reports_without_relaxed_scores():
    with pytest.raises(SystemExit, match="relaxed"):
        compare.table([retrieval_result("bm25", REF, relaxed_hits=NEW), retrieval_result("dense", REF)],
                      relaxed=True)
    with pytest.raises(SystemExit, match="relaxed"):
        compare.table([{"system": "full", "_file": "f.json", "cases": []}], relaxed=True)


def test_table_refuses_a_mix_of_answer_and_retrieval_files():
    with pytest.raises(SystemExit, match="mix"):
        compare.table([retrieval_result("bm25", REF), {"system": "full", "_file": "f.json", "cases": []}])


def test_table_scores_answer_level_files_against_the_dev_questions(monkeypatch):
    monkeypatch.setattr(compare, "load_questions", lambda split: [question("A"), question("B")])
    ref = {"system": "full", "_file": "full.json", "cases": [case("A"), case("B", route="price")]}
    md = compare.table([ref])
    assert md.splitlines()[0] == "| metric | full |"
    assert "| routing | 50.0% (1/2), 95% CI 9.5-90.5% |" in md
    assert "| safe_when_should_abstain | n/a |" in md
