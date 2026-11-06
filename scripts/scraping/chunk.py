"""Chunk a policy snapshot's clean markdown into chunks.jsonl (no network).

Usage: python chunk.py [YYYY-MM-DD]   (default: the date in data/policy_snapshots/ACTIVE)

Rules:
- split by heading (markdown #..###, plus whole-line bold labels used as headings);
  a heading ending in ':' ("### What you need to do:") is a sub-label, not a
  section: it stays in the text with the block it introduces
- sections over ~300 words are split between blocks; a block (paragraph, list or
  table) is never split, and a line ending in ':' stays with the block after it,
  so a figure is not separated from the condition it depends on
- two tables never share a chunk, and a table keeps its caption line; a table
  whose bold header row lacks the |---| divider gets one (headerless tables are
  left as they are); a table row too long for a chunk is split between sentences
  of its longest cell, repeating the header and the row's first cell
- chunk words are copied verbatim from clean/<slug>.md; only table markup
  (divider rows, repeated header/label cells) is added
- chunk_id = CHUNK_<POLICY>_<NN>; ids are kept stable across reruns via
  data/policy_chunks/chunk_id_registry.json (same page + heading + content -> same id)
- eligibility_tags are added only on explicit wording matches, using data/schema/vocab.json values
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date as Date

from fetch import ROOT

SNAPS = ROOT / "data" / "policy_snapshots"
CHUNKS = ROOT / "data" / "policy_chunks"
REGISTRY = CHUNKS / "chunk_id_registry.json"
VOCAB = ROOT / "data" / "schema" / "vocab.json"
TARGET_WORDS = 300
MIN_WORDS = 8

# slug pattern -> (POLICY code, policy_name). First match wins.
POLICIES = [
    (r"ehg", "EHG", "Enhanced CPF Housing Grant (EHG)"),
    (r"^hdb-grant-family-cpf-housing-grants$", "FAMILY", "CPF Housing Grant for Resale Flats (Families)"),
    (r"^hdb-grant-singles-cpf-housing-grant$", "SINGLES", "CPF Housing Grant for Resale Flats (Singles)"),
    (r"proximity|phg", "PHG", "Proximity Housing Grant (PHG)"),
    (r"stepup", "STEPUP", "Step-Up CPF Housing Grant"),
    (r"^mnh-hdb-grants-guide$", "GRANTS", "CPF housing grants (overview)"),
    (r"income-ceiling|income-guidelines|hfe-letter-inc$", "INCOME", "Income ceilings and income assessment"),
    (r"hfe", "HFE", "HDB Flat Eligibility (HFE) letter"),
    (r"eip-and-spr-quota", "EIP", "Ethnic Integration Policy (EIP) and SPR quota"),
    (r"^hdb-resale-mode-of-financing$|^cpf-how-much-cpf-for-home-purchase$", "LEASE",
     "Remaining lease, CPF usage and financing for resale flats"),
    (r"housing-loan|loans-guide", "LOAN", "HDB housing loan and bank loans"),
    (r"^hdb-elig-|^mnh-hdb-buying-guide-(singles|young-couples|seniors)$|eligibility-seniors$",
     "ELIG", "Flat eligibility (citizenship, household, age)"),
    (r"^hdb-pdf-(otp|resale|ecf)|resale", "RESALE", "Buying a resale flat (process, OTP, deposit)"),
    (r"executive-condominium", "EC", "Executive Condominiums (EC)"),
    (r"bto|new-flat|sales-launch|priority|flat-types|types-of-flats", "BTO", "Buying a new flat (BTO/SBF)"),
    (r"financial-planning", "FINANCE", "Financial planning for a flat purchase"),
    (r"^cpf-", "CPF", "Using CPF for housing"),
    (r".*", "GENERAL", "HDB flat buying (general)"),
]

# The CPF site banner is page chrome, not policy content.
DROP_PARAGRAPHS = [re.compile(r"^\*\*Notice\*\*$"),
                   re.compile(r"^Our CPF hotlines are temporarily unavailable")]

# Explicit wording -> (vocab field, canonical value). Only literal mentions count.
TAG_RULES = [
    (r"\bSC/ ?SC\b", "citizenship", "SC/SC"),
    (r"\bSC/ ?SPR\b", "citizenship", "SC/SPR"),
    (r"\bSPR household|\bSPR/ ?SPR\b", "citizenship", "SPR/SPR"),
    (r"non-resident spouse", "citizenship", "SC/NR"),
    (r"\bsingle (Singapore )?citizens?\b|first-timer singles?\b", "citizenship", "SC_single"),
    # Scheme names ("Family Grant", "Singles Grant", "core family nucleus") are not household types.
    (r"\bcouples?\b|\bfamilies\b|\bmarried\b|\bfamily\b(?! Grant| nucleus)", "household_type", "couple_family"),
    (r"fianc", "household_type", "fiance"),
    (r"\bsingles?\b(?! Grant)", "household_type", "single"),
    (r"extended (or multi-generation )?famil|multi-generation famil", "household_type", "extended_family"),
    (r"\bseniors?\b", "household_type", "senior"),
    (r"first-timer", "first_timer", "true"),
    (r"second-timer", "first_timer", "false"),
    (r"\b1-room\b", "flat_type", "1-room"),
    (r"\b2-room\b(?! Flexi)|2- to [345]-room|2 to 5-room", "flat_type", "2-room"),
    (r"\b3-room\b|2- to [45]-room|2 to 5-room", "flat_type", "3-room"),
    (r"\b4-room\b|2- to 4-room|2 to 5-room", "flat_type", "4-room"),
    (r"\b5-room\b|2 to 5-room", "flat_type", "5-room"),
    (r"\bExecutive flat", "flat_type", "executive"),
    (r"2-room Flexi", "flat_type", "2-room-flexi"),
    (r"\b3Gen\b", "flat_type", "3gen"),
]

HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
BOLD_LINE = re.compile(r"^\*\*([^*]{2,120})\*\*:?$")
EFFECTIVE = re.compile(
    r"\b(?:[Ww]ith effect from|[Ee]ffective (?:from )?|From)\s+(\d{1,2} (?:January|February|March|April|May|June|"
    r"July|August|September|October|November|December) \d{4})")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                      "August", "September", "October", "November", "December"], 1)}


def policy_for(slug: str) -> tuple[str, str]:
    for pattern, code, name in POLICIES:
        if re.search(pattern, slug):
            return code, name
    raise AssertionError(slug)


def pdf_page_title(block: str, root: str) -> str | None:
    """A PDF page's own title, when it names a variant of the document's title.

    The EHG Singles PDF has one table per page ("... amount for applicant with
    non-resident spouse", "... amount for two or more first-timer singles"), but every
    page was headed with page 1's title. The title is the first line plus the wrapped
    lines that start in lower case. It is used only if it starts like the document title
    and differs from it, so numbered clauses ("6 Housing Loan") and repeated headers
    keep "<document title> > Page n".
    """
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if not lines:
        return None
    title = lines[0]
    for line in lines[1:]:
        if not line[0].islower():
            break
        title += line if title.endswith("-") else " " + line
    words = lambda t: " ".join(t.replace(")", ") ").split()).casefold().split()
    if words(title)[:3] != words(root)[:3] or words(title) == words(root) or len(words(title)) > 25:
        return None
    return title


def sections(md: str, root: str | None = None) -> list[tuple[str, list[str]]]:
    """[(heading path, blocks)] — blocks are blank-line separated, verbatim.

    root: optional level-0 title (used for PDFs, whose headings are just 'Page n').
    """
    out: list[tuple[str, list[str]]] = []
    path: list[tuple[int, str]] = [(0, root)] if root else []
    blocks: list[str] = []
    cur: list[str] = []

    def flush_block():
        if cur:
            text = "\n".join(cur).strip()
            if text and not any(p.match(text) for p in DROP_PARAGRAPHS):
                blocks.append(text)
            cur.clear()

    def flush_section():
        flush_block()
        if blocks:
            titles = [t for _, t in path]
            page_title = pdf_page_title(blocks[0], root) if root and titles[-1].startswith("Page ") else None
            if page_title:
                titles = [page_title, titles[-1]]
            out.append((" > ".join(titles), blocks.copy()))
            blocks.clear()

    for line in md.splitlines():
        if line.startswith(("Source: ", "Snapshot: ")):
            continue
        m = HEADING.match(line)
        b = BOLD_LINE.match(line.strip()) if not m else None
        if is_sub_label(line):
            flush_block()  # its own block ending in ':', so pack() joins it to what follows
            cur.append(line)
            flush_block()
            continue
        if m or (b and len(b.group(1).split()) <= 15):
            flush_section()
            level = len(m.group(1)) if m else 4
            title = (m.group(2) if m else b.group(1)).strip("* ").strip()
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            continue
        if not line.strip():
            flush_block()
        else:
            cur.append(line)
    flush_section()
    return out


def is_sub_label(line: str) -> bool:
    """A heading or bold line ending in ':' ("### What you need to do:"): it introduces
    the block below it, so it is kept as text rather than starting a new section."""
    m = HEADING.match(line)
    b = BOLD_LINE.match(line.strip()) if not m else None
    title = m.group(2) if m else b.group(1) if b else None
    return title is not None and (title.rstrip("* ").endswith(":") or line.rstrip().endswith(":"))


DIVIDER = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
SENTENCE_END = re.compile(r"(?<=[.?!])\s+(?=\S)")


def table_rows(block: str) -> list[str] | None:
    """The block's table rows, or None if it is not a table. A cell can hold line
    breaks, so a row runs from a line starting with '|' to a line ending with '|'."""
    rows: list[str] = []
    for line in block.split("\n"):
        if rows and not rows[-1].rstrip().endswith("|"):
            rows[-1] += "\n" + line
        elif line.lstrip().startswith("|"):
            rows.append(line)
        else:
            return None
    return rows or None


def is_table(block: str) -> bool:
    return table_rows(block) is not None


def has_table(block: str) -> bool:
    return any(ln.lstrip().startswith("|") for ln in block.split("\n"))


def cells(row: str) -> list[str]:
    inner = row.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip() for c in inner.split("|")]


def row_text(cols: list[str]) -> str:
    return "| " + " | ".join(cols) + " |"


def is_header_row(row: str) -> bool:
    """Every non-empty cell is bold ("| **Household Type** | **Grant Amount** |").
    A first row like "| **Citizenship** | At least 1 applicant ... |" is data."""
    filled = [c for c in cells(" ".join(row.split("\n"))) if c]
    return bool(filled) and all(re.fullmatch(r"\*\*[^*]+\*\*", c) for c in filled)


def with_divider(block: str) -> str:
    """Add the |---| row a table's header needs, if the extractor left it out.

    Headerless tables are left as they are: a divider would turn their first data
    row into column names (policy_synthesis.model_evidence reads row 1 as headers).
    """
    rows = table_rows(block)
    if rows is None or len(rows) < 2 or DIVIDER.match(rows[1].strip()) or not is_header_row(rows[0]):
        return block
    return "\n".join([rows[0], row_text(["---"] * len(cells(rows[0])))] + rows[1:])


def is_caption(block: str) -> bool:
    """A one-line table title ("Enhanced CPF Housing Grant Amount Based on Household Type")."""
    text = block.strip()
    return ("\n" not in text and not has_table(text) and len(text.split()) <= 15
            and not text.endswith((".", "?", "!", ":")))


def split_row(row: str, head_words: int) -> list[str]:
    """A table row too long for one chunk, split between sentences of its longest cell.

    Continuation rows repeat the first cell (the row's label) and leave other cells
    empty; every sentence stays verbatim and whole.
    """
    if len(row.split()) + head_words <= TARGET_WORDS:
        return [row]
    cols = cells(" ".join(row.split("\n")))  # a split row is rewritten on one line
    if len(cols) < 2:
        return [row]
    longest = max(range(len(cols)), key=lambda i: len(cols[i].split()))
    sentences = SENTENCE_END.split(cols[longest])
    budget = TARGET_WORDS - head_words - sum(len(c.split()) for i, c in enumerate(cols) if i != longest)
    pieces, cur = [], []
    for s in sentences:
        if cur and len(" ".join(cur + [s]).split()) > max(budget, 50):
            pieces.append(" ".join(cur))
            cur = []
        cur.append(s)
    pieces.append(" ".join(cur))
    rows = []
    for n, piece in enumerate(pieces):
        if n == 0:
            out = cols.copy()
        else:
            out = [cols[0] if longest != 0 else ""] + [""] * (len(cols) - 1)
        out[longest] = piece
        rows.append(row_text(out))
    return rows


def split_lines(block: str) -> list[str]:
    """Split an oversized text block (a PDF page has no blank lines) between lines
    that end a sentence. Lines are kept whole and verbatim."""
    parts, cur = [], []
    for line in block.split("\n"):
        cur.append(line)
        if len(" ".join(cur).split()) >= TARGET_WORDS and line.rstrip().endswith((".", ";")):
            parts.append("\n".join(cur))
            cur = []
    if cur:
        parts.append("\n".join(cur))
    return parts


def split_table(block: str) -> list[str]:
    """Split an oversized markdown table between rows, repeating its header row.
    Oversized text blocks are split between sentence-ending lines instead."""
    lines = table_rows(block)
    if len(block.split()) <= 2 * TARGET_WORDS:
        return [block]
    if lines is None:
        return [block] if has_table(block) else split_lines(block)
    head = lines[:2] if len(lines) > 1 and DIVIDER.match(lines[1].strip()) else lines[:1]
    head_words = len(" ".join(head).split())
    rows = [part for row in lines[len(head):] for part in split_row(row, head_words)]
    parts, cur = [], []
    for row in rows:
        if cur and len(" ".join(head + cur + [row]).split()) > TARGET_WORDS:
            parts.append("\n".join(head + cur))
            cur = []
        cur.append(row)
    if cur:
        parts.append("\n".join(head + cur))
    return parts


def pack(blocks: list[str]) -> list[str]:
    # Keep a lead-in ending with ':', or a table's one-line caption, together with
    # the block it introduces.
    merged: list[str] = []
    for blk in (part for b in blocks for part in split_table(with_divider(b))):
        last = merged[-1].split("\n\n")[-1] if merged else ""
        if merged and (last.rstrip().endswith(":") or (is_table(blk) and is_caption(last))):
            merged[-1] += "\n\n" + blk
        else:
            merged.append(blk)
    # Two tables never share a chunk, so each keeps its own header.
    chunks, cur, words = [], [], 0
    for blk in merged:
        n = len(blk.split())
        if cur and (words + n > TARGET_WORDS or (has_table(blk) and any(has_table(c) for c in cur))):
            chunks.append("\n\n".join(cur))
            cur, words = [], 0
        cur.append(blk)
        words += n
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def tags_for(text: str, vocab: dict) -> dict[str, list[str]]:
    tags: dict[str, list[str]] = {}
    for pattern, field, value in TAG_RULES:
        assert value in vocab["fields"][field]["values"], (field, value)
        if re.search(pattern, text, flags=re.I if field != "citizenship" else 0) and value not in tags.get(field, []):
            tags.setdefault(field, []).append(value)
    return tags


def effective(text: str) -> tuple[str | None, str | None]:
    found = {m.group(0) for m in EFFECTIVE.finditer(text)}
    if len(found) != 1:  # none, or ambiguous: record nothing
        return None, None
    phrase = found.pop()
    d, mon, y = EFFECTIVE.search(phrase).group(1).split()
    return Date(int(y), MONTHS[mon], int(d)).isoformat(), phrase


def next_counters(registry: dict[str, str]) -> dict[str, int]:
    """Highest number already used per policy code, keyed by the bare code ("EHG").

    Must use the same key as allocate(); keying on "CHUNK_EHG" here once restarted
    numbering at 01 on every rerun, reusing IDs for new passages.
    """
    next_n: dict[str, int] = {}
    for cid in registry.values():
        prefix, n = cid.rsplit("_", 1)
        code = prefix.removeprefix("CHUNK_")
        next_n[code] = max(next_n.get(code, 0), int(n))
    return next_n


def allocate(registry: dict[str, str], next_n: dict[str, int], key: str, code: str) -> str:
    """Give a new passage the next unused ID for its policy code."""
    used = set(registry.values())
    next_n[code] = next_n.get(code, 0) + 1
    cid = f"CHUNK_{code}_{next_n[code]:02d}"
    if cid in used:
        raise SystemExit(f"chunk ID {cid} already assigned; registry counters are inconsistent")
    registry[key] = cid
    return cid


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else (SNAPS / "ACTIVE").read_text(encoding="utf-8").strip()
    snap = SNAPS / date
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}
    next_n = next_counters(registry)

    rows, seen_keys = [], set()
    for page in manifest["pages"]:
        md_path = snap / "clean" / f"{page['slug']}.md"
        if not md_path.exists():
            continue
        code, name = policy_for(page["slug"])
        low_priority = page["word_count"] < 200
        root = page.get("page_title") if page.get("method") == "pdf" else None
        for heading, blocks in sections(md_path.read_text(encoding="utf-8"), root):
            for content in pack(blocks):
                if len(content.split()) < MIN_WORDS and not re.search(r"\$\d", content):
                    continue  # stray labels; any chunk with a figure is kept
                sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                key = hashlib.sha256(f"{page['slug']}\n{heading}\n{sha}".encode()).hexdigest()
                occurrence = 0
                while f"{key}:{occurrence}" in seen_keys:
                    occurrence += 1
                key = f"{key}:{occurrence}"
                seen_keys.add(key)
                if key not in registry:
                    allocate(registry, next_n, key, code)
                eff, eff_text = effective(content)
                rows.append({
                    "chunk_id": registry[key],
                    "source_url": page["final_url"],
                    "source_slug": page["slug"],
                    "source_tier": page["source_tier"],
                    "policy_name": name,
                    "section_heading": heading or page.get("page_title") or "",
                    "snapshot_date": date,
                    "verified_on": date,
                    "page_last_updated": page.get("last_updated_printed"),
                    "effective_date": eff,
                    "effective_date_text": eff_text,
                    "low_priority": low_priority,
                    "superseded": False,
                    "eligibility_tags": tags_for(content, vocab),
                    "content": content,
                    "content_sha256": sha,
                })

    out = CHUNKS / date
    out.mkdir(parents=True, exist_ok=True)
    with (out / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    REGISTRY.write_text(json.dumps(registry, indent=1, sort_keys=True), encoding="utf-8")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["chunk_id"].rsplit("_", 1)[0]] = counts.get(r["chunk_id"].rsplit("_", 1)[0], 0) + 1
    print(f"{len(rows)} chunks -> {out / 'chunks.jsonl'}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
