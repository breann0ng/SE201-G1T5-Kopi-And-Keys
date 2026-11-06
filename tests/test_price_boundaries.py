"""Exact boundaries and messages of the price tool, added to kill surviving mutants.

See docs/testing-price-tool.md. Every expected value is a literal worked out by hand in the
comments, never by calling the code under test. Some edges (storey 06/12/99, a 0- or 99-year
lease) are not in the 2017+ snapshot, where lower storeys are 01, 04, 07, ... and leases start
at 39 years, but the importer accepts them, so the bands must still place them correctly.
"""

import csv
import dataclasses
import hashlib
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import kopi_keys
from kopi_keys.components.price_query import (
    InvalidPriceFilterError, PriceOutOfRangeError, SqlitePriceTool, ToolUnavailableError,
    UnconfiguredPriceTool, filters_from_state, is_low_volume,
)
from kopi_keys.ingest import resale_db as importer
from kopi_keys.schemas import PriceFilters, PriceResult

BASE = {
    "month": "2026-01", "town": "TOA PAYOH", "flat_type": "5 ROOM", "block": "1",
    "street_name": "LOR 1 TOA PAYOH", "storey_range": "04 TO 06", "floor_area_sqm": "120",
    "flat_model": "Improved", "lease_commence_date": "1990", "remaining_lease": "70 years",
    "resale_price": "500000",
}
# Toa Payoh 5-room: one sale per month, Jan..Jun 2026, all on storey 04 (low).
# remaining lease -> months: 0, 59*12+11 = 719, 60*12 = 720, 79*12+11 = 959, 80*12 = 960, 99*12 = 1188
LEASE_SALES = [
    ("2026-01", "0 years", "300000"),             # under_60 (lowest possible lease)
    ("2026-02", "59 years 11 months", "400000"),  # under_60 (719 < 720)
    ("2026-03", "60 years", "500000"),            # 60_79   (720 is the band's first month)
    ("2026-04", "79 years 11 months", "600000"),  # 60_79   (959 < 960)
    ("2026-05", "80 years", "700000"),            # 80_plus (960 is the band's first month)
    ("2026-06", "99 years", "900000"),            # 80_plus (1188, the importer's maximum)
]
# Bedok 4-room, Mar 2026, lease 70 years: lower storey 01 and 06 low, 07 and 12 mid, 13 and 99 high.
STOREY_SALES = [
    ("01 TO 03", "410000"), ("06 TO 08", "430000"),
    ("07 TO 09", "450000"), ("12 TO 14", "470000"),
    ("13 TO 15", "490000"), ("99 TO 99", "510000"),
]
OTHER_ROWS = [
    {"town": "TAMPINES", "flat_type": "4 ROOM", "month": "2026-02"},
    {"town": "YISHUN", "flat_type": "MULTI-GENERATION", "month": "2026-04", "resale_price": "880000"},
    {"town": "YISHUN", "flat_type": "2 ROOM", "month": "2026-04", "resale_price": "250000"},
    {"town": "YISHUN", "flat_type": "3 ROOM", "month": "2026-04", "resale_price": "350000"},
]
TOA_PAYOH = PriceFilters(town="TOA PAYOH", flat_type="5 ROOM", start_month="2026-01", end_month="2026-06")
BEDOK = PriceFilters(town="BEDOK", flat_type="4 ROOM", start_month="2026-01", end_month="2026-06")


def _rows():
    rows = [{**BASE, "month": m, "remaining_lease": lease, "resale_price": price, "block": str(i)}
            for i, (m, lease, price) in enumerate(LEASE_SALES, start=1)]
    rows += [{**BASE, "town": "BEDOK", "flat_type": "4 ROOM", "month": "2026-03", "street_name": "BEDOK NTH RD",
              "storey_range": storey, "resale_price": price} for storey, price in STOREY_SALES]
    rows += [{**BASE, **extra} for extra in OTHER_ROWS]
    return rows


@pytest.fixture
def built(tmp_path):
    csv_path = tmp_path / "resale.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_rows())
    db_path = tmp_path / "db.sqlite"
    importer.build(csv_path, db_path, today=date(2026, 10, 15), downloaded_on=date(2026, 10, 15))
    return SqlitePriceTool(db_path), csv_path, db_path


@pytest.fixture
def tool(built):
    return built[0]


def band(result, dimension, name):
    return next(b for b in result.breakdown if b.dimension == dimension and b.band == name)


# --- lease bands: [0, 720), [720, 960), [960, 1200) months ------------------

def test_lease_bands_at_exactly_60_and_80_years(tool):
    result = tool.query(TOA_PAYOH)
    # under_60: 300k, 400k -> median (300k + 400k) / 2 = 350k
    # 60_79:    500k, 600k -> 550k;  80_plus: 700k, 900k -> 800k
    assert [(band(result, "lease", b).volume, band(result, "lease", b).median)
            for b in ("under_60", "60_79", "80_plus")] == [
        (2, Decimal("350000.00")), (2, Decimal("550000.00")), (2, Decimal("800000.00"))]


@pytest.mark.parametrize("lease_band, months", [
    ("under_60", ["2026-02", "2026-01"]), ("60_79", ["2026-04", "2026-03"]), ("80_plus", ["2026-06", "2026-05"]),
])
def test_each_lease_band_filter_selects_its_two_sales(tool, lease_band, months):
    result = tool.query(TOA_PAYOH.model_copy(update={"lease_band": lease_band}))
    assert result.volume == 2 and [s.month for s in result.recent_sales] == months


# --- floor bands: 1-6, 7-12, 13-99 by lower storey, inclusive ----------------

def test_floor_bands_at_storey_6_7_12_13_and_99(tool):
    result = tool.query(BEDOK)
    # low: 01 (410k), 06 (430k) -> 420k | mid: 07 (450k), 12 (470k) -> 460k | high: 13 (490k), 99 (510k) -> 500k
    assert [(band(result, "storey", b).volume, band(result, "storey", b).median)
            for b in ("low", "mid", "high")] == [
        (2, Decimal("420000.00")), (2, Decimal("460000.00")), (2, Decimal("500000.00"))]


# --- recent sales -------------------------------------------------------------

def test_recent_sales_are_the_five_newest_with_every_field(tool):
    result = tool.query(TOA_PAYOH)
    assert result.volume == 6
    assert [s.month for s in result.recent_sales] == ["2026-06", "2026-05", "2026-04", "2026-03", "2026-02"]
    newest = result.recent_sales[0]
    assert (newest.block, newest.street_name, newest.storey_range, newest.floor_area_sqm,
            newest.remaining_lease, newest.resale_price) == (
        "6", "LOR 1 TOA PAYOH", "04 TO 06", Decimal("120"), "99 years", Decimal("900000"))


# --- thin-sample flag: 1..9 sales -------------------------------------------

def _result(volume):
    stats = {} if volume == 0 else dict(mean=1, median=1, iqr=0, minimum=1, maximum=1)
    return PriceResult(query_id="x", filters=TOA_PAYOH, volume=volume, **stats)


@pytest.mark.parametrize("volume, low", [(0, False), (1, True), (9, True), (10, False)])
def test_low_volume_flag_is_one_to_nine_sales(volume, low):
    assert is_low_volume(_result(volume)) is low


# --- query ID ---------------------------------------------------------------

def test_query_id_is_the_documented_hash(built):
    tool, csv_path, _ = built
    source = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    fingerprint = ('{"bands": [null, null], "params": ["TOA PAYOH", "5 ROOM", "2026-01", "2026-06"], '
                   f'"source": "{source}", "version": "price-v3"}}')
    expected = "price-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
    assert tool.query(TOA_PAYOH).query_id == expected


# --- normalisation and messages ---------------------------------------------

def test_hyphenated_and_multi_generation_flat_types_are_normalised(tool):
    assert tool.query(TOA_PAYOH.model_copy(update={"flat_type": "5-room"})).filters.flat_type == "5 ROOM"
    multi = tool.query(PriceFilters(town="yishun", flat_type="Multi-Generation",
                                    start_month="2026-01", end_month="2026-06"))
    assert (multi.filters.flat_type, multi.volume, multi.median) == ("MULTI-GENERATION", 1, Decimal("880000.00"))


@pytest.mark.parametrize("town, flat_type, message", [
    ("TAMPINESS", "4 ROOM", "Unknown town 'TAMPINESS'. Did you mean: TAMPINES?"),
    ("TAMPINES", "PENTHOUSE", "Unknown flat type 'PENTHOUSE'."),
    # '6 ROOM' differs from each 'N ROOM' by one character, so all tie; the 3 kept are the
    # alphabetically last (difflib breaks ties in reverse order). 2 ROOM is the 4th and is dropped.
    ("TAMPINES", "6 ROOM", "Unknown flat type '6 ROOM'. Did you mean: 5 ROOM, 4 ROOM, 3 ROOM?"),
])
def test_unknown_value_messages(tool, town, flat_type, message):
    with pytest.raises(InvalidPriceFilterError) as error:
        tool.query(TOA_PAYOH.model_copy(update={"town": town, "flat_type": flat_type}))
    assert str(error.value) == message


def test_outside_dataset_message_and_the_last_month_is_inside(tool):
    with pytest.raises(InvalidPriceFilterError) as error:
        tool.query(TOA_PAYOH.model_copy(update={"start_month": "2019-01", "end_month": "2019-12"}))
    assert str(error.value) == "2019-01 to 2019-12 is outside the dataset, which covers 2026-01 to 2026-06."
    last = tool.query(TOA_PAYOH.model_copy(update={"start_month": "2026-06", "end_month": "2026-06"}))
    assert last.volume == 1


def test_unconfigured_and_missing_database_messages(tmp_path, monkeypatch):
    with pytest.raises(ToolUnavailableError) as error:
        UnconfiguredPriceTool().query(TOA_PAYOH)
    assert str(error.value) == "Official resale transactions and the SQLite adapter are not connected yet."
    with pytest.raises(ToolUnavailableError) as error:
        SqlitePriceTool(tmp_path / "missing.db").info()
    assert str(error.value) == "The resale database has not been built. Run scripts/build_resale_db.py."


def test_unreadable_database_message_from_info_and_from_query(built, tmp_path):
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"this is not a database" * 100)
    with pytest.raises(ToolUnavailableError) as error:
        SqlitePriceTool(garbage).info()
    assert str(error.value) == "The resale database could not be read: file is not a database"
    tool, _, db_path = built
    tool.info()  # cached, so query() reaches its own read
    db_path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(ToolUnavailableError) as error:
        tool.query(TOA_PAYOH)
    assert str(error.value) == "The resale database could not be read: file is not a database"


def test_missing_metadata_message_from_info_and_from_query(built):
    tool, _, db_path = built
    tool.info()  # cached before the metadata disappears
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM import_metadata")
    message = "The resale database has no import metadata; rebuild it."
    with pytest.raises(ToolUnavailableError) as error:
        tool.query(TOA_PAYOH)
    assert str(error.value) == message
    with pytest.raises(ToolUnavailableError) as error:
        SqlitePriceTool(db_path).info()
    assert str(error.value) == message


def test_dataset_info_cannot_be_changed_by_callers(tool):
    # info() is cached and shared, so it must be immutable.
    with pytest.raises(dataclasses.FrozenInstanceError):
        tool.info().max_month = "2099-12"


# --- database location ------------------------------------------------------

def test_database_path_defaults_to_data_processed_and_honours_the_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("KOPI_RESALE_DB", raising=False)
    repo = Path(kopi_keys.__file__).resolve().parent.parent.parent  # backend/kopi_keys -> repo root
    assert SqlitePriceTool().db_path == repo / "data" / "processed" / "hdb_prices.db"
    monkeypatch.setenv("KOPI_RESALE_DB", str(tmp_path / "other.db"))
    assert SqlitePriceTool().db_path == tmp_path / "other.db"


# --- filters_from_state edges -----------------------------------------------

def state(start, end, **extra):
    return SimpleNamespace(town="TAMPINES", flat_type="4 ROOM", start_month=start, end_month=end, **extra)


def test_bands_from_the_router_reach_the_filters():
    filters = filters_from_state(state("2025-01", "2025-06", lease_band="80_plus", storey_band="high"),
                                 latest_month="2026-10")
    assert (filters.lease_band, filters.storey_band) == ("80_plus", "high")


def test_the_latest_month_and_jan_2017_are_inside_the_data():
    assert filters_from_state(state("2026-10", "2026-10"), latest_month="2026-10").start_month == "2026-10"
    assert filters_from_state(state("2017-01", "2017-01"), latest_month="2026-10").end_month == "2017-01"


def test_a_one_month_period_with_a_missing_town_is_not_called_a_future_period():
    bad = SimpleNamespace(town=None, flat_type="4 ROOM", start_month="2025-03", end_month="2025-03")
    with pytest.raises(InvalidPriceFilterError) as error:
        filters_from_state(bad, latest_month="2026-10")
    assert type(error.value) is InvalidPriceFilterError
    assert str(error.value) == "I couldn't work out which sales to look up for this question."


def test_before_2017_message_without_a_known_latest_month():
    with pytest.raises(PriceOutOfRangeError) as error:
        filters_from_state(state("2012-01", "2012-12"))
    assert str(error.value) == "Our records cover sales from Jan 2017 onwards, so there are no sales before Jan 2017."
