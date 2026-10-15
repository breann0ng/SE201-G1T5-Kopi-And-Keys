"""Request parsing and required-field checks for the orchestration graph."""

import re
from decimal import Decimal

from ..schemas import GraphState, Intent
from .router import classify_intent


AGE_PATTERN = re.compile(
    r"\b(?:i am|i'm|aged?|age|single and|both|we're both)\s*(?:is|:)?\s*(\d{1,3})\b",
    re.IGNORECASE,
)
INCOME_PATTERN = re.compile(
    r"\b(?:income|salary|earn(?:s|ing)?|make)\b[^\d$]{0,20}"
    r"(?:sgd\s*)?\$?\s*([\d,]+(?:\.\d{1,2})?)\s*([km])?\b",
    re.IGNORECASE,
)
CITIZENSHIP_PATTERNS = (
    (re.compile(r"\b(?:singaporean|singapore citizen|citizen of singapore)\b", re.IGNORECASE), "Singaporean"),
    (re.compile(r"\b(?:permanent resident|singapore pr|pr)\b", re.IGNORECASE), "PR"),
)
TOWN_PATTERN = re.compile(
    r"\b(?:town|located in|live in|living in|in)\s*[:,-]?\s*"
    r"([a-z][a-z ]{2,30}?)(?=\s*(?:\band\b|\bwith\b|\bfor\b|\bin\b|\bthis\b|\bover\b|\bpast\b|\bsell\b|\bsold\b|\byear\b|\bcost\b|\blisted\b|,|\?|\.|$))",
    re.IGNORECASE,
)
FLAT_PATTERN = re.compile(r"\b(([1-5])\s*[- ]?room|executive)(?:\s+flat)?\b", re.IGNORECASE)

TOWN_ALIASES = {
    "AMK": "ANG MO KIO",
    "BIDADARI": "TOA PAYOH",
}
KNOWN_TOWNS = {
    "ANG MO KIO", "BEDOK", "BISHAN", "CLEMENTI", "HOUGANG", "JURONG WEST",
    "PUNGGOL", "SENGKANG", "TAMPINES", "TOA PAYOH", "WOODLANDS", "YISHUN",
    "AMK", "BIDADARI",
}

REQUIRED_FIELDS: dict[Intent, tuple[str, ...]] = {
    "policy": (),
    "price": ("town", "flat_type"),
    "mixed": ("town", "flat_type"),
    "discovery": (),
    "unanswerable": (),
}


def _extract(message: str) -> dict:
    age_match = AGE_PATTERN.search(message)
    income_match = INCOME_PATTERN.search(message)
    citizenship = "Singaporean" if re.search(r"\b(?:i am|i'm) a citizen\b", message, re.IGNORECASE) else next(
        (value for pattern, value in CITIZENSHIP_PATTERNS if pattern.search(message)),
        None,
    )
    town_match = next(
        (
            match for match in TOWN_PATTERN.finditer(message)
            if match.group(1).strip().upper() in KNOWN_TOWNS | set(TOWN_ALIASES)
            and not re.search(
                r"(?:parents?|mum|mom)\s+(?:stay|are|is|live|lives)?\s*"
                r"(?:in|near)?\s*$",
                message[max(0, match.start() - 35):match.start()],
                re.IGNORECASE,
            )
        ),
        None,
    )
    flat_match = FLAT_PATTERN.search(message)
    flat_type = flat_match.group(1).upper() if flat_match else None
    if flat_match and flat_match.group(2):
        flat_type = f"{flat_match.group(2)} ROOM"
    return {
        "user_age": int(age_match.group(1)) if age_match else None,
        "income": (
            Decimal(income_match.group(1).replace(",", ""))
            * (1000 if (income_match.group(2) or "").casefold() == "k" else 1000000 if (income_match.group(2) or "").casefold() == "m" else 1)
            if income_match else None
        ),
        "citizenship": citizenship,
        "town": (
            TOWN_ALIASES.get(town_match.group(1).strip().upper(), town_match.group(1).strip().upper())
            if town_match else None
        ),
        "flat_type": flat_type,
    }


def parse_gateway(message: str) -> GraphState:
    """Parse raw user text into validated state without calling external tools."""
    state = GraphState(message=message, **_extract(message))
    state.intent = classify_intent(message)
    return state


def missing_fields(state: GraphState) -> list[str]:
    """Return fields required before this request may continue."""
    missing = [
        field for field in REQUIRED_FIELDS[state.intent or "unanswerable"]
        if getattr(state, field) is None
    ]
    if state.intent in {"policy", "discovery"} and any(
        phrase in state.message.casefold()
        for phrase in ("condo", "private property", "sold our", "sold my")
    ) and state.user_age is None:
        missing = ["user_age"]
    return missing
