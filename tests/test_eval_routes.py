"""The eval set's expected routes use the backend's Route labels (evaluation/run_eval.py)."""
import json
import sys
from pathlib import Path
from typing import get_args

from kopi_keys.schemas import Route

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import run_eval  # noqa: E402


def test_expected_routes_are_backend_routes():
    items = [json.loads(line) for line in (ROOT / "evaluation" / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {it["expected_route"] for it in items} <= set(get_args(Route))


def test_route_comes_from_the_response_not_the_trace():
    # Price answers trace as "price_query:...", which the old trace search misread.
    resp = {"route": "price", "trace": ["query_router:price", "price_query:12 transactions"]}
    assert run_eval.response_route(resp) == "price"
    assert run_eval.response_route({"route": "mixed", "trace": []}) == "mixed"


def test_committed_eval_files_hold_no_held_out_questions():
    # Held-out questions live in a private, gitignored folder (evaluation/held-out/).
    spec = json.loads((ROOT / "evaluation" / "questions.json").read_text(encoding="utf-8"))
    assert {q["split"] for q in spec["questions"]} == {"dev"}
    items = [json.loads(line) for line in (ROOT / "evaluation" / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {it["split"] for it in items} == {"dev"}
