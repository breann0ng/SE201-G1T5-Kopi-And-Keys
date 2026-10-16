"""SqlitePriceTool: statistics, validation and fit with the graph and verifier."""

import csv
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kopi_keys.components.policy_retrieval import DemoPolicyRetriever
from kopi_keys.components.price_query import (
    InvalidPriceFilterError, SqlitePriceTool, ToolUnavailableError, _cents, _quantile, is_low_volume,
)
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.components.verifier import verify_generated_numbers
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest, PriceFilters, PriceResult

_spec = importlib.util.spec_from_file_location(
    "build_resale_db", Path(__file__).resolve().parents[1] / "scripts/build_resale_db.py",
)
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)

BASE = {
    "month": "2025-01", "town": "TAMPINES", "flat_type": "4 ROOM", "block": "101",
    "street_name": "TAMPINES ST 11", "storey_range": "04 TO 06", "floor_area_sqm": "92",
    "flat_model": "Model A", "lease_commence_date": "1985", "remaining_lease": "59 years 03 months",
    "resale_price": "500000",
}
# Hand-checked: sorted 400k, 450k, 500k, 650k, 700k, 750k (n=6)
#   mean   = 3,450,000 / 6           = 575,000.00
#   median = (500k + 650k) / 2       = 575,000.00
#   Q1 pos = 5 * 0.25 = 1.25 -> 450k + 0.25 * 50k  = 462,500
#   Q3 pos = 5 * 0.75 = 3.75 -> 650k + 0.75 * 50k  = 687,500   -> IQR 225,000.00
PRICES = ["400000", "750000", "500000", "650000", "450000", "700000"]
FILTERS = PriceFilters(town="TAMPINES", flat_type="4 ROOM", start_month="2025-01", end_month="2025-06")


@pytest.fixture
def tool(tmp_path):
    rows = [{**BASE, "month": f"2025-0{i + 1}", "resale_price": p} for i, p in enumerate(PRICES)]
    rows += [
        {**BASE, "month": "2025-07", "resale_price": "999000"},          # outside range
        {**BASE, "flat_type": "5 ROOM", "resale_price": "820000"},       # other flat type
        {**BASE, "town": "BEDOK", "resale_price": "300000"},             # other town
        {**BASE, "town": "YISHUN", "flat_type": "3 ROOM", "resale_price": "350000"},
    ]
    csv_path = tmp_path / "resale.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    importer.build(csv_path, tmp_path / "db.sqlite", today=date(2026, 10, 15),
                   downloaded_on=date(2026, 10, 15))
    return SqlitePriceTool(tmp_path / "db.sqlite")


def test_stats_match_hand_calculation(tool):
    result = tool.query(FILTERS)
    assert isinstance(result, PriceResult)
    assert result.volume == 6
    assert result.mean == Decimal("575000.00")
    assert result.median == Decimal("575000.00")
    assert result.iqr == Decimal("225000.00")
    assert (result.minimum, result.maximum) == (Decimal("400000"), Decimal("750000"))
    assert result.filters == FILTERS


def test_quantile_matches_standard_library_inclusive_method():
    import statistics
    values = sorted(Decimal(v) for v in ["1", "2", "3", "4", "10", "11", "50"])
    q1, q2, q3 = statistics.quantiles([float(v) for v in values], n=4, method="inclusive")
    assert [float(_quantile(values, Decimal(f))) for f in ("0.25", "0.5", "0.75")] == [q1, q2, q3]


def test_mean_is_rounded_once_to_cents():
    # 3 prices summing to 1,000,001 -> mean 333,333.666... -> 333,333.67
    assert _cents(Decimal(1_000_001) / 3) == Decimal("333333.67")


def test_single_transaction_has_zero_iqr(tool):
    result = tool.query(FILTERS.model_copy(update={"start_month": "2025-01", "end_month": "2025-01"}))
    assert result.volume == 1 and result.iqr == 0 and result.mean == result.median == Decimal("400000.00")
    assert is_low_volume(result)


def test_zero_matches_return_volume_zero_for_the_no_data_path(tool):
    result = tool.query(PriceFilters(town="YISHUN", flat_type="4 ROOM",
                                     start_month="2025-01", end_month="2025-06"))
    assert result.volume == 0 and result.median is None and not is_low_volume(result)


def test_case_and_spacing_are_normalised(tool):
    loose = FILTERS.model_copy(update={"town": "  tampines ", "flat_type": "4  room"})
    result = tool.query(loose)
    assert result.query_id == tool.query(FILTERS).query_id
    assert (result.filters.town, result.filters.flat_type) == ("TAMPINES", "4 ROOM")
    assert str(result.minimum) == "400000"  # no trailing '.0' from the REAL column


@pytest.mark.parametrize("town, flat_type, hint", [
    ("TAMPINESS", "4 ROOM", "TAMPINES"),
    ("TAMPINES", "4 RM", None),
    ("TAMPINES' OR '1'='1", "4 ROOM", None),   # injection text is just an unknown town
])
def test_unknown_values_are_rejected_with_suggestions(tool, town, flat_type, hint):
    with pytest.raises(InvalidPriceFilterError) as error:
        tool.query(FILTERS.model_copy(update={"town": town, "flat_type": flat_type}))
    if hint:
        assert hint in str(error.value)


def test_dates_outside_dataset_coverage_are_rejected(tool):
    with pytest.raises(InvalidPriceFilterError, match="covers 2025-01 to 2025-07"):
        tool.query(FILTERS.model_copy(update={"start_month": "2019-01", "end_month": "2019-12"}))


def test_dataset_info_reports_provenance(tool):
    info = tool.info()
    assert info.downloaded_on == "2026-10-15" and info.row_count == 10
    assert "BEDOK" in info.towns and "5 ROOM" in info.flat_types


def test_missing_database_is_reported(tmp_path):
    with pytest.raises(ToolUnavailableError, match="not been built"):
        SqlitePriceTool(tmp_path / "missing.db").query(FILTERS)


def test_stage3_verifier_accepts_text_built_from_stage2_output(tool):
    """End-to-end contract check with Nisha's Stage 4 verifier, no model needed."""
    result = tool.query(FILTERS)
    shown = result.display_values()
    text = (f"Mean: SGD {shown['mean']}\nMedian: SGD {shown['median']}\nIQR: SGD {shown['iqr']}\n"
            f"Range: SGD {shown['minimum']} to SGD {shown['maximum']}\n"
            f"Volume: {shown['volume']} transactions")
    assert verify_generated_numbers(text, result).passed


# --- inside the graph --------------------------------------------------------

def _graph(tool):
    return build_graph(retriever=DemoPolicyRetriever(), price_tool=tool,
                       synthesiser=Synthesiser(engine=None), cards=[])


def test_graph_receives_database_statistics(tool):
    request = ChatRequest(message="What is the resale price for a 4-room flat in Tampines?",
                          price_filters=FILTERS)
    state = run_graph(_graph(tool), request)
    assert state.price_result is not None and state.price_result.volume == 6
    assert state.price_error is None


def test_graph_records_misspelt_town_as_price_error_instead_of_crashing(tool):
    request = ChatRequest(message="What is the resale price for a 4-room flat?",
                          price_filters=FILTERS.model_copy(update={"town": "TAMPINESS"}))
    state = run_graph(_graph(tool), request)
    assert state.price_result is None
    assert "Did you mean: TAMPINES" in state.price_error
