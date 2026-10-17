"""Add in-scope URLs from the cached sitemaps to seeds.json (no network).

Scope agreed with Sandra on 2026-10-15:
- every hdb.gov.sg page under /buying-a-flat/ (includes SC/SPR, non-citizen spouse,
  non-resident and EIP/SPR-quota rules, since the advisor serves non-Singaporeans too)
- mynicehome.gov.sg /get-started/ guides
- cpf.gov.sg /member/home-ownership/ pages
Policy PDFs linked from fetched pages are added separately (see `fetch.py pdfs`).

Usage: python discover.py [YYYY-MM-DD]
"""
from __future__ import annotations

import json
import re
import sys

from fetch import ROOT, SEEDS_PATH, SNAPSHOT_DATE

SCOPE = [
    ("www.hdb.gov.sg_sitemap.xml", r"^https://www\.hdb\.gov\.sg/buying-a-flat/.+", "hdb"),
    ("www.mynicehome.gov.sg_sitemap.xml", r"^https://www\.mynicehome\.gov\.sg/get-started/.+", "mnh"),
    ("www.cpf.gov.sg_sitemap.xml", r"^https://www\.cpf\.gov\.sg/member/home-ownership(/.*)?$", "cpf"),
]
# Interactive tools/calculators are out of scope (no forms, no calculators).
EXCLUDE = re.compile(r"home-purchase-planner$|calculator|e-service", re.I)


def slug_for(prefix: str, url: str) -> str:
    path = re.sub(r"^https://[^/]+/", "", url).strip("/")
    parts = [p for p in path.split("/") if p not in ("buying-a-flat", "member", "get-started")]
    return (prefix + "-" + "-".join(parts[-3:])).lower()[:90]


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else SNAPSHOT_DATE
    smap = ROOT / "data" / "policy_snapshots" / date / "sitemaps"
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    have_urls = {s["url"].rstrip("/") for s in seeds}
    have_slugs = {s["slug"] for s in seeds}
    added = 0
    for fname, pattern, prefix in SCOPE:
        locs = re.findall(r"<loc>([^<]+)</loc>", (smap / fname).read_text(encoding="utf-8"))
        for url in locs:
            url = url.strip()
            if not re.match(pattern, url) or EXCLUDE.search(url) or url.rstrip("/") in have_urls:
                continue
            slug = slug_for(prefix, url)
            while slug in have_slugs:
                slug += "-x"
            seeds.append({"slug": slug, "topic": "scope:sitemap", "url": url})
            have_urls.add(url.rstrip("/"))
            have_slugs.add(slug)
            added += 1
            print(f"+ {slug}  {url}")
    SEEDS_PATH.write_text(json.dumps(seeds, indent=2), encoding="utf-8")
    print(f"added {added}; seeds now {len(seeds)}")


if __name__ == "__main__":
    main()
