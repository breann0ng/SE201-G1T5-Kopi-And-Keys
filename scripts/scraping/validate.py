"""Validate policy chunks and topic cards (no network).

Usage: python validate.py [YYYY-MM-DD]   (default: date in data/policy_snapshots/ACTIVE)
Exit code 1 if any check fails.

Checks:
 1. every chunk / card parses and matches its Pydantic schema
 2. no duplicate chunk_ids, no empty chunks, content_sha256 matches content
 3. every eligibility tag key/value exists in data/schema/vocab.json
 4. every dollar figure in a chunk appears in its source clean .md
 5. every supporting_chunk_id exists (and is not superseded or low-priority)
 6. every trigger_conditions key/value exists in vocab.json
 7. question_template has no policy figures (digits or $) and only {placeholders}
 8. every raw file's sha256 matches manifest.json (snapshot evidence is byte-exact)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fetch import ROOT

SNAPS = ROOT / "data" / "policy_snapshots"
DOLLAR = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Chunk(Strict):
    chunk_id: str = Field(pattern=r"^CHUNK_[A-Z]+_\d{2,}$")
    source_url: str = Field(pattern=r"^https://www\.(hdb|cpf|mynicehome)\.gov\.sg/")
    source_slug: str
    source_tier: Literal[1, 2, 3]
    policy_name: str = Field(min_length=1)
    section_heading: str
    snapshot_date: date
    verified_on: date
    page_last_updated: str | None
    effective_date: date | None
    effective_date_text: str | None
    low_priority: bool
    superseded: bool
    eligibility_tags: dict[str, list[str]]
    content: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Card(Strict):
    card_id: str = Field(pattern=r"^CARD_[A-Z_]+$")
    topic_name: str = Field(min_length=1)
    trigger_conditions: dict[str, list[str]]
    required_fields: list[str] = Field(min_length=1)
    supporting_chunk_ids: list[str] = Field(min_length=1)
    question_template: str = Field(min_length=1)
    snapshot_date: date


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else (SNAPS / "ACTIVE").read_text(encoding="utf-8").strip()
    vocab = json.loads((ROOT / "data" / "schema" / "vocab.json").read_text(encoding="utf-8"))["fields"]
    errors: list[str] = []
    results: list[tuple[str, int]] = []

    def check(name: str, problems: list[str]) -> None:
        results.append((name, len(problems)))
        errors.extend(f"[{name}] {p}" for p in problems)

    def vocab_problems(where: str, mapping: dict[str, list[str]]) -> list[str]:
        out = []
        for key, values in mapping.items():
            if key not in vocab:
                out.append(f"{where}: unknown key {key!r}")
                continue
            out += [f"{where}: {key}={v!r} not in vocab" for v in values if v not in vocab[key]["values"]]
        return out

    # 1-2. chunks
    chunks: dict[str, Chunk] = {}
    parse, dupes, empty, sha = [], [], [], []
    path = ROOT / "data" / "policy_chunks" / day / "chunks.jsonl"
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            c = Chunk.model_validate_json(line)
        except ValidationError as e:
            parse.append(f"line {n}: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
            continue
        if c.chunk_id in chunks:
            dupes.append(c.chunk_id)
        if not c.content.strip():
            empty.append(c.chunk_id)
        if hashlib.sha256(c.content.encode("utf-8")).hexdigest() != c.content_sha256:
            sha.append(c.chunk_id)
        chunks[c.chunk_id] = c
    check("chunks parse + schema", parse)
    check("no duplicate chunk_ids", dupes)
    check("no empty chunks", empty)
    check("content_sha256 matches", sha)

    # 3. tags
    check("chunk tags in vocab", [p for c in chunks.values() for p in vocab_problems(c.chunk_id, c.eligibility_tags)])

    # 4. figures traceable to source
    clean_cache: dict[str, str] = {}
    missing = []
    for c in chunks.values():
        src = clean_cache.setdefault(c.source_slug, (SNAPS / day / "clean" / f"{c.source_slug}.md")
                                     .read_text(encoding="utf-8"))
        missing += [f"{c.chunk_id}: {f!r} not in clean/{c.source_slug}.md"
                    for f in set(DOLLAR.findall(c.content)) if f not in src]
    check("chunk $ figures in source clean .md", missing)

    # 8. raw evidence unchanged since capture (.gitattributes keeps raw/ byte-exact)
    manifest = json.loads((SNAPS / day / "manifest.json").read_text(encoding="utf-8"))
    raw_bad = []
    for page in manifest["pages"]:
        if not page.get("sha256"):
            continue
        method = page.get("method")
        ext = ".pdf" if method == "pdf" else ".rendered.html" if method == "playwright" else ".html"
        raw = SNAPS / day / "raw" / f"{page['slug']}{ext}"
        if not raw.exists():
            raw_bad.append(f"{page['slug']}: raw/{raw.name} missing")
        elif hashlib.sha256(raw.read_bytes()).hexdigest() != page["sha256"]:
            raw_bad.append(f"{page['slug']}: raw/{raw.name} sha256 differs from manifest")
    check("raw files match manifest sha256", raw_bad)

    # 5-7. cards
    cards, card_parse = [], []
    for p in sorted((ROOT / "data" / "topic_cards").glob("*.json")):
        try:
            cards.append(Card.model_validate_json(p.read_text(encoding="utf-8")))
        except ValidationError as e:
            card_parse.append(f"{p.name}: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
    check("cards parse + schema", card_parse)
    refs = []
    for card in cards:
        for cid in card.supporting_chunk_ids:
            c = chunks.get(cid)
            if c is None:
                refs.append(f"{card.card_id}: {cid} not in chunks.jsonl")
            elif c.superseded or c.low_priority:
                refs.append(f"{card.card_id}: {cid} is superseded/low-priority")
    check("supporting_chunk_ids exist", refs)
    check("trigger_conditions in vocab",
          [p for card in cards for p in vocab_problems(card.card_id, card.trigger_conditions)])
    tmpl = []
    for card in cards:
        if re.search(r"[\d$]", card.question_template):
            tmpl.append(f"{card.card_id}: template contains a digit or '$'")
        stripped = re.sub(r"\{[a-z_]+\}", "", card.question_template)
        if "{" in stripped or "}" in stripped:
            tmpl.append(f"{card.card_id}: malformed placeholder")
        if card.snapshot_date.isoformat() != day:
            tmpl.append(f"{card.card_id}: snapshot_date {card.snapshot_date} != {day}")
    check("question_template has no figures", tmpl)

    print(f"Validating snapshot {day}: {len(chunks)} chunks, {len(cards)} cards\n")
    for name, n in results:
        print(f"  {'PASS' if n == 0 else 'FAIL'}  {name}" + (f"  ({n} problems)" if n else ""))
    if errors:
        print("\nProblems:")
        for e in errors[:50]:
            print("  - " + e)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more")
    print(f"\n{'ALL CHECKS PASSED' if not errors else f'{len(errors)} PROBLEM(S)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
