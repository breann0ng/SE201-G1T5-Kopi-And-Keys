"""Resolve evaluation/questions.json into evaluation/eval_set.jsonl (no network).

Each evidence quote is looked up VERBATIM in the ACTIVE snapshot's chunks; the
build fails if a quote is missing, so every expected passage is traceable to
official text. Rebuild after a new snapshot goes live: chunk IDs may change,
the quotes should not.

Usage: python evaluation/build_eval_set.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from kopi_keys.topic_cards import load_cards  # noqa: E402

HERE = Path(__file__).resolve().parent
CATEGORY_COUNTS = {"policy": 12, "price": 10, "mixed": 8, "discovery": 6, "policy_changed": 6, "unanswerable": 8}
DEV_COUNTS = {"policy": 7, "price": 6, "mixed": 5, "discovery": 4, "policy_changed": 4, "unanswerable": 4}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    quote: str = Field(min_length=3)


class PriceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    town: str
    flat_type: str
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^(POL|PRC|MIX|DSC|CHG|OOS)-\d{2}$")
    category: Literal["policy", "price", "mixed", "discovery", "policy_changed", "unanswerable"]
    split: Literal["dev", "heldout"]
    question: str = Field(min_length=5)
    profile: dict[str, Any]
    expected_route: Literal["policy", "price", "mixed", "unsupported"]
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


def main() -> int:
    spec = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    active = (ROOT / "data" / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
    chunks = [json.loads(ln) for ln in (ROOT / "data" / "policy_chunks" / active / "chunks.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    vocab = json.loads((ROOT / "data" / "schema" / "vocab.json").read_text(encoding="utf-8"))["fields"]
    card_ids = {c.card_id for c in load_cards()}
    db_towns = set(vocab["town"]["values"])
    db_flats = {v["db_form"] for v in vocab["flat_type"]["values"].values() if v.get("db_form")}

    problems: list[str] = []
    out: list[dict] = []
    for raw in spec["questions"]:
        try:
            q = Question.model_validate(raw)
        except ValidationError as e:
            problems.append(f"{raw.get('id')}: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
            continue
        chunk_ids: list[str] = []
        for ev in q.evidence:
            hits = [c["chunk_id"] for c in chunks if re.search(ev.source, c["source_slug"])
                    and ev.quote in c["content"] and not c["superseded"]]
            preferred = [h for h in hits if not next(c for c in chunks if c["chunk_id"] == h)["low_priority"]]
            if not hits:
                problems.append(f"{q.id}: quote not found verbatim in {ev.source!r}: {ev.quote!r}")
            chunk_ids += [h for h in (preferred or hits) if h not in chunk_ids]
        if q.expected_answer and q.evidence and not any(
                q.expected_answer in c["content"] for c in chunks if c["chunk_id"] in chunk_ids):
            problems.append(f"{q.id}: expected_answer not found in its evidence chunks")
        for field, value in q.profile.items():
            if field in vocab and str(value).lower() not in {k.lower() for k in vocab[field]["values"]}:
                problems.append(f"{q.id}: profile {field}={value!r} not in vocab.json")
        for cid in q.expected_cards + q.topics:
            if cid not in card_ids:
                problems.append(f"{q.id}: unknown card {cid}")
        if q.price_filters and (q.price_filters.town not in db_towns or q.price_filters.flat_type not in db_flats):
            problems.append(f"{q.id}: price_filters not in vocab db_form values")
        if q.category in ("policy", "mixed", "policy_changed") and not chunk_ids:
            problems.append(f"{q.id}: policy question without evidence")
        if q.category in ("price", "mixed") and not q.price_filters:
            problems.append(f"{q.id}: price question without price_filters")
        if q.category == "discovery" and not q.expected_cards:
            problems.append(f"{q.id}: discovery question without expected_cards")
        if q.should_abstain != (q.expected_route == "unsupported"):
            problems.append(f"{q.id}: should_abstain inconsistent with expected_route")
        out.append({**q.model_dump(exclude_none=True), "expected_chunk_ids": chunk_ids, "snapshot_date": active})

    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)):
        problems.append("duplicate question ids")
    cats = Counter(r["category"] for r in out)
    devs = Counter(r["category"] for r in out if r["split"] == "dev")
    if dict(cats) != CATEGORY_COUNTS:
        problems.append(f"category counts {dict(cats)} != {CATEGORY_COUNTS}")
    if dict(devs) != DEV_COUNTS:
        problems.append(f"dev split {dict(devs)} != {DEV_COUNTS} (30 dev / 20 heldout, stratified)")

    print(f"{len(out)} questions; categories {dict(cats)}; dev {sum(devs.values())} / heldout {len(out) - sum(devs.values())}")
    needs_source = [r["id"] for r in out if r["category"] == "policy_changed" and not r.get("superseded_value")]
    if needs_source:
        print(f"note: superseded value still needs a source for {needs_source}")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  - " + p)
        return 1
    with (HERE / "eval_set.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {HERE / 'eval_set.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
