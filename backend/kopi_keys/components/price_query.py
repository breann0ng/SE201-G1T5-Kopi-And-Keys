"""Price Query Tool: parameterised SQL over HDB resale transactions.

Diagram box: "Price Query Tool (deterministic script)" over the HDB Resale
Database (SQLite). Replace UnconfiguredPriceTool with a SQLite adapter that
implements `PriceQueryTool.query`. Use fixed parameterised queries and stable
query IDs; never execute model-written SQL.
"""

from datetime import date
from typing import Protocol

from ..schemas import PriceFilters, PriceResult


# Assumption: when the user gives no date range, benchmark the last 12 months.
DEFAULT_LOOKBACK_MONTHS = 12


class ToolUnavailableError(RuntimeError):
    """Expected missing configuration or unavailable data, safe to abstain."""


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
