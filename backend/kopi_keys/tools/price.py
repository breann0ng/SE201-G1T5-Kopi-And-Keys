import hashlib
import json
import sqlite3
import statistics
from contextlib import closing
from pathlib import Path
from typing import Protocol

from ..schemas import PriceFilters, PriceResult


class ToolUnavailableError(RuntimeError):
    """Expected missing configuration or unavailable data, safe to abstain."""


class NoMatchingTransactionsError(ToolUnavailableError):
    """The database is available but no transactions match the filters."""


class PriceQueryTool(Protocol):
    def query(self, filters: PriceFilters) -> PriceResult: ...


class UnconfiguredPriceTool:
    def query(self, filters: PriceFilters) -> PriceResult:
        raise ToolUnavailableError(
            "Official resale transactions and the SQLite adapter are not connected yet."
        )


class SqlitePriceTool:
    """Read-only benchmark over the database built by scripts/build_resale_db.py.

    Only this fixed, parameterised query runs; model output never reaches SQL.
    """

    QUERY_VERSION = "price-v1"
    _SQL = (
        "SELECT resale_price FROM transactions "
        "WHERE town = ? AND flat_type = ? AND month BETWEEN ? AND ? "
        "ORDER BY resale_price"
    )

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise ToolUnavailableError(
                "The resale database has not been built. Run scripts/build_resale_db.py."
            )
        return sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)

    def query(self, filters: PriceFilters) -> PriceResult:
        filters = PriceFilters.model_validate(filters)
        params = (
            filters.town.upper(), filters.flat_type.upper(),
            filters.start_month, filters.end_month,
        )
        try:
            with closing(self._connect()) as conn:
                source = conn.execute("SELECT source_sha256 FROM import_metadata").fetchone()
                prices = [row[0] for row in conn.execute(self._SQL, params)]
        except sqlite3.Error as error:
            raise ToolUnavailableError(f"The resale database could not be read: {error}") from error
        if source is None:
            raise ToolUnavailableError("The resale database has no import metadata; rebuild it.")
        if not prices:
            raise NoMatchingTransactionsError(
                f"No resale transactions match {params[1]} in {params[0]} "
                f"from {params[2]} to {params[3]}."
            )
        # Same source file + same normalised filters -> same ID, across rebuilds.
        fingerprint = json.dumps(
            {"version": self.QUERY_VERSION, "source": source[0], "params": params},
            sort_keys=True,
        )
        return PriceResult(
            query_id="price-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12],
            filters=filters,  # returned as requested, so the verifier can match it
            count=len(prices),
            median=statistics.median(prices),
            minimum=prices[0],
            maximum=prices[-1],
        )
