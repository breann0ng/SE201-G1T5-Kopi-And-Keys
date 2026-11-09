"""Run scripts/scraping/validate.py as part of the test suite (so CI runs it on every PR).

The validator checks the ACTIVE snapshot's chunks and topic cards: schemas, unique chunk IDs,
content hashes, vocabulary, dollar figures against the source, card chunk IDs that exist and
are current, verbatim overview quotes, and income schemes. Offline, about three seconds.
Re-chunking that breaks a card's chunk IDs fails here instead of in the frontend tests.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "scraping"))
import validate  # noqa: E402


def test_active_snapshot_chunks_and_cards_pass_every_check(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["validate.py"])  # no date: validate the ACTIVE snapshot
    code = validate.main()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "ALL CHECKS PASSED" in out
    assert "FAIL" not in out
