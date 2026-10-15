from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas import PriceFilters


CENT = Decimal("0.01")
METRICS = ("mean", "median", "iqr", "minimum", "maximum")


class SQLPriceResult(BaseModel):
    """Trusted Stage 2 output. IQR is the width Q3 - Q1, in SGD."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    query_id: str = Field(min_length=1, max_length=200)
    filters: PriceFilters
    volume: int = Field(ge=0, strict=True)
    mean: Decimal | None = Field(default=None, ge=0, max_digits=20)
    median: Decimal | None = Field(default=None, ge=0, max_digits=20)
    iqr: Decimal | None = Field(default=None, ge=0, max_digits=20)
    minimum: Decimal | None = Field(default=None, ge=0, max_digits=20)
    maximum: Decimal | None = Field(default=None, ge=0, max_digits=20)

    @model_validator(mode="after")
    def consistent_statistics(self):
        values = [getattr(self, name) for name in METRICS]
        if self.volume == 0:
            if any(value is not None for value in values):
                raise ValueError("Zero transactions must have null price statistics.")
            return self
        if any(value is None for value in values):
            raise ValueError("Non-empty SQL results require mean, median, IQR, minimum and maximum.")
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("Mean must lie within the SQL price range.")
        if not self.minimum <= self.median <= self.maximum:
            raise ValueError("Median must lie within the SQL price range.")
        if self.iqr > self.maximum - self.minimum:
            raise ValueError("IQR cannot exceed the full SQL price range.")
        return self

    def display_values(self) -> dict[str, str]:
        values = {
            name: format(getattr(self, name).quantize(CENT, rounding=ROUND_HALF_UP), ",.2f")
            for name in METRICS if getattr(self, name) is not None
        }
        return {**values, "volume": str(self.volume)}


class SynthesisState(BaseModel):
    """The state slice Breann can embed in the project's global GraphState."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_query: str = Field(min_length=1, max_length=4000)
    sql_result: SQLPriceResult
    data_origin: Literal["stage2", "synthetic_fixture"] = "stage2"
    draft_response: str = ""
    final_response: str = ""
    status: Literal["pending", "needs_repair", "answered", "no_data", "abstained"] = "pending"
    verification_passed: bool = False
    verification_errors: list[str] = Field(default_factory=list)
    generation_error: str | None = None
    model_calls: int = 0
    model_usage: list[dict] = Field(default_factory=list)
