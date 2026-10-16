"""One-command policy re-snapshot, meant to be run by a scheduler.

Steps (each is an existing script, run in order; any failure stops the run):
  1. robots.txt for each domain        fetch.py robots
  2. sitemaps declared in robots.txt   fetch.py sitemap <url>
  3. add in-scope pages to seeds.json  discover.py
  4. fetch every seed page             fetch.py seeds
  5. fetch every policy PDF            fetch.py pdf <slug> <url>   (pdf_seeds.json)
  6. extract clean text/tables         extract.py
  7. check figures raw vs clean        verify.py
  8. compare with previous snapshot    diff.py

Writes data/policy_snapshots/<today SGT>/. Same-day reruns re-fetch nothing.
The diff is against the snapshot named in data/policy_snapshots/ACTIVE.
Playwright renders are not repeated: the 3 pages rendered on 2026-10-15 gained
no content from it. It does NOT mark anything superseded; a person reviews
changes_since_<old>.md and decides.

Usage: python refresh.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITEMAPS = [
    "https://www.hdb.gov.sg/sitemap.xml",
    "https://www.mynicehome.gov.sg/sitemap.xml",
    "https://www.cpf.gov.sg/sitemap.xml",
]


def run(*args: str) -> None:
    print(f"\n>>> {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], cwd=HERE, check=True)


def main() -> None:
    run("fetch.py", "robots")
    for url in SITEMAPS:
        run("fetch.py", "sitemap", url)
    run("discover.py")
    run("fetch.py", "seeds")
    for pdf in json.loads((HERE / "pdf_seeds.json").read_text(encoding="utf-8")):
        run("fetch.py", "pdf", pdf["slug"], pdf["url"])
    run("extract.py")
    run("verify.py")
    snaps = HERE.parents[1] / "data" / "policy_snapshots"
    if sum(1 for d in snaps.iterdir() if (d / "manifest.json").exists()) >= 2:
        run("diff.py")
    else:
        print("\nOnly one snapshot exists; nothing to diff yet.")


if __name__ == "__main__":
    main()
