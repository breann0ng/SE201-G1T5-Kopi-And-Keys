"""The single state object passed between every node in graph.py.

Sections follow the architecture diagram, left to right. Each node only writes
the fields in its own section (plus `trace`).
"""

import operator
from decimal import Decimal
import re
from typing import Annotated

from pydantic import Field, model_validator

from .schemas import (
    ChatRequest, ChatResponse, Contract, DataOrigin, Draft, Intent, PolicyPassage,
    IncomeNote, OverviewItem, Suggestion, PriceResult, Route, RouterStatus,
    HistoryTurn,
)


class GraphState(Contract):
    # User input (from the API request; the Query Router may fill gaps)
    message: str = Field(min_length=1, max_length=4000)
    user_age: int | None = Field(default=None, ge=0, le=120)
    income: Decimal | None = Field(default=None, ge=0)
    citizenship: str | None = None
    first_timer: bool | None = None
    household_type: str | None = None
    history: list[HistoryTurn] = Field(default_factory=list)
    followup_question: str | None = None
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
    overview: list[OverviewItem] = Field(default_factory=list)
    suggestion_seeds: list[Suggestion] = Field(default_factory=list)
    income_notes: list[IncomeNote] = Field(default_factory=list)
    profile_hint: bool = False

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


def _reply_fields(message: str, previous_reply: str = "") -> dict:
    from .components.query_router import extract_fields

    fields = extract_fields(message)
    if fields["town"] is None and len(message) < 100:
        fields["town"] = extract_fields("in " + message)["town"]
    if previous_reply.startswith("Please provide:"):
        requested = previous_reply.removeprefix("Please provide:").strip().lower()
        if requested.startswith("age") and re.fullmatch(r"\s*\d{1,3}\s*", message):
            value = int(message)
            if value <= 120:
                fields["user_age"] = value
        elif requested.startswith("household income"):
            match = re.fullmatch(r"\s*(?:SGD\s*)?\$?([\d,]+(?:\.\d{1,2})?)\s*([kK])?\s*", message)
            if match:
                fields["income"] = Decimal(match[1].replace(",", "")) * (1000 if match[2] else 1)
        elif requested.startswith("first-timer") and message.strip().lower() in {"yes", "no"}:
            fields["first_timer"] = message.strip().lower() == "yes"
        elif requested.startswith("household type") and message.strip().lower() == "single":
            fields["household_type"] = "single"
        # Added 2026-10-17: one reply answering several requested numbers in order,
        # e.g. "22, 50000" to "Please provide: age, household income." used to be ignored.
        numeric = [f for f in (part.strip() for part in requested.rstrip(".").split(","))
                   if f.startswith(("age", "household income"))]
        numbers = re.findall(r"(?:SGD\s*|\$)?(\d[\d,]*(?:\.\d{1,2})?)\s*([kK])?\b", message)
        if len(numeric) > 1 and len(numbers) == len(numeric):
            for name, (value, k) in zip(numeric, numbers):
                amount = Decimal(value.replace(",", "")) * (1000 if k else 1)
                if name.startswith("age") and fields["user_age"] is None and amount <= 120:
                    fields["user_age"] = int(amount)
                elif name.startswith("household income") and fields["income"] is None:
                    fields["income"] = amount
    return fields


def initial_state(request: ChatRequest, data_origin: DataOrigin = "database") -> dict:
    """Convert an API request into graph input. Router extraction fills any gaps."""
    profile = request.profile
    filters = request.price_filters
    from .components.query_router import extract_fields, classify_intent

    # History supplies conversation context, never policy evidence. Explicit
    # sidebar fields take precedence; the router then applies the current turn.
    remembered = {}
    previous_question = None
    previous_reply = ""
    for turn in request.history:
        if turn.role == "user":
            fields = _reply_fields(turn.content, previous_reply)
            answering_clarification = previous_reply.startswith("Please provide:") and not re.search(
                r"\?|\b(?:can|may|what|how|why|eligible|qualify)\b", turn.content, re.I)
            self_description = bool(re.search(
                r"\b(?:i am|i'm|we are|we're|my income|our income|i earn|we earn|my salary|our salary)\b",
                turn.content, re.I,
            ))
            remembered.update({k: v for k, v in fields.items()
                               if v is not None and (k in {"town", "flat_type"} or self_description or answering_clarification)})
            if classify_intent(turn.content) != "unanswerable" and not answering_clarification:
                previous_question = turn.content
            previous_reply = ""
        else:
            previous_reply = turn.content
    current = _reply_fields(request.message, previous_reply)
    last_reply = request.history[-1] if request.history else None
    if (previous_question and last_reply and last_reply.role == "assistant"
            and last_reply.content.startswith("Please provide:")
            and not re.search(r"\?|\b(?:can|may|what|how|why|eligible|qualify)\b", request.message, re.I)
            and any(v is not None for v in current.values())):
        remembered.update({k: v for k, v in current.items() if v is not None})
        followup_question = previous_question
    else:
        followup_question = None
    return GraphState(
        message=request.message,
        history=request.history,
        followup_question=followup_question,
        user_age=profile.age if profile.age is not None else remembered.get("user_age"),
        income=Decimal(str(profile.household_income)) if profile.household_income is not None else remembered.get("income"),
        citizenship=profile.citizenship or remembered.get("citizenship"),
        first_timer=profile.first_timer if profile.first_timer is not None else remembered.get("first_timer"),
        household_type=profile.household_type or remembered.get("household_type"),
        town=filters.town if filters else remembered.get("town"),
        flat_type=filters.flat_type if filters else remembered.get("flat_type"),
        start_month=filters.start_month if filters else None,
        end_month=filters.end_month if filters else None,
        data_origin=data_origin,
    ).model_dump(exclude_defaults=True)


