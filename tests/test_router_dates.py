"""The router reads the period a price question names (query_router.extract_month_range)."""
from datetime import date

import pytest

from kopi_keys.components.query_router import extract_month_range, route_query

TODAY = date(2026, 10, 18)


@pytest.mark.parametrize("question, expected", [
    ("What did 4-room flats in Tampines sell for in 2012?", ("2012-01", "2012-12")),
    ("How much did 5-room flats in Punggol sell for in 2025?", ("2025-01", "2025-12")),
    ("What are 3-room flats in Bedok going for in the last half of 2025?", ("2025-07", "2025-12")),
    ("first half of 2025", ("2025-01", "2025-06")),
    ("median 3-room price in Jurong West in 2026 so far", ("2026-01", "2026-10")),
    ("Median price of 4-room flats in Queenstown from January to June 2026?", ("2026-01", "2026-06")),
    ("4-room in AMK this year", ("2026-01", "2026-10")),
    ("4-room in AMK last year", ("2025-01", "2025-12")),
    ("median 4-room price in Tampines over the past 6 months", ("2026-05", "2026-10")),
    ("executive flats sold in Woodlands in the past year", None),   # default window
    ("4-room flats in Tampines, what are they going for these days?", None),
])
def test_periods_named_in_price_questions(question, expected):
    assert extract_month_range(question, TODAY) == expected


def test_router_passes_the_period_to_the_price_tool():
    routed = route_query("How much did 5-room flats in Punggol sell for in 2025?")
    assert (routed.start_month, routed.end_month) == ("2025-01", "2025-12")


def test_explicit_filters_are_kept_when_the_question_names_no_period():
    routed = route_query("What are 4-room flats in Tampines going for?",
                         {"start_month": "2024-01", "end_month": "2024-06"})
    assert (routed.start_month, routed.end_month) == ("2024-01", "2024-06")
