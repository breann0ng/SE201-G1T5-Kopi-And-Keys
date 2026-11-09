import pytest

from kopi_keys.evaluation import stats
from kopi_keys.evaluation.compare import answer_outcomes


def test_wilson_matches_known_values():
    lo, hi = stats.wilson(18, 22)
    assert (round(lo, 3), round(hi, 3)) == (0.615, 0.927)
    assert stats.wilson(0, 9)[0] == 0.0 and stats.wilson(0, 9)[1] == pytest.approx(0.299, abs=1e-3)
    assert stats.wilson(9, 9)[1] == 1.0
    assert stats.wilson(0, 0) == (0.0, 1.0)


def test_exact_mcnemar():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(0, 2) == 0.5
    assert stats.mcnemar_exact(0, 9) == pytest.approx(2 / 512)
    assert stats.mcnemar_exact(3, 3) == 1.0
    assert stats.mcnemar_exact(1, 9) == stats.mcnemar_exact(9, 1)


def test_paired_counts_only_shared_questions():
    a = {"q1": True, "q2": False, "q3": True, "q4": True}
    b = {"q1": True, "q2": True, "q3": False, "q5": True}
    p = stats.paired(a, b)
    assert (p["n"], p["only_a"], p["only_b"]) == (3, 1, 1)


def test_paired_tells_the_two_systems_apart():
    # q1 both right, q2 only A, q3 only B twice over: counts must not swap or include ties.
    a = {"q1": True, "q2": True, "q3": False, "q4": False, "q5": False}
    b = {"q1": True, "q2": False, "q3": True, "q4": True, "q5": False}
    p = stats.paired(a, b)
    assert (p["n"], p["a"], p["b"], p["only_a"], p["only_b"]) == (5, 2, 3, 1, 2)
    assert p["p"] == 1.0  # 1 vs 2 discordant: no evidence of a difference


def test_rate_formats_percent_count_and_interval():
    assert stats.rate(18, 22) == "81.8% (18/22), 95% CI 61.5-92.7%"
    assert stats.rate(0, 9) == "0.0% (0/9), 95% CI 0.0-29.9%"
    assert stats.rate(0, 0) == "n/a"


def test_run_errors_count_as_failures_on_a_fixed_population():
    questions = [
        {"id": "A", "category": "policy", "should_abstain": False},
        {"id": "B", "category": "policy", "should_abstain": True},
    ]
    metrics = {"cases": [{"id": "A", "error": "timeout"},
                         {"id": "B", "category": "policy", "status": "abstained", "route": "policy",
                          "expected_route": "policy", "unsafe": False, "over_abstained": False,
                          "uncited": False, "stale": False, "price_ok": None}]}
    out = answer_outcomes(metrics, questions)
    assert out["answers_answerable"] == {"A": False}
    assert out["safe_when_should_abstain"] == {"B": True}
    assert out["routing"] == {"A": False, "B": True}
