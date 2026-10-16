"""Chunk IDs stay unique when a snapshot update adds passages (scripts/scraping/chunk.py)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "scraping"))
import chunk  # noqa: E402


def test_counters_are_keyed_by_bare_policy_code():
    registry = {"a:0": "CHUNK_EHG_01", "b:0": "CHUNK_EHG_07", "c:0": "CHUNK_CPF_03"}
    assert chunk.next_counters(registry) == {"EHG": 7, "CPF": 3}


def test_new_passage_after_update_gets_a_fresh_id():
    registry = {"a:0": "CHUNK_EHG_01", "b:0": "CHUNK_EHG_02"}
    next_n = chunk.next_counters(registry)
    assert chunk.allocate(registry, next_n, "new-paragraph:0", "EHG") == "CHUNK_EHG_03"
    assert len(set(registry.values())) == len(registry)


def test_real_registry_update_never_reuses_an_id():
    registry = json.loads((ROOT / "data" / "policy_chunks" / "chunk_id_registry.json").read_text(encoding="utf-8"))
    before = set(registry.values())
    next_n = chunk.next_counters(registry)
    added = {chunk.allocate(registry, next_n, f"added-{code}:0", code) for code in next_n}
    assert added.isdisjoint(before)
    assert len(set(registry.values())) == len(registry)


def test_allocate_refuses_an_id_already_in_use():
    registry = {"a:0": "CHUNK_EHG_01"}
    with pytest.raises(SystemExit, match="already assigned"):
        chunk.allocate(registry, {"EHG": 0}, "b:0", "EHG")
