"""Load, validate and resolve the labelled question sets (proposal section 4.1).

The development set lives in data/evaluation-data/development/dev_set_questions.jsonl,
one question per line. Each question carries both kinds of label:

- Stage 1 gateway labels (expected_intent, expected_route, expected_status,
  expected_extraction, expected_missing_fields, turns): what the query router
  should output. stage1_gateway_labels.jsonl is generated from these fields
  (`python -m kopi_keys.evaluation.dataset`) and checked by
  tests/test_development_set_contract.py.
- Answer labels: verbatim evidence quotes (resolved here to chunk IDs in the
  ACTIVE policy snapshot; loading fails if a quote is not found word for word),
  price filters, expected topic cards, and current vs superseded values.

No held-out questions are stored in the repository. For the final evaluation
only (proposal section 4.1: the success targets are measured on the held-out
set), point the KOPI_HELDOUT_DIR environment variable at the private folder that
holds heldout_questions.jsonl, which uses the same schema as the dev set. Without
that variable, the held-out split is simply unavailable.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..topic_cards import load_cards

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
DEV_DIR = DATA / "evaluation-data" / "development"
DEV_FILE = DEV_DIR / "dev_set_questions.jsonl"
LABELS_FILE = DEV_DIR / "stage1_gateway_labels.jsonl"
HELDOUT_FILE_NAME = "heldout_questions.jsonl"

# Proposal section 4.1: 50 questions, split 30:20 and stratified by category.
DEV_COUNTS = {"policy": 7, "price": 6, "mixed": 5, "discovery": 4, "policy_changed": 4, "unanswerable": 4}
STAGE1_FIELDS = ("expected_intent", "expected_route", "expected_extraction",
                 "expected_missing_fields", "expected_status", "turns")


class EvalError(ValueError):
    """The question file is invalid or a quote isn't in the snapshot."""


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str  # regex over the chunk's source_slug
    quote: str = Field(min_length=3)  # must appear verbatim in a current chunk


class PriceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    town: str
    flat_type: str
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^(POL|PRC|MIX|DSC|CHG|OOS)-\d{2}$")
    origin: str = ""
    category: Literal["policy", "price", "mixed", "discovery", "policy_changed", "unanswerable"]
    question: str = Field(min_length=5)
    profile: dict[str, Any] = {}
    # Stage 1 gateway labels (backend Intent / Route / RouterStatus values)
    expected_intent: Literal["policy", "price", "mixed", "discovery", "unanswerable"]
    expected_route: Literal["policy", "price", "mixed", "discovery", "clarify", "abstain"]
    expected_status: Literal["continue", "clarify", "abstain"]
    expected_extraction: dict[str, Any]
    expected_missing_fields: list[str]
    turns: list[dict[str, Any]] = Field(min_length=1)
    # Answer labels
    should_abstain: bool
    expected_answer: str | None = None
    evidence: list[Evidence] = []
    price_filters: PriceFilters | None = None
    topics: list[str] = []
    expected_cards: list[str] = []
    expected_ask: str | None = None
    current_value: str | None = None
    superseded_value: str | None = None
    superseded_source: str | None = None
    effective_date: str | None = None
    notes: str | None = None


def active_snapshot() -> str:
    return (DATA / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()


def load_chunks(snapshot: str | None = None) -> list[dict]:
    path = DATA / "policy_chunks" / (snapshot or active_snapshot()) / "chunks.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def heldout_path() -> Path | None:
    folder = os.environ.get("KOPI_HELDOUT_DIR")
    return Path(folder) / HELDOUT_FILE_NAME if folder else None


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_questions(split: Literal["dev", "heldout"] = "dev", *, strict_counts: bool = True) -> list[dict]:
    """Validated questions with expected_chunk_ids resolved against the ACTIVE snapshot."""
    if split == "dev":
        path = DEV_FILE
    else:
        path = heldout_path()
        if path is None or not path.exists():
            raise EvalError("Held-out questions are private: set KOPI_HELDOUT_DIR to the folder holding "
                            f"{HELDOUT_FILE_NAME} (outside the repository).")
    chunks = [c for c in load_chunks() if not c["superseded"]]
    card_ids = {c.card_id for c in load_cards()}
    vocab = json.loads((DATA / "schema" / "vocab.json").read_text(encoding="utf-8"))["fields"]
    db_towns = set(vocab["town"]["values"])
    db_flats = {v["db_form"] for v in vocab["flat_type"]["values"].values() if v.get("db_form")}

    problems, out = [], []
    for raw in _read(path):
        try:
            q = Question.model_validate(raw)
        except ValidationError as error:
            first = error.errors()[0]
            problems.append(f"{raw.get('id')}: {first['loc']} {first['msg']}")
            continue
        ids: list[str] = []
        for ev in q.evidence:
            hits = [c for c in chunks if re.search(ev.source, c["source_slug"]) and ev.quote in c["content"]]
            if not hits:
                problems.append(f"{q.id}: quote not found verbatim in {ev.source!r}: {ev.quote!r}")
            preferred = [c for c in hits if not c["low_priority"]] or hits
            ids += [c["chunk_id"] for c in preferred if c["chunk_id"] not in ids]
        for field, value in q.profile.items():
            if field in vocab and str(value).lower() not in {k.lower() for k in vocab[field]["values"]}:
                problems.append(f"{q.id}: profile {field}={value!r} not in vocab.json")
        problems += [f"{q.id}: unknown card {c}" for c in q.expected_cards + q.topics if c not in card_ids]
        if q.price_filters and (q.price_filters.town not in db_towns or q.price_filters.flat_type not in db_flats):
            problems.append(f"{q.id}: price_filters not in vocab db_form values")
        if q.category in ("policy", "mixed", "policy_changed") and not ids:
            problems.append(f"{q.id}: policy question without evidence")
        if q.category in ("price", "mixed") and not q.price_filters:
            problems.append(f"{q.id}: price question without price_filters")
        if q.category == "discovery" and not q.expected_cards:
            problems.append(f"{q.id}: discovery question without expected_cards")
        if q.expected_route == "abstain" and not q.should_abstain:
            problems.append(f"{q.id}: abstain route but should_abstain is false")
        out.append({**q.model_dump(exclude_none=True), "expected_chunk_ids": ids, "split": split})

    ids = [q["id"] for q in out]
    if len(ids) != len(set(ids)):
        problems.append("duplicate question ids")
    if split == "dev" and strict_counts and dict(Counter(q["category"] for q in out)) != DEV_COUNTS:
        problems.append(f"dev categories {dict(Counter(q['category'] for q in out))} != {DEV_COUNTS}")
    if problems:
        raise EvalError("Invalid question set:\n  - " + "\n  - ".join(problems))
    return out


def stage1_labels(questions: list[dict]) -> list[dict]:
    """The router-only view of each question, in the format test_development_set_contract reads."""
    return [{"id": q["id"], **{field: q[field] for field in STAGE1_FIELDS}} for q in questions]


def write_stage1_labels() -> Path:
    labels = stage1_labels(load_questions("dev"))
    LABELS_FILE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in labels), encoding="utf-8")
    return LABELS_FILE


def main() -> int:
    """Validate the dev set and regenerate stage1_gateway_labels.jsonl from it."""
    try:
        path = write_stage1_labels()
    except EvalError as error:
        print(error)
        return 1
    questions = load_questions("dev")
    print(f"{len(questions)} dev questions valid; categories {dict(Counter(q['category'] for q in questions))}")
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
