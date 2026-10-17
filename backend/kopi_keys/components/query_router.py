"""Query Router: classify the question, extract buyer/price filters, validate.

Diagram box: "Query router (LLM)". The current implementation is rule-based
(keywords + regex) and is the baseline for the dev-set routing labels. An LLM
classifier should replace `classify_intent` and `extract_fields` behind the
same `route_query` contract; its output must still pass `RouterOutput`
validation before anything runs.

`missing_fields` is a temporary hard-coded gate. Per proposal Appendix B it
should eventually be driven by the topic cards' required fields
(see components/topic_cards.py).
"""

import re
from datetime import date
from decimal import Decimal

from pydantic import Field

from ..schemas import Contract, Intent, Route, RouterStatus


# --- Intent classification -------------------------------------------------

FLAT_PATTERN = re.compile(r"\b(([1-5])\s*[- ]?room|executive)(?:\s+flat)?\b", re.IGNORECASE)
PRICE_WORDS = (
    "price", "prices", "selling", "sold", "cost", "median", "benchmark",
    "going for", "what did", "how much", "damage", "listed at", "normal",
)
POLICY_WORDS = (
    "eligible", "eligibility", "grant", "scheme", "policy", "can i buy", "allowed",
    "cpf", "ehg", "mop", "lease", "rent", "rental", "income ceiling", "ethnic",
    "parents", "proximity", "wait-out", "wait out", "private property", "single",
    "hdb", "condo", "stuck there", "how long", "block", "neighbourhood", "full",
    "loan", "mortgage", "financing", "hfe",
    "borrow", "repayment", "interest rate", "instalment", "installment",
    # Purchase steps and non-citizen households (combined dev set, 2026-10-17).
    "option to purchase", "option fee", "otp", "loan-to-value",
    "spouse", "wife", "husband", "foreigner", "work pass", "visit pass", "what pass",
)
BUY_ELIGIBILITY = re.compile(
    r"\b(?:can|may)\b.{0,70}\bbuy\b.{0,40}\b(?:resale|hdb|flat)\b", re.IGNORECASE,
)
DISCOVERY_WORDS = (
    "what can i afford", "where should i buy", "help me decide", "recommend",
    "what should i look into", "what should we look into", "where do we start",
    "what's the catch", "what is the catch",
    "with our grants", "with my grants", "what should i know", "what should we know",
    "anything we should check", "anything i should check",
)
UNANSWERABLE_PATTERNS = (
    "will this flat be worth", "buy now or wait", "recommend a good property agent",
    "what will it actually sell for",
    # Eligibility verdicts: only HDB's HFE letter confirms eligibility (framing rule).
    "confirm we are", "confirm i am", "confirm that we", "confirm that i", "definitely eligible",
    "guarantee we", "guarantee i",
)


# "How much is a flat in Toa Payoh?" names no flat type and no strong price word,
# but a flat or a town makes "how much" / "sold" a price question (the router then
# asks for the missing flat type instead of declining).
PRICE_SUBJECT = re.compile(r"\b(?:flats?|units?)\b", re.IGNORECASE)


def _names_a_town(message: str) -> bool:
    return bool(TOWN_PATTERN.search(message))


def classify_intent(message: str) -> Intent:
    normalized = message.casefold()
    if any(pattern in normalized for pattern in UNANSWERABLE_PATTERNS):
        return "unanswerable"
    has_price = any(word in normalized for word in PRICE_WORDS)
    has_policy = any(word in normalized for word in POLICY_WORDS) or bool(BUY_ELIGIBILITY.search(message))
    is_discovery = any(phrase in normalized for phrase in DISCOVERY_WORDS)
    if is_discovery:
        return "discovery"
    has_price_context = has_price and (
        bool(FLAT_PATTERN.search(message))
        or any(word in normalized for word in (
            "price", "median", "benchmark", "going for", "cost", "damage", "listed at",
        ))
        or (not has_policy and (bool(PRICE_SUBJECT.search(message)) or _names_a_town(message)))
    )
    has_explicit_price_stat = any(
        word in normalized
        for word in (
            "price", "median", "benchmark", "going for", "cost", "damage", "listed at", "sold", "what did",
        )
    )
    has_mixed_policy = any(
        word in normalized for word in POLICY_WORDS if word not in {"lease"}
    ) or bool(BUY_ELIGIBILITY.search(message))
    if has_price_context and "grant" in normalized and not has_explicit_price_stat:
        return "policy"
    if has_price_context and has_mixed_policy:
        return "mixed"
    if has_price_context:
        return "price"
    if has_policy:
        return "policy"
    return "unanswerable"


def route_for_intent(intent: Intent) -> Route:
    if intent == "unanswerable":
        return "abstain"
    if intent == "discovery":
        return "policy"
    return intent


# --- Field extraction ------------------------------------------------------

AGE_PATTERN = re.compile(
    r"\b(?:i am|i'm|aged?|age|single and|both|we're both)\s*(?:is|:)?\s*(\d{1,3})\b",
    re.IGNORECASE,
)
INCOME_PATTERN = re.compile(
    r"\b(?:income|salary|earn(?:s|ing)?|make)\b[^\d$]{0,20}"
    r"(?:sgd\s*)?\$?\s*([\d,]+(?:\.\d{1,2})?)\s*([km])?\b",
    re.IGNORECASE,
)
# "not Singaporean" / "not a PR" describe someone else, so negated mentions are skipped.
CITIZENSHIP_PATTERNS = (
    (re.compile(r"\b(?<!not )(?<!not a )(?:singaporean|singapore citizen|citizen of singapore)\b", re.IGNORECASE),
     "Singaporean"),
    (re.compile(r"\b(?<!not )(?<!not a )(?:permanent resident|singapore pr|pr)\b", re.IGNORECASE), "PR"),
)
# All 26 towns in the HDB resale dataset (same list as scripts/build_resale_db.py).
KNOWN_TOWNS = {
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG",
    "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS",
    "PUNGGOL", "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
}
# Common names that are not dataset town names -> the dataset town.
TOWN_ALIASES = {
    "AMK": "ANG MO KIO",
    "BIDADARI": "TOA PAYOH",
    "CCK": "CHOA CHU KANG",
    "KALLANG": "KALLANG/WHAMPOA",
    "WHAMPOA": "KALLANG/WHAMPOA",
    "KALLANG WHAMPOA": "KALLANG/WHAMPOA",
}
# Match a known town name after a location word. Names are listed longest first
# so "JURONG WEST" wins over a shorter prefix; spaces/slashes may vary in input.
_TOWN_NAMES = sorted(KNOWN_TOWNS | set(TOWN_ALIASES), key=len, reverse=True)
TOWN_PATTERN = re.compile(
    r"\b(?:town|located in|live in|living in|in|at|near)\s*[:,-]?\s*("
    + "|".join(r"[\s/]+".join(map(re.escape, re.split(r"[\s/]+", name))) for name in _TOWN_NAMES)
    + r")\b",
    re.IGNORECASE,
)


def _canonical_town(text: str) -> str:
    name = " ".join(re.split(r"[\s/]+", text.strip().upper()))
    if name in TOWN_ALIASES:
        return TOWN_ALIASES[name]
    return "KALLANG/WHAMPOA" if name == "KALLANG WHAMPOA" else name


EXTRACTED_FIELDS = ("user_age", "income", "citizenship", "town", "flat_type", "first_timer", "household_type")


def extract_fields(message: str) -> dict:
    age_match = AGE_PATTERN.search(message)
    income_match = INCOME_PATTERN.search(message)
    citizenship = "Singaporean" if re.search(r"\b(?:i am|i'm) a citizen\b", message, re.IGNORECASE) else next(
        (value for pattern, value in CITIZENSHIP_PATTERNS if pattern.search(message)),
        None,
    )
    # Preserve household citizenship when replying with a sidebar option.
    for pattern, value in (
        (r"\bSC/SC\b|two Singapore citizens", "SC/SC"),
        (r"\bSC/SPR\b|Singapore Citizen with Singapore Permanent Resident", "SC/SPR"),
        (r"\bSPR/SPR\b|Singapore Permanent Residents only", "SPR/SPR"),
        (r"\bSC/NR\b|Singapore Citizen with non-resident", "SC/NR"),
        (r"\bSC_single\b|Single Singapore Citizen", "SC_single"),
    ):
        if re.search(pattern, message, re.I):
            citizenship = value
            break
    town_match = next(
        (
            match for match in TOWN_PATTERN.finditer(message)
            if not re.search(
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
    first_timer = None
    if re.search(r"\b(?:second[- ]timer|not (?:a )?first[- ]timer)\b", message, re.I):
        first_timer = False
    elif re.search(r"\bfirst[- ]timer\b", message, re.I):
        first_timer = True
    household_type = None
    if re.search(r"\b(?:couple|married|family|families)\b", message, re.I):
        household_type = "couple_family"
    elif re.search(r"\b(?:i am|i'm|as a|buying as a)\s+single\b", message, re.I):
        household_type = "single"
    return {
        "user_age": int(age_match.group(1)) if age_match else None,
        "income": (
            Decimal(income_match.group(1).replace(",", ""))
            * (1000 if (income_match.group(2) or "").casefold() == "k" else 1000000 if (income_match.group(2) or "").casefold() == "m" else 1)
            if income_match else None
        ),
        "citizenship": citizenship,
        "town": _canonical_town(town_match.group(1)) if town_match else None,
        "flat_type": flat_type,
        "first_timer": first_timer,
        "household_type": household_type,
    }


# --- Date range ----------------------------------------------------------------
# Added 2026-10-18: price questions naming a period used to fall back to the
# last 12 months, so "in 2012" or "the last half of 2025" got recent prices. Phrases
# such as "past year", "recently" or "these days" still use that default window.

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"((?:19|20)\d{2})"


def _ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _cap(year: int, month: int, today: date) -> str:
    """A month, but never later than the current one."""
    return _ym(year, month) if (year, month) <= (today.year, today.month) else _ym(today.year, today.month)


def extract_month_range(message: str, today: date | None = None) -> tuple[str, str] | None:
    """(start_month, end_month) for a period named in the question, else None (default window)."""
    today = today or date.today()
    text = message.casefold()
    m = re.search(rf"\b(?:from\s+)?{_MONTH}\s*(?:{_YEAR}\s*)?(?:to|-|until|till)\s*{_MONTH}\s+{_YEAR}\b", text)
    if m:
        end_year = int(m.group(4))
        start_year = int(m.group(2)) if m.group(2) else end_year
        return (_ym(start_year, _MONTHS[m.group(1)[:3]]), _cap(end_year, _MONTHS[m.group(3)[:3]], today))
    m = re.search(rf"\b(first|1st|second|2nd|last|latter)\s+half\s+(?:of\s+)?{_YEAR}\b", text)
    if m:
        year = int(m.group(2))
        if m.group(1) in ("first", "1st"):
            return _ym(year, 1), _cap(year, 6, today)
        return _ym(year, 7), _cap(year, 12, today)
    m = re.search(r"\b(?:past|last)\s+(\d{1,2})\s+months?\b", text)
    if m:
        n = max(1, min(int(m.group(1)), 120))
        first = today.year * 12 + today.month - n
        return _ym(first // 12, first % 12 + 1), _ym(today.year, today.month)
    if re.search(r"\bthis year\b", text):
        return _ym(today.year, 1), _ym(today.year, today.month)
    if re.search(r"\blast year\b", text):
        return _ym(today.year - 1, 1), _ym(today.year - 1, 12)
    m = re.search(rf"\b(?:in|for|during|of|since)\s+{_YEAR}\b|\b{_YEAR}\s+so far\b|\b{_YEAR}\b", text)
    if m:
        year = int(next(g for g in m.groups() if g))
        return _ym(year, 1), _cap(year, 12, today)
    return None


# --- Required-field gate (to be replaced by topic-card requirements) -------

REQUIRED_FIELDS: dict[Intent, tuple[str, ...]] = {
    "policy": (),
    "price": ("town", "flat_type"),
    "mixed": ("town", "flat_type"),
    "discovery": (),
    "unanswerable": (),
}


def missing_fields(intent: Intent, message: str, values: dict) -> list[str]:
    """Return fields required before this request may continue."""
    missing = [field for field in REQUIRED_FIELDS[intent] if values.get(field) is None]
    if intent in {"policy", "discovery"} and any(
        phrase in message.casefold()
        for phrase in ("condo", "private property", "sold our", "sold my")
    ) and values.get("user_age") is None:
        missing = ["user_age"]
    return missing


# --- Validated router output -----------------------------------------------

class RouterOutput(Contract):
    """Validated in code before any tool runs."""

    intent: Intent
    route: Route
    status: RouterStatus
    missing_fields: list[str] = Field(default_factory=list)
    user_age: int | None = Field(default=None, ge=0, le=120)
    income: Decimal | None = Field(default=None, ge=0)
    citizenship: str | None = None
    town: str | None = None
    flat_type: str | None = None
    first_timer: bool | None = None
    household_type: str | None = None
    start_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def route_query(message: str, known: dict | None = None, context_question: str | None = None) -> RouterOutput:
    """Classify and extract. Values found in the message win; `known` fills gaps."""
    known = known or {}
    intent = classify_intent(message)
    if context_question:
        intent = classify_intent(context_question)
    extracted = extract_fields(message)
    values = {
        field: extracted[field] if extracted[field] is not None else known.get(field)
        for field in EXTRACTED_FIELDS
    }
    period = extract_month_range(message) or (extract_month_range(context_question) if context_question else None)
    values["start_month"], values["end_month"] = period or (known.get("start_month"), known.get("end_month"))
    missing = missing_fields(intent, message, values)
    if re.fullmatch(r"\s*(?:i (?:want|would like) to know about|tell me about|what is|explain)\s+hdb[?.! ]*", message, re.I):
        missing = ["topic"]
    if missing:
        route, status = "clarify", "clarify"
    elif intent == "unanswerable":
        route, status = "abstain", "abstain"
    else:
        route, status = route_for_intent(intent), "continue"
    return RouterOutput(intent=intent, route=route, status=status, missing_fields=missing, **values)
