"""Importer (scripts/build_resale_db.py) and SQLite price adapter tests."""

import csv
import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from kopi_keys.advisor import DemoAdvisor
from kopi_keys.schemas import ChatRequest, PriceFilters
from kopi_keys.tools.policy import DemoPolicyRetriever
from kopi_keys.tools.price import (
    NoMatchingTransactionsError, SqlitePriceTool, ToolUnavailableError,
)
from kopi_keys.workflow import build_workflow, run_request

_spec = importlib.util.spec_from_file_location(
    "build_resale_db", Path(__file__).resolve().parents[1] / "scripts/build_resale_db.py",
)
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)

TODAY = date(2026, 10, 13)
GOOD = {
    "month": "2025-01", "town": "TAMPINES", "flat_type": "4 ROOM", "block": "101",
    "street_name": "TAMPINES ST 11", "storey_range": "04 TO 06", "floor_area_sqm": "92",
    "flat_model": "Model A", "lease_commence_date": "1985", "remaining_lease": "59 years 03 months",
    "resale_price": "500000",
}


def row(**changes):
    return {**GOOD, **changes}


def write_csv(path: Path, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build(tmp_path, rows, **kwargs):
    csv_path = write_csv(tmp_path / "resale.csv", rows)
    db_path = tmp_path / "resale.db"
    return importer.build(csv_path, db_path, today=TODAY, **kwargs), db_path


# --- lease parsing ---------------------------------------------------------

@pytest.mark.parametrize("text, months", [
    ("61 years 04 months", 736), ("60 years 1 month", 721), ("63 years", 756), ("1 year", 12),
])
def test_lease_months_parses_all_source_formats(text, months):
    assert importer.lease_months(text) == months


@pytest.mark.parametrize("text", ["", "61", "61 yrs", "61 years 12 months", "years 4 months"])
def test_lease_months_rejects_malformed_text(text):
    with pytest.raises(ValueError):
        importer.lease_months(text)


# --- end-to-end build, duplicates and metadata ------------------------------

def test_build_writes_rows_metadata_and_keeps_counted_duplicates(tmp_path):
    rows = [row(), row(), row(month="2025-03", resale_price="600000", remaining_lease="59 years")]
    meta, db_path = build(tmp_path, rows, downloaded_on=date(2026, 10, 12))
    assert meta["row_count"] == 3
    assert meta["duplicate_rows"] == 1
    with closing_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 3
        assert conn.execute("PRAGMA user_version").fetchone()[0] == importer.SCHEMA_VERSION
        stored = dict(zip(
            [c[0] for c in conn.execute("SELECT * FROM import_metadata").description],
            conn.execute("SELECT * FROM import_metadata").fetchone(),
        ))
        leases = [r[0] for r in conn.execute(
            "SELECT remaining_lease_months FROM transactions ORDER BY id")]
    assert leases == [711, 711, 708]
    assert stored["min_month"] == "2025-01" and stored["max_month"] == "2025-03"
    assert stored["downloaded_on"] == "2026-10-12"
    assert stored["dataset_id"] == importer.DEFAULT_DATASET_ID
    assert stored["source_url"].startswith("https://data.gov.sg/")
    assert len(stored["source_sha256"]) == 64
    assert stored["schema_version"] == importer.SCHEMA_VERSION


def test_lowercase_town_and_flat_type_are_normalised(tmp_path):
    _, db_path = build(tmp_path, [row(town="tampines", flat_type="4 room")])
    with closing_db(db_path) as conn:
        assert conn.execute("SELECT town, flat_type FROM transactions").fetchone() == ("TAMPINES", "4 ROOM")


# --- strict validation -------------------------------------------------------

@pytest.mark.parametrize("field, value", [
    ("resale_price", "NaN"), ("resale_price", "inf"), ("resale_price", "-500000"),
    ("resale_price", "5"), ("resale_price", "abc"), ("floor_area_sqm", "0"),
    ("floor_area_sqm", "nan"), ("month", "2025-13"), ("month", "25-01"),
    ("month", "2027-01"), ("lease_commence_date", "1985.5"), ("lease_commence_date", "2030"),
    ("remaining_lease", "120 years"), ("remaining_lease", "soon"),
    ("town", "ATLANTIS"), ("flat_type", "9 ROOM"), ("storey_range", "4-6"), ("block", ""),
])
def test_invalid_values_reject_the_whole_import(tmp_path, field, value):
    with pytest.raises(importer.DataValidationError, match="line 3"):
        build(tmp_path, [row(), row(**{field: value})])
    assert not (tmp_path / "resale.db").exists()
    assert not (tmp_path / "resale.db.tmp").exists()


def test_missing_columns_are_rejected(tmp_path):
    path = tmp_path / "resale.csv"
    path.write_text("month,town\n2025-01,TAMPINES\n", encoding="utf-8")
    with pytest.raises(importer.DataValidationError, match="missing columns"):
        importer.build(path, tmp_path / "resale.db", today=TODAY)


def test_empty_file_is_rejected(tmp_path):
    with pytest.raises(importer.DataValidationError, match="no data rows"):
        build(tmp_path, [])


# --- atomic replacement ------------------------------------------------------

def test_failed_rebuild_keeps_the_existing_database(tmp_path):
    _, db_path = build(tmp_path, [row(), row(month="2025-02")])
    with pytest.raises(importer.DataValidationError):
        build(tmp_path, [row(resale_price="NaN")])
    with closing_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    assert not (tmp_path / "resale.db.tmp").exists()


def test_successful_rebuild_replaces_the_database(tmp_path):
    build(tmp_path, [row(), row(month="2025-02")])
    _, db_path = build(tmp_path, [row()])
    with closing_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1


# --- SQLite price adapter ----------------------------------------------------

FILTERS = PriceFilters(town="TAMPINES", flat_type="4 ROOM", start_month="2025-01", end_month="2025-03")


@pytest.fixture
def price_db(tmp_path):
    _, db_path = build(tmp_path, [
        row(month="2025-01", resale_price="400000"),
        row(month="2025-02", resale_price="500000"),
        row(month="2025-03", resale_price="700000"),
        row(month="2025-04", resale_price="999999"),             # outside range
        row(flat_type="5 ROOM", resale_price="800000"),          # other flat type
        row(town="BEDOK", resale_price="300000"),                # other town
    ])
    return db_path


def test_price_tool_returns_statistics_for_matching_rows_only(price_db):
    result = SqlitePriceTool(price_db).query(FILTERS)
    assert (result.count, result.minimum, result.median, result.maximum) == (3, 400000, 500000, 700000)
    assert result.filters == FILTERS


def test_price_query_id_is_reproducible_and_filter_specific(price_db):
    tool = SqlitePriceTool(price_db)
    first = tool.query(FILTERS).query_id
    assert first.startswith("price-")
    assert tool.query(FILTERS).query_id == first
    lower = FILTERS.model_copy(update={"town": "tampines", "flat_type": "4 room"})
    assert tool.query(lower).query_id == first
    assert tool.query(lower).filters == lower  # echoed as requested for the verifier
    narrower = FILTERS.model_copy(update={"end_month": "2025-02"})
    assert tool.query(narrower).query_id != first


def test_price_tool_reports_no_matches(price_db):
    with pytest.raises(NoMatchingTransactionsError):
        SqlitePriceTool(price_db).query(FILTERS.model_copy(update={"town": "YISHUN"}))


def test_price_tool_reports_missing_database(tmp_path):
    with pytest.raises(ToolUnavailableError, match="not been built"):
        SqlitePriceTool(tmp_path / "missing.db").query(FILTERS)


def test_price_tool_opens_the_database_read_only(price_db):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with closing_db_ro(price_db) as conn:
            conn.execute("DELETE FROM transactions")


def test_workflow_answers_from_the_database_and_abstains_on_no_match(price_db):
    graph = build_workflow(DemoAdvisor(), DemoPolicyRetriever(), SqlitePriceTool(price_db))
    result = run_request(graph, ChatRequest(message="What are resale prices?", price_filters=FILTERS))
    assert result.status == "answered"
    assert "median SGD 500,000.00" in result.message
    assert result.price_result.query_id in result.message
    empty = FILTERS.model_copy(update={"town": "YISHUN"})
    result = run_request(graph, ChatRequest(message="What are resale prices?", price_filters=empty))
    assert result.status == "abstained"
    assert "No resale transactions match" in result.message


# --- helpers -----------------------------------------------------------------

def closing_db(path):
    from contextlib import closing
    return closing(sqlite3.connect(path))


def closing_db_ro(path):
    from contextlib import closing
    return closing(SqlitePriceTool(path)._connect())
