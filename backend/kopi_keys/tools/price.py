from typing import Protocol

from ..schemas import PriceFilters, PriceResult


class ToolUnavailableError(RuntimeError):
    """Expected missing configuration or unavailable data, safe to abstain."""


class PriceQueryTool(Protocol):
    def query(self, filters: PriceFilters) -> PriceResult: ...


class UnconfiguredPriceTool:
    def query(self, filters: PriceFilters) -> PriceResult:
        raise ToolUnavailableError(
            "Official resale transactions and the SQLite adapter are not connected yet."
        )
