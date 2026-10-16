"""Extract clean markdown, tables and a manifest from cached raw HTML (no network).

Usage: python extract.py [YYYY-MM-DD]   (defaults to today's SGT snapshot)

Prefers raw/<slug>.rendered.html (Playwright) over raw/<slug>.html when present.
Figures are never edited: clean text is exactly what trafilatura/BeautifulSoup
pull from the page.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from fetch import ROOT, SNAPSHOT_DATE

THIN_WORDS = 200
# Source ranking for retrieval/citation (1 = most authoritative). Decided by Person 4,
# 2026-10-15: explainer articles rank below official scheme pages.
SOURCE_TIERS = [
    ("https://www.hdb.gov.sg/", 1, "HDB official scheme page / HDB-published PDF"),
    ("https://www.cpf.gov.sg/member/home-ownership", 1, "CPF official scheme page"),
    ("https://www.mynicehome.gov.sg/", 2, "HDB MyNiceHome guide (summary of scheme pages)"),
    ("https://www.cpf.gov.sg/member/infohub/", 3, "CPF explainer article (infohub)"),
]


def source_tier(url: str | None) -> tuple[int | None, str | None]:
    for prefix, tier, label in SOURCE_TIERS:
        if url and url.startswith(prefix):
            return tier, label
    return None, None
# Verbatim "last updated"-style phrases; captured as printed, never normalised.
DATE_PATTERNS = [
    r"(?:Last\s+updated|Last\s+modified|Updated\s+on|Page\s+last\s+updated|Effective\s+(?:from|date)|With\s+effect\s+from)"
    r"\s*:?\s*(?:on\s+)?\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}",
]


def page_title(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    return soup.title.get_text(strip=True) if soup.title else None


def printed_dates(soup: BeautifulSoup) -> list[str]:
    text = soup.get_text(" ", strip=True)
    found: list[str] = []
    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            if m.group(0) not in found:
                found.append(m.group(0))
    return found


def extract_tables(soup: BeautifulSoup, slug: str, out_dir: Path) -> list[str]:
    written = []
    for n, table in enumerate(soup.find_all("table"), start=1):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        path = out_dir / f"{slug}_{n}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        written.append(path.name)
    return written


def pdf_extract(path: Path, slug: str, out_dir: Path) -> tuple[str, list[str]]:
    """Page text verbatim (one '## Page n' section per page) plus every table as CSV."""
    import pdfplumber

    pages, written, n = [], [], 0
    with pdfplumber.open(path) as doc:
        for i, page in enumerate(doc.pages, start=1):
            pages.append(f"## Page {i}\n\n{page.extract_text() or ''}")
            for table in page.extract_tables():
                n += 1
                out = out_dir / f"{slug}_{n}.csv"
                with out.open("w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows([[c or "" for c in row] for row in table])
                written.append(out.name)
    return "\n\n".join(pages), written


def pdf_title(text: str) -> str | None:
    """First text line of the PDF (joining a title that wraps on a trailing hyphen)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("## Page")]
    if not lines:
        return None
    title = lines[0]
    if title.endswith("-") and len(lines) > 1:
        title += lines[1]
    return title


def to_markdown(html: str, url: str | None) -> str:
    return trafilatura.extract(html, output_format="markdown", include_tables=True,
                               include_links=False, favor_recall=True, url=url) or ""


# Sitecore components whose fields are page content. Others (nav cards, banners)
# are skipped and named in the notes so nothing disappears silently.
CONTENT_COMPONENTS = {"PageHeader", "BodyContent", "AccordionWrapper"}


def sitecore_body(soup: BeautifulSoup) -> tuple[str, str, str | None] | None:
    """Rebuild page body HTML, in component order, from HDB's __NEXT_DATA__."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    props = json.loads(tag.string).get("props", {}).get("pageProps", {})
    route = (props.get("layoutData") or {}).get("sitecore", {}).get("route")
    if not route:
        return None
    comp_props = props.get("componentProps") or {}
    parts, skipped = [], []
    title = ((route.get("fields") or {}).get("pageTitle") or {}).get("value")

    def walk(placeholders: dict) -> None:
        for items in placeholders.values():
            for c in items:
                name, fields = c.get("componentName"), c.get("fields") or {}
                if name == "PageHeader":
                    parts.append(f"<h1>{title or ''}</h1>")
                    desc = (fields.get("pageDescrition") or {}).get("value")
                    if desc:
                        parts.append(f"<p>{desc}</p>")
                elif name == "BodyContent":
                    parts.append((fields.get("bodyContent") or {}).get("value") or "")
                elif name == "AccordionWrapper":
                    items_ = (comp_props.get(c.get("uid")) or {}).get("props", {}).get("accordionItems", [])
                    for a in items_:
                        parts.append(f"<h2>{a.get('titleVal') or ''}</h2>")
                        if a.get("descVal"):
                            parts.append(f"<p>{a['descVal']}</p>")
                        parts.append(a.get("bodyContentVal") or "")
                elif name and name not in skipped:
                    skipped.append(name)
                if c.get("placeholders"):
                    walk(c["placeholders"])

    walk(route.get("placeholders") or {})
    html = "<html><body><article>" + "\n".join(parts) + "</article></body></html>"
    note = f" Skipped non-content components: {skipped}." if skipped else ""
    return html, note, title


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else SNAPSHOT_DATE
    snap = ROOT / "data" / "policy_snapshots" / date
    log = json.loads((snap / "fetch_log.json").read_text(encoding="utf-8"))
    clean_dir, table_dir = snap / "clean", snap / "tables"
    clean_dir.mkdir(exist_ok=True)
    table_dir.mkdir(exist_ok=True)

    # Hand-written observations per slug (kept separate so reruns don't lose them).
    notes_path = snap / "notes.json"
    manual_notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    manifest = []
    for slug, info in log["pages"].items():
        entry = {
            "slug": slug,
            "final_url": info.get("final_url"),
            "requested_url": info["requested_url"],
            "fetched_at": info.get("fetched_at"),
            "http_status": info.get("http_status"),
            "method": None,
            "robots_allowed": info.get("robots_allowed"),
            "page_title": None,
            "word_count": 0,
            "sha256": info.get("sha256"),
            "last_updated_printed": None,
            "tables": [],
            "source_tier": source_tier(info.get("final_url") or info["requested_url"])[0],
            "source_tier_label": source_tier(info.get("final_url") or info["requested_url"])[1],
            "notes": " ".join(filter(None, [info.get("notes", ""), manual_notes.get(slug, "")])),
        }
        pdf = snap / "raw" / f"{slug}.pdf"
        if pdf.exists():
            text, tables = pdf_extract(pdf, slug, table_dir)
            (clean_dir / f"{slug}.md").write_text(
                f"Source: {entry['final_url']}\nSnapshot: {date}\n\n{text}", encoding="utf-8")
            entry.update(method="pdf", sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                         page_title=pdf_title(text),
                         word_count=len(text.split()), tables=tables)
            entry["notes"] = entry["notes"].strip()
            manifest.append(entry)
            print(f"{slug}: pdf {entry['word_count']} words, {len(tables)} tables")
            continue
        rendered = snap / "raw" / f"{slug}.rendered.html"
        raw = rendered if rendered.exists() else snap / "raw" / f"{slug}.html"
        if not raw.exists():
            manifest.append(entry)
            continue
        html = raw.read_text(encoding="utf-8", errors="replace")
        entry["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        entry["method"] = "playwright" if rendered.exists() else "trafilatura"
        soup = BeautifulSoup(html, "lxml")
        md = to_markdown(html, entry["final_url"])
        title = page_title(soup)
        body = sitecore_body(soup)
        if body:
            # Sitecore pages ship the real body in __NEXT_DATA__ (static HTML is mostly nav),
            # so always rebuild from it when present, not only when the static text is thin.
            derived_html, comp_notes, title = body
            (snap / "derived").mkdir(exist_ok=True)
            (snap / "derived" / f"{slug}.html").write_text(derived_html, encoding="utf-8")
            soup = BeautifulSoup(derived_html, "lxml")
            md = to_markdown(derived_html, entry["final_url"])
            entry["method"] = "nextdata"
            entry["notes"] += (" Body rebuilt from the page's embedded "
                               "__NEXT_DATA__ (Sitecore layout) into derived/" + slug + ".html."
                               + comp_notes)
        meta = f"Source: {entry['final_url']}\nSnapshot: {date}\n\n"
        header = meta if md.lstrip().startswith("# ") or not title else f"# {title}\n\n{meta}"
        (clean_dir / f"{slug}.md").write_text(header + md, encoding="utf-8")
        entry["page_title"] = title
        entry["word_count"] = len(md.split())
        dates = printed_dates(soup)
        entry["last_updated_printed"] = dates[0] if dates else None
        if len(dates) > 1:
            entry["notes"] += f" Multiple date phrases printed: {dates}."
        entry["tables"] = extract_tables(soup, slug, table_dir)
        if entry["word_count"] < THIN_WORDS:
            entry["notes"] += f" THIN: {entry['word_count']} words (<{THIN_WORDS})."
        entry["notes"] = entry["notes"].strip()
        manifest.append(entry)
        print(f"{slug}: {entry['method']} {entry['word_count']} words, "
              f"{len(entry['tables'])} tables, date={entry['last_updated_printed']!r}")

    out = {"snapshot_date": date, "timezone": "Asia/Singapore (+08:00)",
           "robots": log["robots"], "fetch_count": log["fetch_count"], "pages": manifest}
    (snap / "manifest.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
