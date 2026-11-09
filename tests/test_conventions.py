"""Convention tests: the rules this codebase follows that generated code can get wrong.

Code can be right in general and wrong here: an ID in the wrong form, money as a float, a
source that is not an official site, a held-out file in the repository. Each rule below is
stated once in plain words and checked against the real data and types.
"""
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from kopi_keys.evaluation import dataset
from kopi_keys.schemas import BuyerProfile, ChatRequest
from kopi_keys.state import GraphState, initial_state

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (ROOT / "data" / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
CHUNKS = [json.loads(line) for line in
          (ROOT / "data" / "policy_chunks" / SNAPSHOT / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
CARD_FILES = sorted((ROOT / "data" / "topic_cards" / SNAPSHOT).glob("card_*.json"))


# --- IDs ---------------------------------------------------------------------

def test_chunk_ids_are_upper_snake_case_with_the_chunk_prefix():
    bad = [c["chunk_id"] for c in CHUNKS if not re.fullmatch(r"CHUNK_[A-Z0-9]+(_[A-Z0-9]+)*", c["chunk_id"])]
    assert bad == []


def test_card_ids_have_the_card_prefix_and_match_their_file_name():
    assert CARD_FILES, f"no cards for snapshot {SNAPSHOT}"
    for path in CARD_FILES:
        card_id = json.loads(path.read_text(encoding="utf-8"))["card_id"]
        assert re.fullmatch(r"CARD_[A-Z0-9]+(_[A-Z0-9]+)*", card_id), card_id
        assert path.name == f"card_{card_id.removeprefix('CARD_').lower()}.json", path.name


# --- Sources --------------------------------------------------------------------

def test_every_chunk_comes_from_an_official_gov_sg_page_over_https():
    for c in CHUNKS:
        url = urlparse(c["source_url"])
        assert url.scheme == "https", c["chunk_id"]
        assert url.netloc == "gov.sg" or url.netloc.endswith(".gov.sg"), (c["chunk_id"], url.netloc)


def test_every_chunk_has_a_source_tier_and_belongs_to_the_active_snapshot():
    for c in CHUNKS:
        assert c["source_tier"] in (1, 2, 3), c["chunk_id"]
        assert c["snapshot_date"] == SNAPSHOT, c["chunk_id"]


# --- Money and dates --------------------------------------------------------------

def test_income_from_the_website_becomes_an_exact_decimal():
    # The sidebar sends a JSON number; ceilings are compared in Decimal, never float.
    state = GraphState(**initial_state(ChatRequest(message="hi", profile=BuyerProfile(household_income=7000.1))))
    assert isinstance(state.income, Decimal)
    assert state.income == Decimal("7000.1")


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-01", "2026/01", "2026-00"])
def test_months_must_be_yyyy_mm(month):
    with pytest.raises(ValidationError):
        GraphState(message="x", start_month=month)


# --- Held-out questions ----------------------------------------------------------

def test_held_out_questions_need_an_explicit_folder_outside_the_repo(monkeypatch):
    monkeypatch.delenv("KOPI_HELDOUT_DIR", raising=False)
    assert dataset.heldout_path() is None
    with pytest.raises(dataset.EvalError, match="KOPI_HELDOUT_DIR"):
        dataset.load_questions("heldout")


def test_no_held_out_question_file_is_committed():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    assert [f for f in tracked if Path(f).name == dataset.HELDOUT_FILE_NAME] == []
