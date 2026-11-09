"""Count chunk-shape defects in a snapshot's chunks.jsonl (read-only, no network).

Usage: python audit_chunks.py [YYYY-MM-DD] [--examples N]
       (default: the date in data/policy_snapshots/ACTIVE)

Reported, so a re-chunk can be compared before and after:
- sub-label headings: a section split off under a bold label such as "What you need to do:"
- tables without a divider row: a bold header row not followed by |---|
  (tables with no header row are counted separately; they are left as they are)
- multi-table chunks: two or more separate tables packed into one chunk
- oversized chunks: over 600 words (a table row too long to split)
- short chunks: under 25 words with no $ figure (fragments with little context)
"""
from __future__ import annotations

import argparse
import json
import re

from chunk import is_header_row
from fetch import ROOT

SNAPS = ROOT / "data" / "policy_snapshots"
CHUNKS = ROOT / "data" / "policy_chunks"
DIVIDER = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
OVERSIZED_WORDS = 600
SHORT_WORDS = 25


def tables(content: str) -> list[list[str]]:
    """Each pipe table in the chunk, as its rows. A cell can hold line breaks, so a
    row runs from a line starting with '|' to a line ending with '|'."""
    found, cur = [], []
    for line in content.split("\n"):
        if cur and not cur[-1].rstrip().endswith("|"):
            cur[-1] += "\n" + line
        elif line.lstrip().startswith("|"):
            cur.append(line.strip())
        elif cur:
            found.append(cur)
            cur = []
    if cur:
        found.append(cur)
    return found


def defects(chunk: dict) -> list[str]:
    content, heading = chunk["content"], chunk["section_heading"]
    words = len(content.split())
    found = []
    if heading.split(" > ")[-1].rstrip().endswith(":"):
        found.append("sub-label heading")
    ts = tables(content)
    for t in ts:
        if len(t) > 1 and not DIVIDER.match(t[1]):  # one row has no header to mark
            found.append("table without divider" if is_header_row(t[0]) else "headerless table (as-is)")
            break
    if len(ts) > 1:
        found.append("multi-table chunk")
    if words > OVERSIZED_WORDS:
        found.append("oversized")
    if words < SHORT_WORDS and not re.search(r"\$\d", content):
        found.append("short")
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date", nargs="?")
    ap.add_argument("--examples", type=int, default=3, help="chunk IDs to list per defect")
    args = ap.parse_args()
    date = args.date or (SNAPS / "ACTIVE").read_text(encoding="utf-8").strip()
    rows = [json.loads(line) for line in
            (CHUNKS / date / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    by_defect: dict[str, list[str]] = {}
    for c in rows:
        for d in defects(c):
            by_defect.setdefault(d, []).append(c["chunk_id"])
    print(f"snapshot {date}: {len(rows)} chunks")
    for d in ("sub-label heading", "table without divider", "multi-table chunk", "oversized", "short",
              "headerless table (as-is)"):
        ids = by_defect.get(d, [])
        print(f"  {d:<22} {len(ids):>4}  {' '.join(ids[:args.examples])}")


if __name__ == "__main__":
    main()
