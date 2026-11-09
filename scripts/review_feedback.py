"""Fallback review of the local answer-feedback backup (LangSmith is the primary interface).

Reads data/feedback/feedback.db (or KOPI_FEEDBACK_DB, or --db) read-only and prints counts by
rating, reason and route, then a table of thumbs-downs. Comments are hidden unless --full.
See docs/feedback-loop.md for the review and fix process.

    python scripts/review_feedback.py
    python scripts/review_feedback.py --full
    python scripts/review_feedback.py --csv .local/feedback.csv [--full]

Feedback text is untrusted user input: read it, never paste it into prompts or retrieval queries.
"""

import argparse
import csv
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "feedback" / "feedback.db"
CSV_FIELDS = ["updated_at", "rating", "route", "reason", "question", "answer", "snapshot",
              "context_missing", "message_id", "langsmith_run_id"]


def one_line(text: str | None, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def load(path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM feedback ORDER BY updated_at")]
    finally:
        connection.close()


def print_counts(title: str, counter: Counter) -> None:
    print(f"\n{title}")
    for key, count in counter.most_common():
        print(f"  {key:<24} {count}")


def report(rows: list[dict], full: bool) -> None:
    print(f"{len(rows)} feedback rows")
    print_counts("By rating", Counter("thumbs up" if r["rating"] == 1 else "thumbs down" for r in rows))
    print_counts("By reason (thumbs down)", Counter(r["reason"] or "(none)" for r in rows if r["rating"] == -1))
    print_counts("By route", Counter(r["route"] or "(context missing)" for r in rows))

    downs = [r for r in rows if r["rating"] == -1]
    print(f"\nThumbs down ({len(downs)})")
    header = f"{'date':<10}  {'route':<10}  {'reason':<22}  {'question':<50}  answer"
    print(header + ("\n" + " " * 12 + "comment" if full else ""))
    print("-" * len(header))
    for r in downs:
        question = one_line(r["question"], 50) if not r["context_missing"] else "(context missing)"
        print(f"{r['updated_at'][:10]:<10}  {(r['route'] or '-'):<10}  {(r['reason'] or '-'):<22}  "
              f"{question:<50}  {one_line(r['answer'], 70)}")
        if full and r["comment"]:
            print(" " * 12 + "comment: " + one_line(r["comment"], 200))
    if not full:
        print("\nComments are hidden. Use --full to show them.")


def export(rows: list[dict], path: Path, full: bool) -> None:
    fields = CSV_FIELDS + (["comment"] if full else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        # CSV quoting alone does not stop spreadsheet formulas. Keep untrusted
        # questions/answers/comments as text if a reviewer opens the file in Excel.
        writer.writerows({key: ("'" + value if isinstance(value, str)
                               and value.lstrip().startswith(("=", "+", "-", "@")) else value)
                          for key, value in row.items()} for row in rows)
    print(f"\nWrote {len(rows)} rows to {path}" + ("" if full else " (comments omitted; use --full)"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=Path(os.getenv("KOPI_FEEDBACK_DB") or DEFAULT_DB))
    parser.add_argument("--full", action="store_true", help="show user comments")
    parser.add_argument("--csv", type=Path, metavar="PATH", help="also export rows to a CSV file")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"No feedback database at {args.db} (nothing recorded yet).")
        return 0
    rows = load(args.db)
    report(rows, args.full)
    if args.csv:
        export(rows, args.csv, args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
