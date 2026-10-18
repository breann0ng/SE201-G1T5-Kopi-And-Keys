"""Lease / floor refinements, band breakdown and recent sales from the price tool."""

import csv
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kopi_keys.components.price_display import lease_note, subject_label
from kopi_keys.components.price_query import SqlitePriceTool
from kopi_keys.schemas import ChatRequest, PriceFilters
from kopi_keys.ingest import resale_db as importer
from kopi_keys.state import initial_state

BASE = {
    "month": "2026-01", "town": "TOA PAYOH", "flat_type": "5 ROOM", "block": "1",
    "street_name": "LOR 1 TOA PAYOH", "storey_range": "04 TO 06", "floor_area_sqm": "120",
    "flat_model": "Improved", "lease_commence_date": "1975", "remaining_lease": "48 years 02 months",
    "resale_price": "600000",
}
# (month, remaining lease, storey, price): old flats ~600-700k, new flats ~1.4-1.5M.
SALES = [
    ("2026-01", "48 years 02 months", "01 TO 03", "600000"),
    ("2026-02", "55 years 01 month", "13 TO 15", "700000"),
    ("2026-03", "70 years", "07 TO 09", "950000"),
    ("2026-04", "79 years 11 months", "10 TO 12", "1000000"),
    ("2026-05", "80 years", "16 TO 18", "1400000"),      # 80 years exactly -> 80+ band
    ("2026-06", "92 years 03 months", "04 TO 06", "1300000"),
    ("2026-07", "94 years", "28 TO 30", "1500000"),
]
FILTERS = PriceFilters(town="TOA PAYOH", flat_type="5 ROOM", start_month="2026-01", end_month="2026-12")


@pytest.fixture
def tool(tmp_path):
    rows = [{**BASE, "month": m, "remaining_lease": lease, "storey_range": storey, "resale_price": price,
             "block": str(i)} for i, (m, lease, storey, price) in enumerate(SALES, start=1)]
    path = tmp_path / "resale.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    importer.build(path, tmp_path / "db.sqlite", today=date(2026, 10, 18))
    return SqlitePriceTool(tmp_path / "db.sqlite")


def band(result, dimension, name):
    return next(b for b in result.breakdown if b.dimension == dimension and b.band == name)


def test_lease_band_boundaries_and_breakdown(tool):
    result = tool.query(FILTERS)
    assert result.volume == 7
    assert (band(result, "lease", "under_60").volume, band(result, "lease", "60_79").volume,
            band(result, "lease", "80_plus").volume) == (2, 2, 3)
    assert band(result, "lease", "80_plus").median == Decimal("1400000.00")
    assert band(result, "lease", "under_60").median == Decimal("650000.00")


def test_floor_bands_use_the_lower_storey(tool):
    result = tool.query(FILTERS)
    # low 1-6: 01-03, 04-06 | mid 7-12: 07-09, 10-12 | high 13+: 13-15, 16-18, 28-30
    assert [band(result, "storey", b).volume for b in ("low", "mid", "high")] == [2, 2, 3]


def test_refined_query_uses_only_matching_sales_and_echoes_the_bands(tool):
    result = tool.query(FILTERS.model_copy(update={"lease_band": "80_plus", "storey_band": "high"}))
    assert result.volume == 2 and result.median == Decimal("1450000.00")
    assert (result.filters.lease_band, result.filters.storey_band) == ("80_plus", "high")
    # The lease breakdown is computed with the floor band applied, so the user can compare bands.
    assert band(result, "lease", "under_60").volume == 1
    assert result.query_id != tool.query(FILTERS).query_id


def test_recent_sales_are_the_newest_matches(tool):
    result = tool.query(FILTERS.model_copy(update={"lease_band": "80_plus"}))
    assert [s.month for s in result.recent_sales] == ["2026-07", "2026-06", "2026-05"]
    assert result.recent_sales[0].remaining_lease == "94 years" and result.recent_sales[0].storey_range == "28 TO 30"


def test_an_empty_band_returns_no_data_but_keeps_the_breakdown(tool):
    result = tool.query(FILTERS.model_copy(update={"lease_band": "60_79", "storey_band": "high"}))
    assert result.volume == 0 and result.median is None and result.recent_sales == []
    assert band(result, "lease", "80_plus").volume == 2


def test_unknown_bands_are_rejected():
    with pytest.raises(ValidationError):
        PriceFilters(town="X", flat_type="4 ROOM", start_month="2026-01", end_month="2026-01", lease_band="99_plus")


def test_request_bands_reach_the_graph_state():
    request = ChatRequest(message="prices", price_filters=FILTERS.model_copy(update={"storey_band": "mid"}))
    state = initial_state(request)
    assert state["storey_band"] == "mid" and "lease_band" not in state


def test_wording(tool):
    refined = FILTERS.model_copy(update={"lease_band": "80_plus", "storey_band": "high"})
    assert subject_label(refined) == "5-room flats in Toa Payoh with 80+ years of lease left, on high floors (13+)"
    note = lease_note(tool.query(FILTERS))
    assert note is None  # fewer than 5 sales per band in this tiny fixture
