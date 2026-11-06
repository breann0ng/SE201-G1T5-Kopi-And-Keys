"""Report policy-source freshness; optionally prepare an INACTIVE candidate PR.

Run refresh.py first. Default mode writes local reports only:
    python scripts/policy_watch.py
Only --publish uses git/gh to notify maintainers. Never writes ACTIVE, chunks,
topic cards or the vector index. A failed check never means unchanged policy.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTENTION_TITLE = "Policy watcher needs attention"
MARKER = "<!-- kopi-keys-policy-watcher -->"
BRANCH_PREFIX = "automation/policy-snapshot-"
CHANGE_KEYS = ("changed", "added", "removed", "status_changed")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_date(value: str) -> str:
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Expected a snapshot date in YYYY-MM-DD format")
    return value


def inspect(root: Path = ROOT) -> dict:
    """Fail closed on absent/mismatched reports, incomplete fetches or missing diffs."""
    result = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "status": "failed", "active_unchanged": True}
    try:
        active = snapshot_date((root / "data/policy_snapshots/ACTIVE").read_text().strip())
        result["active_snapshot"] = active
        source = read_json(root / ".local/reports/policy-refresh-status.json")
        candidate = snapshot_date(source["date"])
        result.update(candidate_snapshot=candidate, source_checked_at=source.get("checked_at"))
        if source["active_snapshot"] != active:
            raise ValueError("ACTIVE changed since this refresh; run a new check")
        if source["outcome"] == "blocked":
            result.update(status="blocked", detail=source.get("blocked", {}))
            return result
        if source["outcome"] != "ready" or source.get("snapshot_ready") is not True:
            raise ValueError(source.get("error", "Refresh did not finish successfully"))
        if candidate <= active:
            raise ValueError("Candidate must be newer than ACTIVE; dated snapshots are immutable")
        folder = root / "data/policy_snapshots" / candidate
        manifest = read_json(folder / "manifest.json")
        if manifest["snapshot_date"] != candidate or not manifest["pages"]:
            raise ValueError("Candidate manifest is empty or names another snapshot")
        pages = manifest["pages"]
        if len({p["slug"] for p in pages}) != len(pages):
            raise ValueError("Duplicate page slugs in manifest")
        seeds = read_json(root / "scripts/scraping/seeds.json")
        pdfs = read_json(root / "scripts/scraping/pdf_seeds.json")
        expected = {p["slug"] for p in seeds + pdfs}
        captured = {p["slug"] for p in pages}
        incomplete = sorted(expected - captured)
        for page in pages:
            slug = page["slug"]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
                raise ValueError("Unsafe source slug in manifest")
            clean = folder / "clean" / f"{slug}.md"
            if (page.get("http_status") != 200 or not page.get("method")
                    or page.get("word_count", 0) < 1 or not clean.is_file()):
                incomplete.append(slug)
        if incomplete:
            result.update(status="incomplete", detail={"pages": sorted(set(incomplete))})
            return result
        verification = read_json(folder / "verification.json")
        if captured - set(verification):
            raise ValueError("Missing extraction verification records")
        # Figure-set comparison is diagnostic, not proof of semantic correctness.
        result["figure_warnings"] = sorted(
            slug for slug, entry in verification.items() if entry.get("missing_from_clean"))
        diff = read_json(folder / f"changes_since_{active}.json")
        if diff["old"] != active or diff["new"] != candidate:
            raise ValueError("Diff is for another pair of snapshots")
        if any(not isinstance(diff[key], list) for key in CHANGE_KEYS):
            raise ValueError("Malformed diff categories")
        counts = {key: len(diff[key]) for key in CHANGE_KEYS}
        result.update(status="changed" if any(counts.values()) else "unchanged",
                      counts=counts, pages_checked=len(pages))
        if result["figure_warnings"]:
            result["status"] = "incomplete"
            result["detail"] = {"figure_warnings": result["figure_warnings"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result.update(status="failed", detail=str(error))
    return result


def run(root: Path, *args: str) -> str:
    # No shell interpolation: URLs, dates and messages remain arguments, not code.
    return subprocess.run(args, cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def attention(root: Path, repo: str, body: str) -> str:
    """Update one open alert rather than creating another on every blocked run."""
    issues = json.loads(run(root, "gh", "issue", "list", "--repo", repo,
                            "--state", "open", "--search", f'"{ATTENTION_TITLE}" in:title',
                            "--limit", "100", "--json", "number,title,body,url"))
    path = root / ".local/reports/policy-watch-issue.md"
    path.write_text(f"{MARKER}\n\n{body}\n", encoding="utf-8")
    for issue in issues:
        if issue["title"] == ATTENTION_TITLE and MARKER in (issue.get("body") or ""):
            run(root, "gh", "issue", "edit", str(issue["number"]), "--repo", repo,
                "--body-file", str(path))
            return issue["url"]
    return run(root, "gh", "issue", "create", "--repo", repo,
               "--title", ATTENTION_TITLE, "--body-file", str(path))


def publish(report: dict, root: Path = ROOT) -> dict:
    repo = os.environ["GITHUB_REPOSITORY"]
    base = os.environ["POLICY_DEFAULT_BRANCH"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("Invalid GitHub repository")
    run_url = (f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/"
               f"{os.environ['GITHUB_RUN_ID']}")
    body = (f"Latest check: **{report['status']}**\n\n"
            f"Active snapshot retained: `{report.get('active_snapshot', 'unknown')}`.\n\n"
            f"[Workflow run and evidence artifacts]({run_url})\n\n")
    if report["status"] not in ("changed", "unchanged"):
        body += ("This is not a successful freshness check. Review the diagnostic artifact; "
                 "a blocked, missing or broken page is not evidence of unchanged policy. "
                 "Do not bypass access restrictions or activate incomplete data.\n\n"
                 f"Diagnostic: {json.dumps(report.get('detail'), ensure_ascii=True)}")
        return {"attention_issue": attention(root, repo, body)}
    if report["status"] == "unchanged":
        # Earlier alerts still need a human to review their history and close them.
        return {"publication": "none; checked content unchanged"}
    pending = json.loads(run(root, "gh", "pr", "list", "--repo", repo, "--state", "open",
                             "--base", base, "--limit", "100", "--json", "headRefName,url"))
    existing = next((pr for pr in pending if pr["headRefName"].startswith(BRANCH_PREFIX)), None)
    if existing:
        body += (f"A policy candidate is already awaiting review: {existing['url']}. "
                 "Compare this run's evidence before proceeding; the pending PR may be older. "
                 "This check did not overwrite it or create another PR.")
        return {"pending_pr": existing["url"], "attention_issue": attention(root, repo, body)}
    candidate = snapshot_date(report["candidate_snapshot"])
    branch = f"{BRANCH_PREFIX}{candidate}-{os.environ['GITHUB_RUN_ID']}"
    paths = [f"data/policy_snapshots/{candidate}", "scripts/scraping/seeds.json"]
    if run(root, "git", "diff", "--cached", "--name-only"):
        raise ValueError("Refusing to commit unrelated staged changes")
    run(root, "git", "switch", "-c", branch)
    run(root, "git", "config", "user.name", "github-actions[bot]")
    run(root, "git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run(root, "git", "add", "--", *paths)
    run(root, "git", "commit", "-m", f"data: stage policy snapshot {candidate} for review")
    run(root, "git", "push", "origin", f"HEAD:refs/heads/{branch}")
    body += (f"Candidate: `{candidate}`. Change counts: `{json.dumps(report['counts'])}`.\n\n"
             "**Merging this PR does not activate it.** ACTIVE, chunks, topic cards and the "
             "index are unchanged. This is change detection, not an eligibility certification.\n\n"
             "- [ ] Read the complete diff and original official pages/PDFs; inspect conditions "
             "and table labels, not just amounts.\n"
             "- [ ] Check extraction quality, effective dates, redirects and missing pages.\n"
             "- [ ] Record reviewer, date, findings and unresolved issues in the candidate README.\n"
             "- [ ] Approve the bot PR's CI workflows if GitHub requests approval; require passing CI.\n"
             "- [ ] Keep the evaluation snapshot fixed during held-out evaluation.\n\n"
             "Activation is a separate reviewed change: follow `docs/policy-watcher.md`, "
             "regenerate/validate chunks and topic cards, rebuild the index and restart the backend.")
    path = root / ".local/reports/policy-watch-pr.md"
    path.write_text(body, encoding="utf-8")
    url = run(root, "gh", "pr", "create", "--repo", repo, "--draft", "--base", base,
              "--head", branch, "--title", f"data: review policy snapshot {candidate} (inactive)",
              "--body-file", str(path))
    return {"candidate_pr": url}


def main(*, do_publish: bool = False, root: Path = ROOT) -> int:
    report = inspect(root)
    folder = root / ".local/reports"
    folder.mkdir(parents=True, exist_ok=True)
    if do_publish:
        try:
            report.update(publish(report, root))
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            report["publication_error"] = str(error)
    (folder / "policy-watch-status.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"\n## Policy watcher: {report['status']}\n\n"
                         f"ACTIVE retained: `{report.get('active_snapshot', 'unknown')}`. "
                         "See policy-watch-status.json for source status, review links and errors.\n")
    return 1 if report["status"] == "failed" or "publication_error" in report else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Notify GitHub and prepare a draft PR")
    raise SystemExit(main(do_publish=parser.parse_args().publish))
