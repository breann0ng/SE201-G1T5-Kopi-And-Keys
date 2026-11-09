"""Short price follow-ups ("what about 2015", "how about 5-room?") reuse the previous question."""

import csv
from datetime import date

import pytest

from fakes import FictionalRetriever
from kopi_keys.components.price_query import SqlitePriceTool
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.ingest import resale_db as importer
from kopi_keys.schemas import ChatRequest, HistoryTurn
from kopi_keys.state import initial_state

FIRST = "What were 4-room flats in Tampines selling for in 2028?"
ROW = {
    "month": "2025-01", "town": "TAMPINES", "flat_type": "4 ROOM", "block": "101",
    "street_name": "TAMPINES ST 11", "storey_range": "04 TO 06", "floor_area_sqm": "92",
    "flat_model": "Model A", "lease_commence_date": "1985", "remaining_lease": "59 years 03 months",
    "resale_price": "500000",
}


@pytest.fixture
def graph(tmp_path):
    rows = [ROW, {**ROW, "flat_type": "5 ROOM", "resale_price": "650000"},
            {**ROW, "town": "BEDOK", "resale_price": "450000"}, {**ROW, "month": "2025-07"}]
    csv_path = tmp_path / "resale.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    importer.build(csv_path, tmp_path / "db.sqlite", today=date(2026, 10, 15), downloaded_on=date(2026, 10, 15))
    return build_graph(retriever=FictionalRetriever(), price_tool=SqlitePriceTool(tmp_path / "db.sqlite"),
                       synthesiser=Synthesiser(engine=None), cards=[])


# The assistant's reply does not decide the carry-over; this is what FIRST gets.
FIRST_REPLY = ("Our records cover sales from Jan 2017 to Jul 2025, so there are no sales for Jan 2028 onwards. "
               "Past sales can't tell you what future prices will be.")


def follow_up(message, first=FIRST):
    return ChatRequest(message=message, history=[HistoryTurn(role="user", content=first),
                                                 HistoryTurn(role="assistant", content=FIRST_REPLY)])


def test_period_follow_up_keeps_town_and_flat_and_uses_the_new_period(graph):
    state = run_graph(graph, follow_up("what about sales in 2015"))
    assert (state.route, state.town, state.flat_type) == ("price", "TAMPINES", "4 ROOM")
    assert (state.start_month, state.end_month) == ("2015-01", "2015-12")
    assert state.abstain_reason == "price_out_of_range"
    assert state.response.message == ("Our records cover sales from Jan 2017 to Jul 2025, "
                                      "so there are no sales before Jan 2017.")


def test_flat_type_follow_up_overrides_the_remembered_flat_type(graph):
    state = run_graph(graph, follow_up("how about 5-room?"))
    assert (state.route, state.town, state.flat_type) == ("price", "TAMPINES", "5 ROOM")


def test_town_follow_up_overrides_the_remembered_town(graph):
    state = run_graph(graph, follow_up("and in Bedok?"))
    assert (state.route, state.town, state.flat_type) == ("price", "BEDOK", "4 ROOM")


def test_a_bare_period_is_a_follow_up():
    assert initial_state(follow_up("2019?"))["followup_question"] == FIRST


@pytest.mark.parametrize("message", ["what about next year", "what about next year?", "is mine worth more?"])
def test_forecasts_and_valuations_still_abstain(graph, message):
    assert initial_state(follow_up(message)).get("followup_question") is None
    state = run_graph(graph, follow_up(message))
    assert state.route == "abstain" and state.response.status == "abstained"


def test_unrelated_new_question_does_not_inherit_the_price_question(graph):
    assert initial_state(follow_up("What is the EHG?")).get("followup_question") is None
    assert run_graph(graph, follow_up("What is the EHG?")).route == "policy"


def test_no_carry_over_after_a_policy_question():
    request = follow_up("what about 2015", first="How long is an HFE letter valid for?")
    assert initial_state(request).get("followup_question") is None


FLOOR_AND_LEASE = "how about 16th floor and what are the remaining lease restrictions?"


def floor_history(message):
    return ChatRequest(message=message, history=[
        HistoryTurn(role="user", content="What are resale prices for 4-room flats in Tampines?"),
        HistoryTurn(role="assistant", content="Historical transaction summary."),
        HistoryTurn(role="user", content=FLOOR_AND_LEASE),
        HistoryTurn(role="assistant", content="Which floor band would you like to compare?"),
    ])


@pytest.mark.parametrize("message", [FLOOR_AND_LEASE, "what about floor 16?", "16th floor"])
def test_exact_floor_followup_clarifies_tool_limit_without_model_calls(graph, message):
    state = run_graph(graph, follow_up(message))
    assert state.response.status == "clarifying"
    assert state.missing_fields == ["floor_scope"] and state.model_calls == 0
    assert state.price_result is None and state.storey_band is None
    assert "cannot filter transactions to one exact floor" in state.response.message
    assert "high floors (13+)" in state.response.message
    if "lease" in message:
        assert "CPF usage" in state.response.message and "grant eligibility" in state.response.message


def test_year_after_floor_lease_clarification_explains_data_coverage(graph):
    state = run_graph(graph, floor_history("how about the data in 2027"))
    assert state.followup_question == "What are resale prices for 4-room flats in Tampines?"
    assert (state.town, state.flat_type) == ("TAMPINES", "4 ROOM")
    assert state.abstain_reason == "price_out_of_range" and state.model_calls == 0
    assert "Jan 2017 to Jul 2025" in state.response.message
    assert "Jan 2027" in state.response.message
    assert "Past sales can't tell you what future prices will be" in state.response.message


def test_answering_floor_clarification_uses_only_the_requested_supported_band(graph):
    state = run_graph(graph, floor_history("high floor"))
    assert state.route == "price" and state.storey_band == "high"
    assert state.price_result.filters.storey_band == "high"
    assert state.response.status == "abstained"  # fixture has no high-floor transactions
    assert "No matching" in state.response.message


def test_an_unrelated_policy_question_still_resets_price_followup_context():
    request = floor_history("how about the data in 2027")
    request.history.extend([
        HistoryTurn(role="user", content="What is the EHG?"),
        HistoryTurn(role="assistant", content="Grant overview."),
    ])
    assert initial_state(request).get("followup_question") is None


@pytest.mark.parametrize("message", [
    "How about the 16th floor; can you predict prices next year?",
    "How about recommending a good property agent in Tampines?",
    "How about the 16th floor; should I buy now or wait?",
])
def test_price_context_does_not_bypass_scope_guards(graph, message):
    request = floor_history(message)
    assert initial_state(request).get("followup_question") is None
    state = run_graph(graph, request)
    assert state.response.status == "abstained" and state.route == "abstain"
