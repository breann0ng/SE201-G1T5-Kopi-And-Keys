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
    LeaseBand, StoreyBand,
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
    subsidy_status: str | None = None
    household_type: str | None = None
    history: list[HistoryTurn] = Field(default_factory=list)
    followup_question: str | None = None
    town: str | None = None
    flat_type: str | None = None
    start_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    lease_band: LeaseBand | None = None
    storey_band: StoreyBand | None = None
    data_origin: DataOrigin = "database"

    # Query Router
    intent: Intent | None = None
    route: Route | None = None
    status: RouterStatus = "continue"
    missing_fields: list[str] = Field(default_factory=list)
    router_note: str | None = None
    intent_source: str = "rules"  # see query_router.IntentSource

    # Policy Retrieval Tool
    retrieval_queries: list[str] = Field(default_factory=list)
    retrieval_retry_query: str | None = None
    passages: list[PolicyPassage] = Field(default_factory=list)

    # Price Query Tool
    price_result: PriceResult | None = None
    price_error: str | None = None
    price_out_of_range: bool = False  # price_error is a plain message: no sales in that period

    # Topic cards (matched in code by components/topic_cards.py, worded by the Synthesiser)
    candidate_card_ids: list[str] = Field(default_factory=list)
    overview: list[OverviewItem] = Field(default_factory=list)
    suggestion_seeds: list[Suggestion] = Field(default_factory=list)
    income_notes: list[IncomeNote] = Field(default_factory=list)
    profile_hint: bool = False

    # Synthesiser Agent
    draft: Draft | None = None
    generation_error: str | None = None
    synthesis_errors: list[str] = Field(default_factory=list)
    model_calls: int = 0
    model_usage: list[dict] = Field(default_factory=list)

    # Verifier
    verification_errors: list[str] = Field(default_factory=list)
    verification_passed: bool = False
    relevance_scores: list[dict] = Field(default_factory=list)
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
    from .components.query_router import extract_fields, FLOOR_SCOPE_PREFIX, floor_band_reply

    fields = extract_fields(message)
    if previous_reply.startswith(FLOOR_SCOPE_PREFIX):
        fields["storey_band"] = floor_band_reply(message) or fields["storey_band"]
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


# Added 2026-10-31: "what about sales in 2015" after a price question was declined as
# unsupported, because only replies to "Please provide:" carried the question over.
_FOLLOWUP_OPENER = re.compile(r"^\s*(?:what about|how about|and)\b", re.IGNORECASE)
# Forecasts and valuations never carry a price question over ("what about next year?").
_FOLLOWUP_BLOCKED = re.compile(r"\b(?:next|coming|future|will|worth|forecast|predict|expect)\b", re.IGNORECASE)
_FOLLOWUP_FILLER = re.compile(
    r"\b(?:in|at|for|during|from|to|of|the|a|an|flats?|units?|sales?|then|instead|only|"
    r"past|last|this|year|months?|half|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\d{1,2})\b",
    re.IGNORECASE,
)


def _price_followup(message: str, previous_question: str | None) -> bool:
    """A reply that only makes sense as a variation on the previous price question.

    Carries a short price variation or exact-floor follow-up to a prior price/mixed
    question. A floor/lease reply is kept as context for clarification, not evidence.
    Forecast/valuation wording and the router's scope guards always win.
    """
    from .components.query_router import (
        BARE_TOWN_PATTERN, EXACT_FLOOR_PATTERN, FLOOR_BAND_PATTERN, FLAT_PATTERN,
        MAISONETTE, UNANSWERABLE_PATTERNS, classify_intent, out_of_scope, lease_scope_question,
    )

    if not previous_question or classify_intent(previous_question) not in ("price", "mixed"):
        return False
    if (_FOLLOWUP_BLOCKED.search(message) or out_of_scope(message)
            or any(p in message.casefold() for p in UNANSWERABLE_PATTERNS)):
        return False
    if classify_intent(message) != "unanswerable":
        # A floor/lease follow-up still refers to the earlier transaction question.
        # Keep that context so the router can clarify an unsupported exact floor.
        return lease_scope_question(message) or bool(
            _FOLLOWUP_OPENER.search(message) and EXACT_FLOOR_PATTERN.search(message))
    if EXACT_FLOOR_PATTERN.search(message):
        return True  # e.g. "What happens if I want to buy the 16th floor?"
    if _FOLLOWUP_OPENER.search(message):
        return True
    rest = message
    for pattern in (BARE_TOWN_PATTERN, FLAT_PATTERN, MAISONETTE, EXACT_FLOOR_PATTERN,
                    FLOOR_BAND_PATTERN, re.compile(r"\b(?:19|20)\d{2}\b")):
        rest = pattern.sub(" ", rest)
    return rest != message and not re.sub(r"[\W_]+", "", _FOLLOWUP_FILLER.sub(" ", rest))


def initial_state(request: ChatRequest, data_origin: DataOrigin = "database") -> dict:
    """Convert an API request into graph input. Router extraction fills any gaps."""
    profile = request.profile
    filters = request.price_filters
    from .components.query_router import (classify_intent, extract_month_range, FLOOR_SCOPE_PREFIX,
                                          floor_band_reply, lease_scope_question, lease_topic_reply, topic_reply)

    # History supplies conversation context, never policy evidence. Explicit
    # sidebar fields take precedence; the router then applies the current turn.
    remembered = {}
    previous_question = None
    price_question = None
    previous_reply = ""
    for turn in request.history:
        if turn.role == "user":
            fields = _reply_fields(turn.content, previous_reply)
            answering_floor = previous_reply.startswith(FLOOR_SCOPE_PREFIX) and floor_band_reply(turn.content) is not None
            answering_clarification = answering_floor or (previous_reply.startswith("Please provide:") and not re.search(
                r"\?|\b(?:can|may|what|how|why|eligible|qualify)\b", turn.content, re.I)
            )
            chosen_topic = topic_reply(turn.content, previous_reply)
            scoped_policy = lease_topic_reply(turn.content, previous_reply) or chosen_topic
            intent = classify_intent(turn.content)
            price_turn = intent in {"price", "mixed"} or _price_followup(turn.content, price_question)
            if intent in {"price", "mixed"} and not _price_followup(turn.content, previous_question):
                for field in ("lease_band", "storey_band"):
                    remembered.pop(field, None)  # a new price request starts a new filter scope
            self_description = bool(re.search(
                r"\b(?:i am|i'm|we are|we're|my income|our income|i earn|we earn|my salary|our salary)\b",
                turn.content, re.I,
            ))
            remembered.update({k: v for k, v in fields.items()
                               if v is not None and (k in {"town", "flat_type"} or self_description or answering_clarification
                                                     or (price_turn and k in {"lease_band", "storey_band"}))})
            if scoped_policy:
                previous_question = scoped_policy
                if chosen_topic:
                    price_question = None
            elif intent != "unanswerable" and not answering_clarification:
                if not _price_followup(turn.content, previous_question):
                    previous_question = turn.content
                if intent in {"price", "mixed"}:
                    price_question = turn.content
                elif not price_turn and not lease_scope_question(turn.content):
                    price_question = None
            previous_reply = ""
        else:
            previous_reply = turn.content
    current = _reply_fields(request.message, previous_reply)
    scoped_policy = lease_topic_reply(request.message, previous_reply) or topic_reply(request.message, previous_reply)
    answering_floor = previous_reply.startswith(FLOOR_SCOPE_PREFIX) and floor_band_reply(request.message) is not None
    last_reply = request.history[-1] if request.history else None
    if scoped_policy:
        followup_question = scoped_policy
    elif answering_floor and price_question:
        remembered["storey_band"] = current["storey_band"]
        followup_question = price_question
    elif (previous_question and last_reply and last_reply.role == "assistant"
            and last_reply.content.startswith("Please provide:")
            and not re.search(r"\?|\b(?:can|may|what|how|why|eligible|qualify)\b", request.message, re.I)
            and any(v is not None for v in current.values())):
        remembered.update({k: v for k, v in current.items() if v is not None})
        followup_question = previous_question
    elif _price_followup(request.message, previous_question):
        followup_question = previous_question  # the router lets this message's period/town/flat win
    elif price_question and extract_month_range(request.message) and _price_followup(request.message, price_question):
        followup_question = price_question
    else:
        followup_question = None
    price_memory = remembered if followup_question and classify_intent(followup_question) in {"price", "mixed"} else {}
    return GraphState(
        message=request.message,
        history=request.history,
        followup_question=followup_question,
        user_age=profile.age if profile.age is not None else remembered.get("user_age"),
        income=Decimal(str(profile.household_income)) if profile.household_income is not None else remembered.get("income"),
        citizenship=profile.citizenship or remembered.get("citizenship"),
        first_timer=profile.first_timer if profile.first_timer is not None else remembered.get("first_timer"),
        subsidy_status=profile.subsidy_status,
        household_type=profile.household_type or remembered.get("household_type"),
        town=filters.town if filters else remembered.get("town"),
        flat_type=filters.flat_type if filters else remembered.get("flat_type"),
        start_month=filters.start_month if filters else None,
        end_month=filters.end_month if filters else None,
        lease_band=filters.lease_band if filters else price_memory.get("lease_band"),
        storey_band=filters.storey_band if filters else price_memory.get("storey_band"),
        data_origin=data_origin,
    ).model_dump(exclude_defaults=True)


