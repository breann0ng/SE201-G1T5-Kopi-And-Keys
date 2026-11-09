"""Evaluation must not confuse first-turn routing or wall-clock drift with model quality."""
import pytest

from kopi_keys.evaluation import metrics, run_eval
from kopi_keys.evaluation.run_baselines import run_full
from kopi_keys.components.query_router import extract_month_range


class Reply:
    status_code = 200
    def __init__(self, data):
        self.data = data
    def json(self):
        return self.data


def test_in_process_eval_pins_every_turn_and_retains_initial_route():
    observed = []
    class Client:
        def post(self, url, json):
            observed.append((extract_month_range("past 6 months"), json))
            return Reply({"status": "clarifying" if len(observed) == 1 else "answered",
                          "route": "clarify" if len(observed) == 1 else "price",
                          "message": "Please provide: flat type."})
    question = {"profile": {}, "turns": [{"user": "Past 6 months prices in Bishan?"}, {"user": "4-room"}]}
    response = run_full(Client(), question, as_of="2026-10")
    assert [r[0] for r in observed] == [("2026-05", "2026-10")] * 2
    assert observed[1][1]["history"][0]["content"] == question["turns"][0]["user"]
    assert response["initial_route"] == "clarify" and response["route"] == "price"
    assert response["router_as_of"] == "2026-10" and response["turns_sent"] == 2


def test_remote_evaluation_refuses_incomparable_relative_dates(monkeypatch):
    monkeypatch.setattr(run_eval, "AS_OF", "2000-01")
    question = {"id": "PRC-99", "turns": [{"user": "past 6 months"}]}
    with pytest.raises(SystemExit, match="Use --local"):
        run_eval.chat_responses([question], "http://unused.invalid")


def test_initial_route_metric_does_not_hide_final_route_or_lexical_staleness_flag():
    question = {"id": "A", "category": "policy_changed", "question": "q", "expected_route": "clarify",
                "should_abstain": False, "current_value": "$18,000", "superseded_value": "$16,000"}
    response = {"status": "answered", "route": "policy", "initial_route": "clarify",
                "message": "Earlier cohort: $16,000. Later cohort: $18,000.", "citations": [{"id": "test"}]}
    scored = metrics.end_to_end([question], {"A": response})
    assert scored["routing_accuracy"] == "0% (0/1)"
    assert scored["initial_routing_accuracy"] == "100% (1/1)"
    assert scored["staleness_errors"] == "100% (1/1)"  # retain the raw screen, do not erase it
    assert "human cohort/context review" in scored["staleness_method"]


def test_price_metric_rejects_same_numbers_from_wrong_subset():
    from decimal import Decimal
    question = {"expected_price": {"volume": 6, "median": Decimal(5)},
                "price_filters": {"town": "BISHAN", "flat_type": "4 ROOM", "start_month": "2026-01",
                                  "end_month": "2026-10", "storey_band": "high"}}
    response = {"price_result": {"volume": 6, "median": "5", "filters": {
        **question["price_filters"], "storey_band": None}}}
    assert metrics._price_matches(question, response) is False
    response["price_result"]["filters"]["storey_band"] = "high"
    assert metrics._price_matches(question, response) is True
