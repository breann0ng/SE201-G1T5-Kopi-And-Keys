"""Contracts shared by the API, Advisor and tools."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Intent = Literal["policy", "price", "mixed", "discovery", "unanswerable"]
GatewayStatus = Literal["continue", "clarify", "abstain"]
Route = Literal["policy", "price", "mixed", "discovery", "clarify", "abstain"]


class GraphState(Contract):
    """Validated request state shared by the orchestration graph."""

    message: str = Field(min_length=1, max_length=4000)
    user_age: int | None = Field(default=None, ge=0, le=120)
    income: Decimal | None = Field(default=None, ge=0)
    citizenship: str | None = None
    town: str | None = None
    flat_type: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    intent: Intent | None = None
    route: Route | None = None
    status: GatewayStatus = "continue"
    response: str | None = None
    parse_errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def non_blank_profile_values(self):
        for field in ("citizenship", "town", "flat_type"):
            value = getattr(self, field)
            if value is not None and not value.strip():
                raise ValueError(f"{field} must not be blank")
        return self


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


class PolicyPassage(Contract):
    id: str
    title: str
    text: str
    source_url: str
    effective_date: date
    snapshot_id: str
    superseded: bool = False


class PriceResult(Contract):
    query_id: str
    filters: PriceFilters
    count: int = Field(ge=0)
    median: float | None = Field(default=None, ge=0)
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)


class Claim(Contract):
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)


class AdvisorDecision(Contract):
    action: Literal["retrieve", "price", "answer", "clarify", "abstain"]
    query: str = ""
    message: str = ""
    claims: list[Claim] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_payload(self):
        if self.action == "retrieve" and not self.query:
            raise ValueError("retrieve requires a query")
        if self.action in {"clarify", "abstain"} and not self.message:
            raise ValueError("clarify and abstain require a message")
        return self


class ChatResponse(Contract):
    status: Literal["answered", "clarifying", "abstained"]
    mode: Literal["demo"] = "demo"
    message: str
    citations: list[PolicyPassage] = Field(default_factory=list)
    price_result: PriceResult | None = None
    retrieval_rounds: int = 0
    trace: list[str] = Field(default_factory=list)
