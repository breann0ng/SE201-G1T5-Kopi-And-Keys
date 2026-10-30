"""The dev set and evaluation harness (backend/kopi_keys/evaluation/)."""
import json
from typing import get_args

from kopi_keys.evaluation import dataset, metrics
from kopi_keys.schemas import Route


def test_dev_set_is_valid_stratified_and_resolved():
    questions = dataset.load_questions("dev")  # raises if a quote isn't verbatim in the snapshot
    assert len(questions) == 30
    assert all(q["expected_route"] in get_args(Route) for q in questions)
    policy = [q for q in questions if q["category"] in ("policy", "mixed", "policy_changed")]
    assert all(q["expected_chunk_ids"] for q in policy)


def test_stage1_labels_file_is_generated_from_the_dev_set():
    on_disk = [json.loads(line) for line in dataset.LABELS_FILE.read_text(encoding="utf-8").splitlines()]
    assert on_disk == dataset.stage1_labels(dataset.load_questions("dev")), \
        "Run: python -m kopi_keys.evaluation.dataset"


def test_end_to_end_scores_use_the_response_route():
    question = {"id": "PRC-01", "category": "price", "question": "q", "expected_route": "price",
                "should_abstain": False}
    resp = {"status": "answered", "route": "price", "message": "", "citations": [], "price_result": {"volume": 3},
            "trace": ["query_router:price", "price_query:3 transactions"]}
    assert metrics.end_to_end([question], {"PRC-01": resp})["routing_accuracy"] == "100% (1/1)"


def test_no_held_out_questions_in_the_repository():
    # Held-out questions are read from KOPI_HELDOUT_DIR, outside the repo, for final results only.
    assert not list(dataset.ROOT.glob(f"**/{dataset.HELDOUT_FILE_NAME}"))
    assert all("split" not in json.loads(line) for line in dataset.DEV_FILE.read_text(encoding="utf-8").splitlines())


def _price_question(text, **filters):
    want = {"town": "TAMPINES", "flat_type": "4 ROOM", "start_month": "2026-05", "end_month": "2026-10", **filters}
    return {"id": "PRC-99", "turns": [{"user": text}], "price_filters": want}


def test_price_filters_pin_the_router_date_for_relative_periods():
    q = _price_question("What did 4-room flats in Tampines sell for in the past 6 months?")
    assert metrics.price_filters([q], "2026-10", "2026-10")["accuracy"] == "100% (1/1)"
    # The same question labelled a month later no longer matches.
    assert metrics.price_filters([q], "2026-11", "2026-10")["mismatches"][0]["wrong"] == ["end_month", "start_month"]


def test_price_filters_report_a_missed_band_and_follow_clarification_turns():
    banded = _price_question("What do high floor 4-room flats in Tampines go for?",
                             start_month="2025-11", storey_band="high")
    assert metrics.price_filters([banded], "2026-10", "2026-10")["mismatches"][0]["wrong"] == ["storey_band"]
    clarified = {"id": "PRC-98", "price_filters": {"town": "TAMPINES", "flat_type": "4 ROOM",
                                                   "start_month": "2025-11", "end_month": "2026-10"},
                 "turns": [{"user": "How much is a flat in Tampines?"},
                           {"expected_action": "clarify", "ask_for": ["flat_type"]},
                           {"user": "4-room"}, {"expected_action": "answer"}]}
    assert metrics.price_filters([clarified], "2026-10", "2026-10")["accuracy"] == "100% (1/1)"


def test_price_figures_compare_tool_output_with_expected_price():
    from decimal import Decimal

    from kopi_keys.components.price_query import InvalidPriceFilterError
    from kopi_keys.schemas import PriceResult

    class FakeTool:
        def info(self):
            return type("Info", (), {"max_month": "2026-10"})()

        def query(self, filters):
            if filters.start_month < "2017-01":
                raise InvalidPriceFilterError("outside the dataset")
            return PriceResult(query_id="q", filters=filters, volume=2, mean=Decimal(5), median=Decimal(5),
                               iqr=Decimal(0), minimum=Decimal(5), maximum=Decimal(5))

    good = {**_price_question("How much are 4-room flats in Tampines?"), "expected_price": {"volume": 2, "median": Decimal(5)}}
    wrong = {**good, "id": "PRC-97", "expected_price": {"volume": 2, "median": Decimal(6)}}
    old = {**_price_question("What did 4-room flats in Tampines sell for in 2012?"), "id": "OOS-99",
           "expected_price": {"volume": 0}}
    result = metrics.price_figures([good, wrong, old], FakeTool(), "2026-10")
    assert result["accuracy"] == "67% (2/3)" and [r["id"] for r in result["mismatches"]] == ["PRC-97"]


def test_end_to_end_checks_answered_price_figures():
    from decimal import Decimal

    question = {"id": "PRC-01", "category": "price", "question": "q", "expected_route": "price",
                "should_abstain": False, "expected_price": {"volume": 3, "median": Decimal("500000")}}
    resp = {"status": "answered", "route": "price", "message": "", "citations": [],
            "price_result": {"volume": 3, "median": "500000.00"}}
    assert metrics.end_to_end([question], {"PRC-01": resp})["price_figures"] == "100% (1/1)"
    resp["price_result"]["median"] = "510000.00"
    assert metrics.end_to_end([question], {"PRC-01": resp})["price_figures"] == "0% (0/1)"
