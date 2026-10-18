import json
from decimal import Decimal
from pathlib import Path

from kopi_keys.components.query_router import route_query


LABELS = Path(__file__).resolve().parents[1] / "data" / "evaluation-data" / "development" / "stage1_gateway_labels.jsonl"
VALID_ROUTES = {"policy", "price", "mixed", "discovery", "clarify", "abstain"}
VALID_STATUSES = {"continue", "clarify", "abstain"}


def load_labels():
    return [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines()]


def test_stage1_labels_have_a_complete_machine_readable_contract():
    records = load_labels()

    assert len(records) == 30
    assert len({record["id"] for record in records}) == 30
    assert all(record["expected_route"] in VALID_ROUTES for record in records)
    assert all(record["expected_status"] in VALID_STATUSES for record in records)
    assert all("expected_extraction" in record for record in records)
    assert all("expected_missing_fields" in record for record in records)
    assert "VERIFY" not in LABELS.read_text(encoding="utf-8")
    assert "TO FILL" not in LABELS.read_text(encoding="utf-8")


def test_stage1_labels_match_query_router_output():
    for record in load_labels():
        state = route_query(record["turns"][0]["user"])
        actual = {
            field: getattr(state, field)
            for field in record["expected_extraction"]
        }
        actual = {
            field: float(value) if isinstance(value, Decimal) else value
            for field, value in actual.items()
        }

        assert state.intent == record["expected_intent"], record["id"]
        assert state.route == record["expected_route"], record["id"]
        assert actual == record["expected_extraction"], record["id"]
        assert state.missing_fields == record["expected_missing_fields"], record["id"]
        assert state.status == record["expected_status"], record["id"]
