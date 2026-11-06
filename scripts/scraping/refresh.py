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
       python refresh.py --github-actions

Local exit codes: 0 ready, 2 source access blocked, 1 unexpected failure.
GitHub mode handles only a confirmed fetch block as a successful job with a
notice and outcome=blocked. Publication must require outcome=ready.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import fetch

HERE = Path(__file__).resolve().parent
REPORT_PATH = HERE.parents[1] / ".local" / "reports" / "policy-refresh-status.json"
SITEMAPS = [
    "https://www.hdb.gov.sg/sitemap.xml",
    "https://www.mynicehome.gov.sg/sitemap.xml",
    "https://www.cpf.gov.sg/sitemap.xml",
]


def run(*args: str) -> None:
    print(f"\n>>> {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], cwd=HERE, check=True)


def pipeline() -> None:
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


def main(*, github_actions: bool = False) -> int:
    active = (fetch.ROOT / "data" / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
    report = {"date": fetch.SNAPSHOT_DATE, "active_snapshot": active,
              "outcome": "failed", "snapshot_ready": False,
              "started_at": datetime.now(timezone.utc).isoformat()}
    exit_code = 1
    try:
        if fetch.SNAPSHOT_DATE <= active:
            raise ValueError("Refusing to refresh the active or an older dated snapshot")
        pipeline()
    except subprocess.CalledProcessError as error:
        # Exit 2 is reserved by fetch.cli for an explicitly recorded source block.
        # Do not suppress exit 2 from another script or an ordinary script failure.
        if error.returncode == 2 and Path(error.cmd[1]).name == "fetch.py":
            blocked = fetch.load_log().get("blocked")
            if blocked:
                report.update(outcome="blocked", blocked=blocked)
                exit_code = 0 if github_actions else 2
            else:
                report["error"] = "Fetcher exited 2 without a recorded access block"
                traceback.print_exc()
        else:
            report["error"] = str(error)
            traceback.print_exc()
    except Exception as error:
        report["error"] = str(error)
        traceback.print_exc()
    else:
        report.update(outcome="ready", snapshot_ready=True)
        exit_code = 0

    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nPolicy refresh: {report['outcome']}; active snapshot remains {active}.")
    if github_actions:
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"outcome={report['outcome']}\ndate={fetch.SNAPSHOT_DATE}\n")
        if summary := os.getenv("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"## Policy refresh: {report['outcome']}\n\n"
                             f"Active snapshot retained: `{active}`.\n\n")
                if report["outcome"] == "blocked":
                    stream.write("Source access was blocked. No new snapshot will be published. "
                                 "See the diagnostic artifact for the URL and HTTP status.\n")
                elif report["outcome"] == "ready":
                    stream.write("The candidate snapshot completed. Activation still requires human review.\n")
                else:
                    stream.write("An unexpected error occurred. This job fails; no snapshot is published.\n")
        if report["outcome"] == "blocked":
            print("::notice title=Policy refresh blocked::Source access was denied or restricted; "
                  "retaining the previous active snapshot. No new snapshot was published. See diagnostics.")
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-actions", action="store_true")
    sys.exit(main(github_actions=parser.parse_args().github_actions))
