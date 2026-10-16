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
