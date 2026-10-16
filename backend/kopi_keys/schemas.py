"""Contracts shared by the API, the graph state and every component."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Intent = Literal["policy", "price", "mixed", "discovery", "unanswerable"]
RouterStatus = Literal["continue", "clarify", "abstain"]
Route = Literal["policy", "price", "mixed", "discovery", "clarify", "abstain"]
DataOrigin = Literal["database", "synthetic_fixture"]

CENT = Decimal("0.01")
PRICE_METRICS = ("mean", "median", "iqr", "minimum", "maximum")


# --- API input -------------------------------------------------------------

class BuyerProfile(Contract):
    citizenship: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    household_income: float | None = Field(default=None, ge=0)
    first_timer: bool | None = None


class PriceFilters(Contract):
    town: str = Field(min_length=1, max_length=100)
    flat_type: str = Field(min_length=1, max_length=50)
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @model_validator(mode="after")
    def ordered_months(self):
        if self.start_month > self.end_month:
            raise ValueError("start_month must be on or before end_month")
        return self


class ChatRequest(Contract):
    message: str = Field(min_length=1, max_length=4000)
    profile: BuyerProfile = Field(default_factory=BuyerProfile)
    price_filters: PriceFilters | None = None


# --- Tool outputs ----------------------------------------------------------

class PolicyPassage(Contract):
    """One dated policy chunk returned by the Policy Retrieval Tool."""

    id: str
    title: str
    text: str
    source_url: str
    effective_date: date
    snapshot_id: str
    superseded: bool = False


class PriceResult(BaseModel):
    """Trusted Price Query Tool output. IQR is the width Q3 - Q1, in SGD."""

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
        values = [getattr(self, name) for name in PRICE_METRICS]
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
        """Values rounded to cents (ROUND_HALF_UP), as the Synthesiser must copy them."""
        values = {
            name: format(getattr(self, name).quantize(CENT, rounding=ROUND_HALF_UP), ",.2f")
            for name in PRICE_METRICS if getattr(self, name) is not None
        }
        return {**values, "volume": str(self.volume)}


# --- Synthesiser output ----------------------------------------------------

class Claim(Contract):
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)


class Suggestion(Contract):
    """A discovery suggestion. card_id must be one of the matched topic cards."""

    card_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)


class Draft(Contract):
    """Everything the Synthesiser Agent produces in one turn, before verification."""

    kind: Literal["answer", "clarify"]
    message: str = ""
    claims: list[Claim] = Field(default_factory=list)
    price_text: str | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_payload(self):
        if self.kind == "clarify" and not self.message:
            raise ValueError("A clarifying draft requires a message.")
        return self


# --- API output ------------------------------------------------------------

class ChatResponse(Contract):
    status: Literal["answered", "clarifying", "abstained"]
    mode: Literal["demo"] = "demo"
    route: Route | None = None
    message: str
    citations: list[PolicyPassage] = Field(default_factory=list)
    price_result: PriceResult | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    retrieval_rounds: int = 0
    trace: list[str] = Field(default_factory=list)
