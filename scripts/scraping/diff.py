"""Compare two policy snapshots and report what changed, for human review.

Usage: python diff.py [OLD_DATE NEW_DATE]
Default: OLD = the snapshot named in data/policy_snapshots/ACTIVE (what the advisor
serves), NEW = the most recent snapshot.

Compares clean text, not raw HTML: raw hashes change on every site deploy
(build IDs, nonces) even when the policy wording is identical. The Source/Snapshot
header lines are ignored for the same reason.

Writes data/policy_snapshots/<NEW>/changes_since_<OLD>.{json,md}. Nothing is
marked superseded automatically; a person reviews the report first.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

from fetch import ROOT
from verify import figures

SNAPS = ROOT / "data" / "policy_snapshots"
MAX_DIFF_LINES = 40


def body(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [ln for ln in lines if not ln.startswith(("Source: ", "Snapshot: "))]


def load(date: str) -> tuple[dict, Path]:
    snap = SNAPS / date
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    return {p["slug"]: p for p in manifest["pages"]}, snap


def main() -> None:
    if len(sys.argv) == 3:
        old_date, new_date = sys.argv[1], sys.argv[2]
    else:
        dates = sorted(d.name for d in SNAPS.iterdir() if (d / "manifest.json").exists())
        new_date = dates[-1] if dates else None
        # Compare against what users are served (ACTIVE), not merely the previous folder.
        active = (SNAPS / "ACTIVE").read_text(encoding="utf-8").strip() if (SNAPS / "ACTIVE").exists() else None
        old_date = active if active in dates and active != new_date else (dates[-2] if len(dates) > 1 else None)
        if not old_date or not new_date:
            raise SystemExit(f"Need two snapshots to compare; found {dates}")
    old, old_dir = load(old_date)
    new, new_dir = load(new_date)

    report = {"old": old_date, "new": new_date, "added": [], "removed": [],
              "changed": [], "status_changed": [], "unchanged": 0}
    for slug in sorted(set(old) | set(new)):
        if slug not in new:
            report["removed"].append({"slug": slug, "url": old[slug].get("final_url")})
            continue
        if slug not in old:
            report["added"].append({"slug": slug, "url": new[slug].get("final_url")})
            continue
        o, n = old[slug], new[slug]
        if o.get("http_status") != n.get("http_status") or o.get("final_url") != n.get("final_url"):
            report["status_changed"].append({
                "slug": slug, "old_status": o.get("http_status"), "new_status": n.get("http_status"),
                "old_url": o.get("final_url"), "new_url": n.get("final_url")})
        a, b = body(old_dir / "clean" / f"{slug}.md"), body(new_dir / "clean" / f"{slug}.md")
        if hashlib.sha256("\n".join(a).encode()).digest() == hashlib.sha256("\n".join(b).encode()).digest():
            report["unchanged"] += 1
            continue
        fa, fb = figures("\n".join(a)), figures("\n".join(b))
        diff = list(difflib.unified_diff(a, b, lineterm="", n=0))[2:]
        report["changed"].append({
            "slug": slug, "url": n.get("final_url"), "source_tier": n.get("source_tier"),
            "figures_removed": sorted(fa - fb), "figures_added": sorted(fb - fa),
            "page_last_updated": [o.get("last_updated_printed"), n.get("last_updated_printed")],
            "diff_excerpt": diff[:MAX_DIFF_LINES], "diff_truncated": len(diff) > MAX_DIFF_LINES,
        })
    # Figure changes first: those are what can make a cited answer wrong.
    report["changed"].sort(key=lambda c: (not (c["figures_removed"] or c["figures_added"]),
                                          c["source_tier"] or 9, c["slug"]))

    stem = new_dir / f"changes_since_{old_date}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stem.with_suffix(".md").write_text(render(report), encoding="utf-8")
    print(f"{old_date} -> {new_date}: {len(report['changed'])} changed "
          f"({sum(1 for c in report['changed'] if c['figures_removed'] or c['figures_added'])} with figure changes), "
          f"{len(report['added'])} added, {len(report['removed'])} removed, "
          f"{len(report['status_changed'])} status/URL changes, {report['unchanged']} unchanged")
    print(f"report: {stem.with_suffix('.md')}")


def render(r: dict) -> str:
    out = [f"# Policy changes {r['old']} -> {r['new']}", "",
           "Review each item. If a change is real, mark the old chunks `superseded: true` "
           "and load the new snapshot's chunks. Nothing here was applied automatically.", "",
           f"- Changed: {len(r['changed'])}  - Added: {len(r['added'])}  - Removed: {len(r['removed'])}"
           f"  - Status/URL changes: {len(r['status_changed'])}  - Unchanged: {r['unchanged']}", ""]
    if r["changed"]:
        out += ["## Changed pages (figure changes first)", ""]
        for c in r["changed"]:
            out += [f"### {c['slug']} (tier {c['source_tier']})", c["url"] or "", ""]
            if c["figures_removed"] or c["figures_added"]:
                out += [f"- **Figures removed:** {', '.join(c['figures_removed']) or 'none'}",
                        f"- **Figures added:** {', '.join(c['figures_added']) or 'none'}"]
            out += [f"- Page 'last updated': {c['page_last_updated'][0]} -> {c['page_last_updated'][1]}",
                    "", "```diff", *c["diff_excerpt"],
                    *(["... (truncated; see the JSON or the clean files)"] if c["diff_truncated"] else []),
                    "```", ""]
    for key, title in (("status_changed", "HTTP status / URL changes"),
                       ("added", "New pages"), ("removed", "Pages no longer captured")):
        if r[key]:
            out += [f"## {title}", ""] + [f"- `{x['slug']}`: {json.dumps({k: v for k, v in x.items() if k != 'slug'})}"
                                          for x in r[key]] + [""]
    return "\n".join(out)


if __name__ == "__main__":
    main()
