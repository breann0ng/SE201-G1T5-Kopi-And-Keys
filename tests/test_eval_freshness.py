"""The live freshness check: relative periods on the real date, data coverage and source age."""
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from kopi_keys.components.price_query import SqlitePriceTool
from kopi_keys.evaluation import freshness

TOWNS = ["TAMPINES", "QUEENSTOWN", "ANG MO KIO", "PUNGGOL", "JURONG WEST", "BEDOK"]
TYPES = ["3 ROOM", "4 ROOM", "5 ROOM"]


def months(start: str, end: str) -> list[str]:
    return [freshness.ym_of(i) for i in range(freshness.month_index(start), freshness.month_index(end) + 1)]


@pytest.fixture
def tool(tmp_path):
    """A tiny resale database: two sales per town, flat type and month, Jan 2024 to Oct 2026."""
    db = tmp_path / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE import_metadata (source_url, downloaded_on, min_month, max_month, "
                 "row_count, source_sha256)")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, month, town, flat_type, block, "
                 "street_name, storey_range, floor_area_sqm, remaining_lease, remaining_lease_months, "
                 "resale_price)")
    rows = [(m, t, ft, "1", "X ST", "04 TO 06", 90.0, "70 years", 840, price)
            for m in months("2024-01", "2026-10") for t in TOWNS for ft in TYPES
            for price in (500000.0 + int(m[5:]) * 1000, 510500.0)]
    conn.executemany("INSERT INTO transactions (month, town, flat_type, block, street_name, storey_range, "
                     "floor_area_sqm, remaining_lease, remaining_lease_months, resale_price) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO import_metadata VALUES ('https://example.invalid', '2026-10-14', "
                 "'2024-01', '2026-10', ?, 'abc')", (len(rows),))
    conn.commit()
    conn.close()
    return SqlitePriceTool(db)


@pytest.mark.parametrize("question, today, expected", [
    ("prices in the past 6 months", date(2026, 11, 9), ("2026-06", "2026-11")),
    ("prices in the last 3 months", date(2027, 1, 5), ("2026-11", "2027-01")),  # year boundary
    ("prices this year", date(2026, 11, 9), ("2026-01", "2026-11")),
    ("prices last year", date(2027, 1, 5), ("2026-01", "2026-12")),
    ("prices in 2025", date(2026, 11, 9), ("2025-01", "2025-12")),
    ("prices in 2026", date(2026, 11, 9), ("2026-01", "2026-11")),
    ("how much is a 4-room", date(2026, 11, 9), ("2025-11", "2026-10")),  # default: newest data
])
def test_intended_window_reads_the_phrase_on_the_given_day(question, today, expected):
    assert freshness.intended_window(question, today, "2026-10") == expected


def test_sql_median_is_the_textbook_median(tool):
    volume, median = freshness.sql_figures(tool.db_path, "BEDOK", "4 ROOM", "2026-10", "2026-10")
    assert (volume, median) == (2, Decimal("510250.00"))  # mean of 510000 and 510500
    assert freshness.sql_figures(tool.db_path, "BEDOK", "4 ROOM", "2030-01", "2030-12") == (0, None)


CUT_SHORT = {"past-6-months", "past-3-months", "this-year", "in-current-year"}


def test_periods_past_the_data_are_cut_to_it_and_say_so(tool):
    # 9 Nov with data to Oct: "past 6 months" is asked as Jun-Nov, queried Jun-Oct (#29),
    # and the answer names the missing month.
    report = freshness.check(date(2026, 11, 9), tool=tool, snapshot="2026-10-15")
    by_id = {r["id"]: r for r in report["probes"]}
    assert report["ok"], report
    assert by_id["past-6-months"]["asked"] == ("2026-06", "2026-11")
    assert by_id["past-6-months"]["app"] == ("2026-06", "2026-10")
    assert {i for i, r in by_id.items() if r["disclosure"]} == CUT_SHORT
    assert "Nov 2026" in by_id["past-6-months"]["disclosure"]
    assert by_id["default"]["app"] == ("2025-11", "2026-10") and by_id["default"]["disclosure"] is None


def test_fails_when_a_cut_short_period_is_not_disclosed(tool, monkeypatch):
    from kopi_keys.components import price_display
    monkeypatch.setattr(price_display, "missing_months_note", lambda filters, requested_end: None)
    report = freshness.check(date(2026, 11, 9), tool=tool, snapshot="2026-10-15")
    assert not report["ok"]
    assert {r["id"] for r in report["probes"] if not r["covered"]} == CUT_SHORT


def test_fails_when_the_queried_period_runs_past_the_data(tool, monkeypatch):
    # The behaviour before #29: the period was queried and labelled up to November.
    from kopi_keys.components import price_query
    original = price_query.filters_from_state
    def no_cut(state, today=None, latest_month=None):
        f = original(state, today, latest_month)
        return f.model_copy(update={"end_month": state.end_month or f.end_month})
    monkeypatch.setattr(price_query, "filters_from_state", no_cut)
    report = freshness.check(date(2026, 11, 9), tool=tool, snapshot="2026-10-15")
    assert {r["id"] for r in report["probes"] if not r["covered"]} == CUT_SHORT


def test_passes_when_today_is_inside_the_data(tool):
    report = freshness.check(date(2026, 10, 20), tool=tool, snapshot="2026-10-15")
    assert report["ok"], report
    assert report["sources"]["price_data"]["lag_months"] == 0


def test_flags_stale_price_data_and_old_policy_snapshot(tool):
    report = freshness.check(date(2027, 3, 1), tool=tool, snapshot="2026-10-15")
    assert report["sources"]["price_data"] == {
        "newest_month": "2026-10", "downloaded_on": "2026-10-14", "lag_months": 5, "ok": False}
    assert report["sources"]["policy_snapshot"]["age_days"] == 137
    assert not report["sources"]["policy_snapshot"]["ok"]
    # "last 3 months" is wholly after the data: the app declines (no figures), no crash
    past3 = next(r for r in report["probes"] if r["id"] == "past-3-months")
    assert past3["asked"] == ("2027-01", "2027-03") and past3["volume"] == 0 and "note" in past3


def test_thresholds_are_inclusive(tool):
    report = freshness.check(date(2026, 12, 1), tool=tool, snapshot="2026-10-17",
                             max_data_lag=2, max_policy_age=45)
    assert report["sources"]["price_data"]["ok"] and report["sources"]["policy_snapshot"]["ok"]
