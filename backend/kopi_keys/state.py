"""The single state object passed between every node in graph.py.

Sections follow the architecture diagram, left to right. Each node only writes
the fields in its own section (plus `trace`).
"""

import operator
from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from .schemas import (
    ChatRequest, ChatResponse, Contract, DataOrigin, Draft, Intent, PolicyPassage,
    PriceResult, Route, RouterStatus,
)


class GraphState(Contract):
    # User input (from the API request; the Query Router may fill gaps)
    message: str = Field(min_length=1, max_length=4000)
    user_age: int | None = Field(default=None, ge=0, le=120)
    income: Decimal | None = Field(default=None, ge=0)
    citizenship: str | None = None
    first_timer: bool | None = None
    town: str | None = None
    flat_type: str | None = None
    start_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    data_origin: DataOrigin = "database"

    # Query Router
    intent: Intent | None = None
    route: Route | None = None
    status: RouterStatus = "continue"
    missing_fields: list[str] = Field(default_factory=list)

    # Policy Retrieval Tool
    retrieval_queries: list[str] = Field(default_factory=list)
    passages: list[PolicyPassage] = Field(default_factory=list)

    # Price Query Tool
    price_result: PriceResult | None = None
    price_error: str | None = None

    # Topic cards (matched in code by components/topic_cards.py, worded by the Synthesiser)
    candidate_card_ids: list[str] = Field(default_factory=list)

    # Synthesiser Agent
    draft: Draft | None = None
    generation_error: str | None = None
    model_calls: int = 0
    model_usage: list[dict] = Field(default_factory=list)

    # Verifier
    verification_errors: list[str] = Field(default_factory=list)
    verification_passed: bool = False
    repair_count: int = 0

    # Abstention / output
    abstain_reason: str | None = None
    response: ChatResponse | None = None

    # Appended to by every node, in execution order
    trace: Annotated[list[str], operator.add] = Field(default_factory=list)

    @model_validator(mode="after")
    def non_blank_profile_values(self):
        for field in ("citizenship", "town", "flat_type"):
            value = getattr(self, field)
            if value is not None and not value.strip():
                raise ValueError(f"{field} must not be blank")
        return self


def initial_state(request: ChatRequest, data_origin: DataOrigin = "database") -> dict:
    """Convert an API request into graph input. Router extraction fills any gaps."""
    profile = request.profile
    filters = request.price_filters
    return GraphState(
        message=request.message,
        user_age=profile.age,
        income=Decimal(str(profile.household_income)) if profile.household_income is not None else None,
        citizenship=profile.citizenship,
        first_timer=profile.first_timer,
        town=filters.town if filters else None,
        flat_type=filters.flat_type if filters else None,
        start_month=filters.start_month if filters else None,
        end_month=filters.end_month if filters else None,
        data_origin=data_origin,
    ).model_dump(exclude_defaults=True)


