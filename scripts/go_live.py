"""Make a reviewed policy snapshot the one the advisor serves (data/README.md, section 4.1).

Usage (repo root, project venv):
    python scripts/go_live.py YYYY-MM-DD            # switch ACTIVE and rebuild the local index
    python scripts/go_live.py YYYY-MM-DD --no-index # switch only (rebuild the index later)

Run it only after a person has reviewed the snapshot's changes_since_<old>.md. Steps:
1. build data/policy_chunks/<date>/ and data/topic_cards/<date>/ if they are missing
2. validate.py <date>; on any failure ACTIVE is left unchanged
3. write <date> to data/policy_snapshots/ACTIVE
4. rebuild the local vector index, reusing data/policy_index/<date>/ vectors where the text is unchanged

Nothing is committed. Open a go-live pull request with ACTIVE, the snapshot's chunks, cards and
data/policy_index/<date>/, list the review decisions, and have a teammate approve it.
To roll back, run this again with the previous date.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPING = ROOT / "scripts" / "scraping"
ACTIVE = ROOT / "data" / "policy_snapshots" / "ACTIVE"


def run(*args: str) -> bool:
    print(f"\n>>> {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, *args], cwd=SCRAPING).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date", help="snapshot folder name, YYYY-MM-DD")
    ap.add_argument("--no-index", action="store_true", help="switch ACTIVE without rebuilding the vector index")
    args = ap.parse_args()
    date, previous = args.date, ACTIVE.read_text(encoding="utf-8").strip()

    if not (ROOT / "data" / "policy_snapshots" / date / "manifest.json").exists():
        print(f"No snapshot data/policy_snapshots/{date}/ (run scripts/scraping/refresh.py first).")
        return 1
    if not (ROOT / "data" / "policy_chunks" / date / "chunks.jsonl").exists() and not run("chunk.py", date):
        return 1
    if not any((ROOT / "data" / "topic_cards" / date).glob("*.json")) and not run("build_cards.py", date):
        return 1
    if not run("validate.py", date):
        print(f"\nValidation failed: ACTIVE stays {previous}.")
        return 1

    ACTIVE.write_text(date + "\n", encoding="utf-8")
    print(f"\nACTIVE: {previous} -> {date}")
    if not args.no_index:
        index = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_policy_index.py")], cwd=ROOT)
        if index.returncode != 0:
            print("\nThe vector index did not build; policy search is keyword-only until "
                  "scripts/build_policy_index.py succeeds.")
    print("\nNext: run the tests and `python -m kopi_keys.evaluation.run_eval --retriever hybrid`, then open a "
          f"go-live PR with data/policy_snapshots/ACTIVE, data/policy_chunks/{date}/, data/topic_cards/{date}/ "
          f"and data/policy_index/{date}/. To roll back: python scripts/go_live.py {previous}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
