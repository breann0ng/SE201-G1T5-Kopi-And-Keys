"""Price Query Tool: parameterised SQL over HDB resale transactions.

Diagram box: "Price Query Tool (deterministic script)" over the HDB Resale
Database (SQLite). ``SqlitePriceTool`` implements ``PriceQueryTool.query`` over
the database built by ``scripts/build_resale_db.py``. Only the fixed,
parameterised query below runs, on a read-only connection; model-written SQL is
never executed.

Statistics method (documented so results are reproducible):

* All arithmetic uses ``Decimal`` on the stored prices; no floats.
* Median and quartiles use linear interpolation between closest ranks
  (the "inclusive" method; same as ``statistics.quantiles(method="inclusive")``,
  numpy's default and Excel's QUARTILE.INC).
* ``iqr`` is the scalar width Q3 - Q1. ``mean``, ``median`` and ``iqr`` are
  rounded once, to cents, ROUND_HALF_UP. Minimum and maximum are exact.
* Zero matching sales return ``volume=0`` with null statistics (no-data path).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Protocol

from ..schemas import CENT, PriceFilters, PriceResult


# Assumption: when the user gives no date range, benchmark the last 12 months.
DEFAULT_LOOKBACK_MONTHS = 12

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "data/processed/hdb_prices.db"
DB_ENV_VAR = "KOPI_RESALE_DB"
# Fewer matching sales than this: still report them, but flag as a thin sample.
MIN_RELIABLE_VOLUME = 10


class ToolUnavailableError(RuntimeError):
    """Expected missing configuration or unavailable data, safe to abstain."""


class InvalidPriceFilterError(ToolUnavailableError):
    """A filter value is not in the dataset (misspelt town, dates outside coverage).

    Subclasses ToolUnavailableError so the graph records it as ``price_error``
    instead of crashing; the message includes suggestions where possible.
    """


class PriceQueryTool(Protocol):
    def query(self, filters: PriceFilters) -> PriceResult: ...


class UnconfiguredPriceTool:
    def query(self, filters: PriceFilters) -> PriceResult:
        raise ToolUnavailableError(
            "Official resale transactions and the SQLite adapter are not connected yet."
        )


def default_window(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    months = today.year * 12 + today.month - 1 - (DEFAULT_LOOKBACK_MONTHS - 1)
    return f"{months // 12:04d}-{months % 12 + 1:02d}", f"{today.year:04d}-{today.month:02d}"


def filters_from_state(state, today: date | None = None) -> PriceFilters:
    """Build validated filters from router output, defaulting the date window."""
    start, end = default_window(today)
    return PriceFilters(
        town=state.town,
        flat_type=state.flat_type,
        start_month=state.start_month or start,
        end_month=state.end_month or end,
    )


# --- SQLite adapter ----------------------------------------------------------

@dataclass(frozen=True)
class DatasetInfo:
    """Provenance for answers, e.g. 'data.gov.sg, downloaded 2026-10-14, to 2026-10'."""

    source_url: str
    downloaded_on: str | None
    min_month: str
    max_month: str
    row_count: int
    towns: tuple[str, ...]
    flat_types: tuple[str, ...]


def _quantile(sorted_prices: list[Decimal], fraction: Decimal) -> Decimal:
    """Inclusive linear-interpolation quantile on an ascending, non-empty list."""
    position = (len(sorted_prices) - 1) * fraction
    lower = int(position)  # floor; position is never negative
    weight = position - lower
    if weight == 0:
        return sorted_prices[lower]
    return sorted_prices[lower] + (sorted_prices[lower + 1] - sorted_prices[lower]) * weight


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _exact(value) -> Decimal:
    """Stored REAL price -> Decimal, dropping a meaningless '.0' (510000.0 -> 510000)."""
    number = Decimal(str(value))
    return number.to_integral_value() if number == number.to_integral_value() else number


def is_low_volume(result: PriceResult) -> bool:
    """True when there are some, but too few, sales to treat the figures as a benchmark."""
    return 0 < result.volume < MIN_RELIABLE_VOLUME


class SqlitePriceTool:
    """Read-only benchmark over the database built by scripts/build_resale_db.py."""

    QUERY_VERSION = "price-v2"
    _SQL = (
        "SELECT resale_price FROM transactions "
        "WHERE town = ? AND flat_type = ? AND month BETWEEN ? AND ? "
        "ORDER BY resale_price"
    )

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or os.environ.get(DB_ENV_VAR) or DEFAULT_DB)
        self._info: DatasetInfo | None = None

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise ToolUnavailableError(
                "The resale database has not been built. Run scripts/build_resale_db.py."
            )
        return sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)

    def info(self) -> DatasetInfo:
        """Dataset coverage and the valid town / flat type values (cached)."""
        if self._info is None:
            try:
                with closing(self._connect()) as conn:
                    meta = conn.execute(
                        "SELECT source_url, downloaded_on, min_month, max_month, row_count "
                        "FROM import_metadata"
                    ).fetchone()
                    towns = tuple(r[0] for r in conn.execute(
                        "SELECT DISTINCT town FROM transactions ORDER BY town"))
                    types = tuple(r[0] for r in conn.execute(
                        "SELECT DISTINCT flat_type FROM transactions ORDER BY flat_type"))
            except sqlite3.Error as error:
                raise ToolUnavailableError(f"The resale database could not be read: {error}") from error
            if meta is None:
                raise ToolUnavailableError("The resale database has no import metadata; rebuild it.")
            self._info = DatasetInfo(*meta, towns=towns, flat_types=types)
        return self._info

    def _normalise(self, filters: PriceFilters) -> tuple[str, str, str, str]:
        filters = PriceFilters.model_validate(filters)
        info = self.info()
        town = " ".join(filters.town.upper().split())
        flat_type = " ".join(filters.flat_type.upper().replace("-", " ").split())
        if flat_type == "MULTI GENERATION":
            flat_type = "MULTI-GENERATION"
        for label, value, allowed in (("town", town, info.towns), ("flat type", flat_type, info.flat_types)):
            if value not in allowed:
                close = difflib.get_close_matches(value, allowed, n=3, cutoff=0.6)
                hint = f" Did you mean: {', '.join(close)}?" if close else ""
                raise InvalidPriceFilterError(f"Unknown {label} {value!r}.{hint}")
        if filters.end_month < info.min_month or filters.start_month > info.max_month:
            raise InvalidPriceFilterError(
                f"{filters.start_month} to {filters.end_month} is outside the dataset, "
                f"which covers {info.min_month} to {info.max_month}."
            )
        return town, flat_type, filters.start_month, filters.end_month

    def query(self, filters: PriceFilters) -> PriceResult:
        """Statistics for one town / flat type / month range.

        ``filters`` in the result are the normalised dataset values (e.g.
        TAMPINES, 4 ROOM), so answers display them as they appear in the data.
        """
        params = self._normalise(filters)
        try:
            with closing(self._connect()) as conn:
                source = conn.execute("SELECT source_sha256 FROM import_metadata").fetchone()
                prices = [_exact(row[0]) for row in conn.execute(self._SQL, params)]
        except sqlite3.Error as error:
            raise ToolUnavailableError(f"The resale database could not be read: {error}") from error
        if source is None:
            raise ToolUnavailableError("The resale database has no import metadata; rebuild it.")
        # Same source file + same normalised filters -> same ID, across rebuilds.
        fingerprint = json.dumps(
            {"version": self.QUERY_VERSION, "source": source[0], "params": params}, sort_keys=True,
        )
        query_id = "price-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
        normalised = PriceFilters(town=params[0], flat_type=params[1],
                                  start_month=params[2], end_month=params[3])
        if not prices:
            return PriceResult(query_id=query_id, filters=normalised, volume=0)
        q1, q3 = _quantile(prices, Decimal("0.25")), _quantile(prices, Decimal("0.75"))
        return PriceResult(
            query_id=query_id,
            filters=normalised,
            volume=len(prices),
            mean=_cents(sum(prices) / len(prices)),
            median=_cents(_quantile(prices, Decimal("0.5"))),
            iqr=_cents(q3 - q1),
            minimum=prices[0],
            maximum=prices[-1],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Price Query Tool against hdb_prices.db.")
    parser.add_argument("--town", required=True)
    parser.add_argument("--flat-type", required=True, help='e.g. "4 ROOM"')
    parser.add_argument("--start", help="YYYY-MM; defaults to the last 12 months")
    parser.add_argument("--end", help="YYYY-MM")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--question", help="User question to store in the --output case file")
    parser.add_argument("--output", type=Path,
                        help="Write a case file for `python -m kopi_keys.cli --input <file>`")
    args = parser.parse_args()

    default_start, default_end = default_window()
    tool = SqlitePriceTool(args.db)
    try:
        filters = PriceFilters(town=args.town, flat_type=args.flat_type,
                               start_month=args.start or default_start,
                               end_month=args.end or default_end)
        result = tool.query(filters)
    except (ToolUnavailableError, ValueError) as error:
        raise SystemExit(str(error)) from None

    payload = json.loads(result.model_dump_json())
    print(json.dumps(payload, indent=2))
    if is_low_volume(result):
        print(f"Note: only {result.volume} sales; treat as a thin sample.")
    if args.output:
        case = {"user_query": args.question or "Summarise these resale statistics.",
                "data_origin": "database", "sql_result": payload}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(case, indent=2), encoding="utf-8")
        print(f"Wrote case file -> {args.output}")


if __name__ == "__main__":
    main()
