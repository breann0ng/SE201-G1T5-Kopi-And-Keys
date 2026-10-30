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
