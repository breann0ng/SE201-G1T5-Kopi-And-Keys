"""A period that runs past the data keeps the user's dates and says which months are missing.

Asked on 8 Nov 2026 with sales data to Oct 2026, "past 6 months" means Jun to Nov 2026.
The figures cover Jun to Oct 2026, and the answer says there is no Nov 2026 data yet.
"""

import csv
import json
from datetime import date
from types import SimpleNamespace

import pytest

from fakes import FictionalRetriever
from kopi_keys.components import query_router
from kopi_keys.components.price_query import PriceOutOfRangeError, SqlitePriceTool, filters_from_state
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.ingest import resale_db as importer
from kopi_keys.llm import Generation
from kopi_keys.schemas import ChatRequest

ROW = {
    "month": "2026-10", "town": "QUEENSTOWN", "flat_type": "3 ROOM", "block": "1",
    "street_name": "QUEENSWAY", "storey_range": "04 TO 06", "floor_area_sqm": "67",
    "flat_model": "Improved", "lease_commence_date": "1975", "remaining_lease": "48 years 01 month",
    "resale_price": "400000",
}


class CalendarIsNovember(date):
    """The real date when the problem was found: one month after the newest data."""

    @classmethod
    def today(cls):
        return cls(2026, 11, 8)


class CopyingEngine:
    """A stand-in model that copies the verified display values exactly, as instructed."""

    def complete(self, messages):
        v = json.loads(messages[-1]["content"])["display_values"]
        text = (f"Mean: SGD {v['mean']}\nMedian: SGD {v['median']}\nIQR: SGD {v['iqr']}\n"
                f"Range: SGD {v['minimum']} to SGD {v['maximum']}\nVolume: {v['volume']} transactions")
        return Generation(text=text, model="test-fixture")


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setattr(query_router, "date", CalendarIsNovember)
    rows = [{**ROW, "month": m} for m in ("2026-05", "2026-06", "2026-06", "2026-08", "2026-08", "2026-10", "2026-10")]
    csv_path = tmp_path / "resale.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    importer.build(csv_path, tmp_path / "db.sqlite", today=date(2026, 10, 15), downloaded_on=date(2026, 10, 15))
    return build_graph(retriever=FictionalRetriever(), price_tool=SqlitePriceTool(tmp_path / "db.sqlite"),
                       synthesiser=Synthesiser(engine=CopyingEngine()), cards=[])


def test_past_six_months_keeps_the_users_start_and_ends_at_the_data(graph):
    state = run_graph(graph, ChatRequest(message="3-room prices in Queenstown in the past 6 months"))
    assert "query_router:price" in state.trace
    filters = state.price_result.filters
    assert (filters.start_month, filters.end_month) == ("2026-06", "2026-10")  # Jun to Nov asked; data to Oct
    assert (state.start_month, state.end_month) == ("2026-06", "2026-10")  # the months actually used
    assert state.price_result.volume == 6  # Jun, Aug and Oct; May is before the asked period
    assert state.verification_passed


def test_the_answer_says_november_is_not_in_the_data_yet(graph):
    state = run_graph(graph, ChatRequest(message="3-room prices in Queenstown in the past 6 months"))
    assert state.response.status == "answered"
    message = state.response.message
    assert "(Jun 2026 to Oct 2026, 6 sales)" in message
    assert ("We don't have sales data for Nov 2026 yet: our records go up to Oct 2026, "
            "so these figures cover Jun 2026 to Oct 2026.") in message


def test_a_past_period_has_no_missing_months_note(graph):
    state = run_graph(graph, ChatRequest(message="3-room prices in Queenstown from May to Aug 2026"))
    assert state.response.status == "answered"
    assert "(May 2026 to Aug 2026, 5 sales)" in state.response.message
    assert "We don't have sales data" not in state.response.message


def test_this_year_ends_at_the_data(graph):
    state = run_graph(graph, ChatRequest(message="3-room prices in Queenstown this year"))
    assert (state.price_result.filters.start_month, state.price_result.filters.end_month) == ("2026-01", "2026-10")


def test_future_years_still_decline_with_the_plain_english_message(graph):
    state = run_graph(graph, ChatRequest(message="What were 3-room flats in Queenstown selling for in 2028?"))
    assert state.abstain_reason == "price_out_of_range"
    assert "no sales for Jan 2028 onwards" in state.response.message


def _state(start, end):
    return SimpleNamespace(town="QUEENSTOWN", flat_type="3 ROOM", start_month=start, end_month=end)


@pytest.mark.parametrize("start, end, expected", [
    ("2026-06", "2026-11", ("2026-06", "2026-10")),  # runs past the data: cut at Oct
    ("2026-01", "2026-10", ("2026-01", "2026-10")),  # ends exactly at the data: unchanged
    ("2023-01", "2023-12", ("2023-01", "2023-12")),  # a past period: unchanged
])
def test_filters_end_at_the_newest_data_month(start, end, expected):
    filters = filters_from_state(_state(start, end), latest_month="2026-10")
    assert (filters.start_month, filters.end_month) == expected


def test_filters_without_coverage_information_keep_the_period():
    filters = filters_from_state(_state("2026-06", "2026-11"))
    assert (filters.start_month, filters.end_month) == ("2026-06", "2026-11")


def test_a_period_starting_after_the_data_still_declines():
    with pytest.raises(PriceOutOfRangeError):
        filters_from_state(_state("2026-11", "2026-11"), latest_month="2026-10")
