"""scripts/review_feedback.py: counts, hidden comments by default, CSV export. Temporary DB only."""

import csv
import importlib.util
import uuid
import pytest
from pathlib import Path

from kopi_keys.feedback import AnswerContext, FeedbackRequest, FeedbackStore

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_feedback.py"
spec = importlib.util.spec_from_file_location("review_feedback", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def seed(db: Path) -> None:
    store = FeedbackStore(db)
    context = AnswerContext("What is the demo grant?", "The demo grant is $10,000.", "policy", "2026-10-15", None)
    store.save(FeedbackRequest(message_id=str(uuid.uuid4()), rating=1), context)
    store.save(FeedbackRequest(message_id=str(uuid.uuid4()), rating=-1, reason="wrong_numbers",
                               comment="PRIVATE-COMMENT"), context)
    store.save(FeedbackRequest(message_id=str(uuid.uuid4()), rating=-1), None)


def test_report_hides_comments_unless_full(tmp_path, capsys):
    db = tmp_path / "feedback.db"
    seed(db)
    review.main(["--db", str(db)])
    out = capsys.readouterr().out
    assert "3 feedback rows" in out and "thumbs down              2" in out
    assert "wrong_numbers" in out and "(context missing)" in out
    assert "PRIVATE-COMMENT" not in out
    review.main(["--db", str(db), "--full"])
    assert "PRIVATE-COMMENT" in capsys.readouterr().out


def test_csv_export_omits_comments_unless_full(tmp_path):
    db, out = tmp_path / "feedback.db", tmp_path / "out" / "feedback.csv"
    seed(db)
    review.main(["--db", str(db), "--csv", str(out)])
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 3 and "comment" not in rows[0]
    review.main(["--db", str(db), "--csv", str(out), "--full"])
    assert "PRIVATE-COMMENT" in out.read_text(encoding="utf-8")


def test_missing_database_is_not_an_error(tmp_path, capsys):
    assert review.main(["--db", str(tmp_path / "none.db")]) == 0
    assert "nothing recorded yet" in capsys.readouterr().out
    assert not (tmp_path / "none.db").exists()


@pytest.mark.parametrize("text", ["=1+1", " +SUM(1,2)", "\t@SUM(1,2)", "-2+3"])
def test_csv_export_treats_untrusted_formula_prefixes_as_text(tmp_path, text):
    output = tmp_path / "review.csv"
    row = {"rating": -1, "question": text, "answer": "Normal answer.", "comment": text}
    review.export([row], output, full=True)
    with output.open(encoding="utf-8", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["question"] == "'" + text and exported["comment"] == "'" + text
    assert exported["rating"] == "-1" and exported["answer"] == "Normal answer."
    assert row["question"] == text  # export does not modify the saved feedback
