from decimal import Decimal

from kopi_keys.midpoint.contracts import SQLPriceResult
from kopi_keys.midpoint.engine import Generation
from kopi_keys.midpoint.pipeline import build_price_summary_graph
from kopi_keys.orchestration.graph import build_stage1_graph
from kopi_keys.schemas import PriceFilters


VALID_TEXT = """Mean: SGD 650,000.13
Median: SGD 640,000.00
IQR: SGD 80,000.00
Range: SGD 500,000.00 to SGD 780,000.00
Volume: 42 transactions"""


class FixtureEngine:
    def complete(self, messages):
        return Generation(text=VALID_TEXT, model="test-fixture")


def test_stage1_invokes_stage3_and_stage4_with_synthetic_stage2_result():
    filters = PriceFilters(
        town="TAMPINES",
        flat_type="4 ROOM",
        start_month="2025-01",
        end_month="2025-12",
    )
    sql_result = SQLPriceResult(
        query_id="synthetic-stage2-1",
        filters=filters,
        volume=42,
        mean=Decimal("650000.13"),
        median=Decimal("640000.00"),
        iqr=Decimal("80000.00"),
        minimum=Decimal("500000.00"),
        maximum=Decimal("780000.00"),
    )

    def fake_stage2_query(state):
        assert state.route == "price"
        assert state.town == "TAMPINES"
        assert state.flat_type == "4 ROOM"
        return sql_result

    midpoint_graph = build_price_summary_graph(FixtureEngine())
    graph = build_stage1_graph(
        sql_provider=fake_stage2_query,
        midpoint_graph=midpoint_graph,
    )
    result = graph.invoke({
        "message": "What is the resale price for a 4-room flat in Tampines?",
    })

    assert result["route"] == "price"
    assert result["sql_result"].query_id == "synthetic-stage2-1"
    assert result["midpoint_status"] == "answered"
    assert result["verification_passed"] is True
    assert "synthetic-stage2-1" in result["final_response"]
    assert "640,000.00" in result["final_response"]
