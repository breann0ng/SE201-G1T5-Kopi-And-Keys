"""Day 1 check: do the figures visible in raw HTML also appear in clean markdown?

Usage: python verify.py [YYYY-MM-DD]

For each page, collects dollar amounts ($X,XXX / $XK) and "N years" / "age N"
figures from (a) visible raw HTML text, (b) <script> payloads (hydration JSON,
which can hold content the static page hides), and (c) clean/<slug>.md, then
prints the differences. Writes verification.json next to the manifest.
"""
from __future__ import annotations

import json
import re
import sys

from bs4 import BeautifulSoup

from fetch import ROOT, SNAPSHOT_DATE

DOLLAR = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?[kKmM]\b)?")
YEARS = re.compile(r"\b\d{1,3}\s?(?:-\s?)?years?\b", re.I)
AGE = re.compile(r"\b(?:age(?:d)?|aged)\s+\d{2}\b", re.I)


def figures(text: str) -> set[str]:
    out = set()
    for rx in (DOLLAR, YEARS, AGE):
        out |= {re.sub(r"\s+", "", m.group(0)).lower() for m in rx.finditer(text)}
    return out


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else SNAPSHOT_DATE
    snap = ROOT / "data" / "policy_snapshots" / date
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    report = {}
    for p in manifest["pages"]:
        slug = p["slug"]
        md_path = snap / "clean" / f"{slug}.md"
        if not md_path.exists():
            continue
        if p.get("method") == "pdf":
            import pdfplumber

            with pdfplumber.open(snap / "raw" / f"{slug}.pdf") as doc:
                visible = figures(" ".join(pg.extract_text() or "" for pg in doc.pages))
            clean = figures(md_path.read_text(encoding="utf-8"))
            report[slug] = {"visible_in_raw": len(visible), "in_clean": len(clean),
                            "missing_from_clean": sorted(visible - clean),
                            "only_in_scripts_not_visible": [],
                            "in_clean_not_in_visible_raw": sorted(clean - visible)}
            print(f"\n== {slug} (pdf): raw={len(visible)} clean={len(clean)} "
                  f"missing={report[slug]['missing_from_clean']}")
            continue
        rendered = snap / "raw" / f"{slug}.rendered.html"
        raw = rendered if rendered.exists() else snap / "raw" / f"{slug}.html"
        soup = BeautifulSoup(raw.read_text(encoding="utf-8", errors="replace"), "lxml")
        scripts = " ".join(s.get_text(" ") for s in soup.find_all("script"))
        if p.get("method") == "nextdata":
            # Content source is the page's __NEXT_DATA__; compare its full text
            # (HTML tags stripped) so skipped components would show up below.
            nd = soup.find("script", id="__NEXT_DATA__").string
            scripts = BeautifulSoup(json.loads(json.dumps(nd)), "lxml").get_text(" ")
            soup = BeautifulSoup((snap / "derived" / f"{slug}.html").read_text(encoding="utf-8"), "lxml")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        visible = figures(soup.get_text(" "))
        script_only = figures(scripts) - visible
        clean = figures(md_path.read_text(encoding="utf-8"))
        report[slug] = {
            "visible_in_raw": len(visible),
            "in_clean": len(clean),
            "missing_from_clean": sorted(visible - clean),
            "only_in_scripts_not_visible": sorted(script_only),
            "in_clean_not_in_visible_raw": sorted(clean - visible),
        }
        r = report[slug]
        print(f"\n== {slug}: raw-visible={r['visible_in_raw']} clean={r['in_clean']}")
        for k in ("missing_from_clean", "only_in_scripts_not_visible", "in_clean_not_in_visible_raw"):
            if r[k]:
                print(f"  {k}: {r[k]}")
    (snap / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
