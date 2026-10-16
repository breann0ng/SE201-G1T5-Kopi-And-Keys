"""Rebuild the resale SQLite database from the data.gov.sg CSV.

Usage:
    python scripts/build_resale_db.py --downloaded-on 2026-10-13
    python scripts/build_resale_db.py --csv data/raw/2017-onwards-resale-prices.csv \
        --db data/processed/hdb_prices.db --downloaded-on 2026-10-13

The whole file is validated before anything is written. Any invalid row rejects
the import and leaves an existing database untouched. The database is a generated
artifact (gitignored): re-run this script after downloading a newer CSV.

Duplicate policy: exact duplicate rows are RETAINED and counted. The source has
no unit identifier, so two units in the same block and storey range sold in the
same month for the same price are indistinguishable from a repeated record.
Dropping them would undercount real transactions. The count is recorded in
import_metadata.duplicate_rows so it can be reported and revisited.
"""

import argparse
import csv
import hashlib
import math
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/raw/2017-onwards-resale-prices.csv"
DEFAULT_DB = ROOT / "data/processed/hdb_prices.db"
DEFAULT_DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
DEFAULT_SOURCE_URL = f"https://data.gov.sg/datasets/{DEFAULT_DATASET_ID}/view"
SCHEMA_VERSION = 2

KNOWN_FLAT_TYPES = {
    "1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE", "MULTI-GENERATION",
}
# A new town in a future download fails loudly: add it here after checking it.
KNOWN_TOWNS = {
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG",
    "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS",
    "PUNGGOL", "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
}
# Sanity bounds, deliberately wide: they catch corrupt values, not outliers.
PRICE_RANGE = (10_000, 5_000_000)
FLOOR_AREA_RANGE = (15, 500)
LEASE_COMMENCE_MIN = 1960
LEASE_MONTHS_MAX = 99 * 12
MAX_REPORTED_ERRORS = 20

SCHEMA = f"""
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    month TEXT NOT NULL,              -- YYYY-MM
    town TEXT NOT NULL,
    flat_type TEXT NOT NULL,
    block TEXT NOT NULL,
    street_name TEXT NOT NULL,
    storey_range TEXT NOT NULL,
    floor_area_sqm REAL NOT NULL,
    flat_model TEXT NOT NULL,
    lease_commence_date INTEGER NOT NULL,
    remaining_lease TEXT NOT NULL,    -- original text, kept for display
    remaining_lease_months INTEGER NOT NULL,  -- parsed, for filtering
    resale_price REAL NOT NULL
);
CREATE INDEX idx_town_type_month ON transactions (town, flat_type, month);
CREATE INDEX idx_month ON transactions (month);
CREATE INDEX idx_lease_months ON transactions (remaining_lease_months);

CREATE TABLE import_metadata (
    schema_version INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    downloaded_on TEXT,               -- YYYY-MM-DD; NULL if not supplied
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    duplicate_rows INTEGER NOT NULL,  -- rows identical to an earlier row
    min_month TEXT NOT NULL,
    max_month TEXT NOT NULL
);
PRAGMA user_version = {SCHEMA_VERSION};
"""

CSV_COLUMNS = [
    "month", "town", "flat_type", "block", "street_name", "storey_range",
    "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease",
    "resale_price",
]
DB_COLUMNS = [*CSV_COLUMNS[:10], "remaining_lease_months", "resale_price"]

MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
STOREY_PATTERN = re.compile(r"^\d{2} TO \d{2}$")
# Matches "61 years 04 months", "61 years 1 month" and "61 years".
LEASE_PATTERN = re.compile(r"^\s*(\d+)\s+years?(?:\s+(\d+)\s+months?)?\s*$")


class DataValidationError(ValueError):
    """The source file is invalid; nothing was written."""


def lease_months(text: str) -> int:
    match = LEASE_PATTERN.match(text)
    if not match:
        raise ValueError(f"unrecognised remaining_lease {text!r}")
    months = int(match.group(2) or 0)
    if months > 11:
        raise ValueError(f"remaining_lease months out of range in {text!r}")
    return int(match.group(1)) * 12 + months


def bounded_number(text: str, name: str, low: float, high: float) -> float:
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{name} is not a number: {text!r}") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} {text!r} outside {low}–{high}")
    return value


def parse_row(record: dict, today: date) -> tuple:
    values = {key: (record.get(key) or "").strip() for key in CSV_COLUMNS}
    for key in ("block", "street_name", "flat_model"):
        if not values[key]:
            raise ValueError(f"{key} is empty")

    match = MONTH_PATTERN.match(values["month"])
    if not match:
        raise ValueError(f"month must be YYYY-MM: {values['month']!r}")
    if int(match.group(1)) < 1990 or values["month"] > f"{today:%Y-%m}":
        raise ValueError(f"month {values['month']!r} is before 1990 or in the future")

    town = values["town"].upper()
    if town not in KNOWN_TOWNS:
        raise ValueError(f"unknown town {values['town']!r}")
    flat_type = values["flat_type"].upper()
    if flat_type not in KNOWN_FLAT_TYPES:
        raise ValueError(f"unknown flat_type {values['flat_type']!r}")
    if not STOREY_PATTERN.match(values["storey_range"]):
        raise ValueError(f"storey_range must be 'NN TO NN': {values['storey_range']!r}")

    area = bounded_number(values["floor_area_sqm"], "floor_area_sqm", *FLOOR_AREA_RANGE)
    price = bounded_number(values["resale_price"], "resale_price", *PRICE_RANGE)
    lease_start = bounded_number(
        values["lease_commence_date"], "lease_commence_date", LEASE_COMMENCE_MIN, today.year,
    )
    if not lease_start.is_integer():
        raise ValueError(f"lease_commence_date is not a year: {values['lease_commence_date']!r}")
    remaining = lease_months(values["remaining_lease"])
    if remaining > LEASE_MONTHS_MAX:
        raise ValueError(f"remaining_lease exceeds 99 years: {values['remaining_lease']!r}")

    return (
        values["month"], town, flat_type, values["block"], values["street_name"],
        values["storey_range"], area, values["flat_model"], int(lease_start),
        values["remaining_lease"], remaining, price,
    )


def read_rows(path: Path, today: date) -> list[tuple]:
    """Validate the whole file first; report up to MAX_REPORTED_ERRORS problems."""
    rows, errors = [], []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise DataValidationError(f"CSV is missing columns: {sorted(missing)}")
        for line_no, record in enumerate(reader, start=2):
            try:
                rows.append(parse_row(record, today))
            except ValueError as error:
                errors.append(f"line {line_no}: {error}")
    if errors:
        shown = "\n  ".join(errors[:MAX_REPORTED_ERRORS])
        more = len(errors) - MAX_REPORTED_ERRORS
        suffix = f"\n  ... and {more} more" if more > 0 else ""
        raise DataValidationError(f"{len(errors)} invalid rows; nothing written:\n  {shown}{suffix}")
    if not rows:
        raise DataValidationError("CSV has no data rows; nothing written.")
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(
    csv_path: Path,
    db_path: Path,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    dataset_id: str = DEFAULT_DATASET_ID,
    downloaded_on: date | None = None,
    today: date | None = None,
) -> dict:
    csv_path, db_path = Path(csv_path).resolve(), Path(db_path).resolve()
    if not csv_path.is_file():
        raise DataValidationError(f"CSV not found: {csv_path}")
    rows = read_rows(csv_path, today or date.today())
    duplicate_rows = sum(count - 1 for count in Counter(rows).values() if count > 1)
    months = [row[0] for row in rows]
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_file": str(csv_path.relative_to(ROOT)) if csv_path.is_relative_to(ROOT) else str(csv_path),
        "source_sha256": sha256(csv_path),
        "source_url": source_url,
        "dataset_id": dataset_id,
        "downloaded_on": downloaded_on.isoformat() if downloaded_on else None,
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": len(rows),
        "duplicate_rows": duplicate_rows,
        "min_month": min(months),
        "max_month": max(months),
    }

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            conn.executescript(SCHEMA)
            conn.executemany(
                f"INSERT INTO transactions ({', '.join(DB_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(DB_COLUMNS))})",
                rows,
            )
            conn.execute(
                f"INSERT INTO import_metadata ({', '.join(metadata)}) "
                f"VALUES ({', '.join('?' * len(metadata))})",
                list(metadata.values()),
            )
            conn.commit()
        finally:
            conn.close()
        # Swap in atomically so a failed import never replaces a working database.
        tmp_path.replace(db_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument(
        "--downloaded-on", type=date.fromisoformat,
        help="Date the CSV was downloaded (YYYY-MM-DD). Recorded for provenance.",
    )
    args = parser.parse_args()
    if args.downloaded_on is None:
        print("Warning: --downloaded-on not given; downloaded_on will be NULL.")
    try:
        meta = build(
            args.csv, args.db, source_url=args.source_url,
            dataset_id=args.dataset_id, downloaded_on=args.downloaded_on,
        )
    except DataValidationError as error:
        raise SystemExit(f"Import rejected: {error}") from None
    print(
        f"Wrote {meta['row_count']:,} transactions ({meta['min_month']} to {meta['max_month']}; "
        f"{meta['duplicate_rows']} exact duplicates retained) -> {args.db}"
    )


if __name__ == "__main__":
    main()
