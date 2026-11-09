"""Query Router: classify the question, extract buyer/price filters, validate.

Diagram box: "Query router (LLM)". The current implementation is rule-based
(keywords + regex) and is the baseline for the dev-set routing labels.
Hybrid: `rule_intent` returns None when no rule matches. Those questions go to
the LLM fallback (components/intent_fallback.py, called from graph.py), and so
do weak matches (generic keywords only), which the LLM may only veto. It can
never override a strong rule, least of all the scope guard (request types the
app declines). Field extraction stays in regex either way. Output must still
pass `RouterOutput` validation.

`missing_fields` is a temporary hard-coded gate. Per proposal Appendix B it
should eventually be driven by the topic cards' required fields
(see components/topic_cards.py).
"""

import re
from datetime import date
from decimal import Decimal

from pydantic import Field

from typing import Literal

from ..schemas import Contract, Intent, Route, RouterStatus, LeaseBand, StoreyBand
from .intent_fallback import FallbackDecision

# rules: a rule decided. no_match: no rule fired and no LLM was asked (declined by default).
# llm: the LLM fallback chose confidently. llm_unsure / llm_error: low confidence or unusable
# output, so the user is asked which topic they mean.
# rules_confirmed: a weak rule match the LLM did not veto. llm_declined: one it vetoed.
IntentSource = Literal["rules", "no_match", "llm", "llm_unsure", "llm_error", "rules_confirmed", "llm_declined"]


# --- Intent classification -------------------------------------------------

FLAT_PATTERN = re.compile(r"\b(([1-5])\s*[- ]?room|executive)(?:\s+flat)?\b", re.IGNORECASE)
PRICE_WORDS = (
    "price", "prices", "selling", "sold", "cost", "median", "benchmark",
    "going for", "what did", "how much", "the damage", "listed at", "normal",
    "go for", "goes for", "sell for", "sells for",
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
# Added 2026-10-18: "how do I buy a resale flat?", "where do I start if I want to buy a resale
# flat?" and "what sources should I look at ..." had no policy keyword and were declined as
# unsupported. A question about how, where or what to start with when buying is discovery.
BUYING_GUIDE = re.compile(
    r"\b(?:how (?:do|can|should) (?:i|we)|how to|where (?:do|should) (?:i|we) (?:start|begin|look)|"
    r"(?:start|begin)\w*|steps?|process|sources?|guide|what do (?:i|we) need)\b"
    r".{0,60}\bbuy(?:ing)?\b.{0,30}\b(?:resale|hdb|flat)\b",
    re.IGNORECASE,
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
# Added 2026-11-06: scope guard, checked before every other rule. OOS-06 ("What will 4-room
# flats in Tampines cost next year?") was routed as price and answered with past prices, and
# OOS-07 ("Can you guarantee my Family Grant application will be approved ...?") as policy.
# A time phrase alone is not a forecast ("Can I sell my flat in 5 years?" is a MOP question,
# "We're buying next year" is context), so it only counts right next to price/value wording in
# the same sentence. "How much will a 4-room cost?" asks for today's prices, so "will" only
# counts with wording about prices changing.
FORECAST_WORDS = re.compile(r"\b(?:forecast\w*|predict\w*|projections?|projected)\b", re.IGNORECASE)
_FUTURE = (r"(?:(?:next|coming)\s+(?:year|month|decade|few\s+(?:years|months)|\d+\s+years)"
           r"|in\s+(?:\d+|a\s+few|few|two|three|five|ten)\s+years?|in\s+the\s+future|future)")
_VALUE = r"(?:prices?|cost\w*|worth|value|sell\s+for|go\s+for|fetch|appreciat\w*|depreciat\w*)"
FUTURE_VALUE = re.compile(
    rf"\b{_VALUE}\b[^.?!]{{0,30}}\b{_FUTURE}\b|\b{_FUTURE}\b[^.?!]{{0,30}}\b{_VALUE}\b", re.IGNORECASE,
)
WILL_VALUE_CHANGE = re.compile(
    r"\b(?:will|going\s+to|gonna)\b[^.?!]{0,50}\b(?:be\s+worth\s+(?:more|less)|go\s+(?:up|down)|"
    r"rise|fall|drop|increase|decrease|appreciate|depreciate|crash)\b",
    re.IGNORECASE,
)
# Valuing one specific flat (OOS-05: "What is my flat at Blk 512 ... worth right now?"). Without
# a rule it reached the LLM fallback, which read it as a price question.
OWN_FLAT_VALUE = re.compile(
    r"\b(?:my|our|this|that)\s+(?:flat|unit|home|house|place)\b[^.?!]{0,60}\bworth\b"
    r"|\bhow much (?:can|could|will|would) (?:i|we) (?:sell|get for) (?:my|our|this)\b",
    re.IGNORECASE,
)
GUARANTEE = re.compile(
    r"\bguarantee\w*\b|\b(?:will|would)\s+(?:my|our|the)\b.{0,40}\b(?:application|appeal)\b.{0,20}"
    r"\bbe\s+(?:approved|successful|accepted)\b",
    re.IGNORECASE,
)


# Added 2026-11-08: declines written per request type, not per case, so a new provider or task
# is covered without a new rule. Three questions passed as policy on "loan" / "hdb" alone:
# "Recommend me a good mortgage broker", "Which bank gives the cheapest home loan right now?",
# "Can you write my appeal letter to HDB?".
# Recommend a provider: a choosing word just before a kind of provider.
# The provider must be what is being chosen, not a word describing something else: "Which bank
# loan documents are required?" asks about documents (code review, PR #20), and "Who pays the
# agent's commission?" about a fee. So the provider may not be followed by a noun it modifies
# or by a possessive.
_PROVIDER_AS_MODIFIER = (
    r"(?!'s\b|’s\b|\s+(?:loans?|mortgages?|documents?|paperwork|statements?|accounts?|fees?|charges?|"
    r"commissions?|rates?|interest|valuations?|letters?|approvals?|requirements?|terms|polic(?:y|ies)|"
    r"forms?|processing|checks?|rules?)\b)"
)
RECOMMEND_PROVIDER = re.compile(
    r"\b(?:recommend|suggest|which|who|best|good|reliable|trusted|trustworthy|cheapest|top)\b[^.?!]{0,25}?"
    r"\b(?:agents?|agency|agencies|brokers?|banks?|lenders?|lawyers?|law\s+firms?|conveyancers?|"
    r"contractors?|renovators?|interior\s+designers?|movers?|valuers?)\b" + _PROVIDER_AS_MODIFIER +
    r"|\b(?:best|cheapest|lowest[- ]interest)\s+(?:home\s+|bank\s+|mortgage\s+|housing\s+)?(?:loans?|mortgages?)\b",
    re.IGNORECASE,
)
# Investment advice. "Should I wait to buy ...?" stays in scope (POL-02 asks about grant timing).
INVESTMENT_ADVICE = re.compile(
    r"\b(?:good|better|bad|worse|smart|wise|safe)\s+investment\b"
    r"|\b(?:stocks?|shares|crypto|bonds|etfs?)\b[^.?!]{0,40}\b(?:or|vs|versus|instead)\b"
    r"|\b(?:or|vs|versus|instead\s+of)\b[^.?!]{0,40}\b(?:stocks?|shares|crypto|bonds|etfs?)\b"
    r"|\bis\s+(?:it|now)\s+(?:a\s+)?(?:good|right|bad|the\s+right)\s+time\s+to\s+(?:buy|sell)\b",
    re.IGNORECASE,
)
# A task done for the user: the verb right after "can you" / "please", or writing a document.
# "Can you tell me how to submit ...?" is a process question and does not match.
DO_A_TASK = re.compile(
    r"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:help\s+(?:me|us)\s+)?"
    r"(?:write|draft|compose|fill\s+(?:in|out|up)|submit|apply|book|send|email|call|contact|negotiate)\b"
    r"|\bplease\s+(?:write|draft|compose|fill|submit|apply|send|book)\b"
    r"|\b(?:write|draft|compose)\b[^.?!]{0,30}\b(?:letter|appeal|email|message|poem|essay|story|song)\b",
    re.IGNORECASE,
)

# The request types the scope guard declines. Each one is a pattern, not a list of cases.
SCOPE_GUARD = {
    "predict": (FORECAST_WORDS, WILL_VALUE_CHANGE, FUTURE_VALUE),
    "value_one_flat": (OWN_FLAT_VALUE,),
    "guarantee": (GUARANTEE,),
    "recommend_provider": (RECOMMEND_PROVIDER,),
    "investment_advice": (INVESTMENT_ADVICE,),
    "do_a_task": (DO_A_TASK,),
}


def out_of_scope(message: str) -> bool:
    """Requests declined whatever else matches: predictions, valuing one flat, guarantees,
    provider recommendations, investment advice and tasks done for the user."""
    if any(pattern in message.casefold() for pattern in UNANSWERABLE_PATTERNS):
        return True
    return any(p.search(message) for patterns in SCOPE_GUARD.values() for p in patterns)


# "How much is a flat in Toa Payoh?" names no flat type and no strong price word,
# but a flat or a town makes "how much" / "sold" a price question (the router then
# asks for the missing flat type instead of declining).
PRICE_SUBJECT = re.compile(r"\b(?:flats?|units?)\b", re.IGNORECASE)
# Maisonette (a flat model, not a flat type), incl. common misspellings: masionette, maisonnette.
MAISONETTE = re.compile(r"\bma[a-z]{0,3}on+et+e?s?\b", re.IGNORECASE)
# An address ("block 236", "blk 12A") is not a question about HDB block rules.
ADDRESS_BLOCK = re.compile(r"\b(?:block|blk)\s*\d+[a-z]?\b", re.IGNORECASE)
BLOCK_NOTE = "These are town-wide figures: the advisor does not look up a single block yet."
MAISONETTE_NOTE = (
    "HDB's resale data records maisonettes as Executive flats (about 94% of maisonette sales; "
    "the rest are 5-room), so these figures cover all Executive flats, not maisonettes only."
)


def _names_a_town(message: str) -> bool:
    return bool(TOWN_PATTERN.search(message) or BARE_TOWN_PATTERN.search(message))


def classify_intent(message: str) -> Intent:
    """The rules' intent, with "no rule matched" counted as unanswerable (used by follow-ups)."""
    return rule_intent(message) or "unanswerable"


def rule_intent(message: str) -> Intent | None:
    """Intent from the rules, or None when no rule matches (as opposed to an explicit decline)."""
    return rule_match(message)[0]


# Added 2026-11-08: keywords common outside the app's scope too ("a loan from the bank", "the
# HDB hub", "how long to drive"). When these are the only reason a question is policy, the rule
# still picks the intent but the LLM is asked to confirm (see route_query). "hdb loan" and
# "housing loan" name the HDB's own loan, so they are strong.
WEAK_POLICY_WORDS = {
    "hdb", "loan", "mortgage", "financing", "borrow", "repayment", "interest rate", "instalment",
    "installment", "block", "full", "how long", "stuck there", "neighbourhood", "condo", "rent",
    "rental", "policy", "scheme", "allowed",
}
STRONG_POLICY_PHRASES = ("hdb loan", "housing loan", "resale")
WEAK_DISCOVERY_WORDS = {"recommend"}


def rule_match(message: str) -> tuple[Intent | None, bool]:
    """(intent, weak). weak: policy or discovery decided only by generic keywords."""
    normalized = message.casefold()
    if out_of_scope(message):
        return "unanswerable", False
    has_price = any(word in normalized for word in PRICE_WORDS)
    policy_text = ADDRESS_BLOCK.sub(" ", normalized)
    policy_hits = {word for word in POLICY_WORDS if word in policy_text}
    has_policy = bool(policy_hits) or bool(BUY_ELIGIBILITY.search(message))
    weak_policy = (bool(policy_hits) and policy_hits <= WEAK_POLICY_WORDS
                   and not BUY_ELIGIBILITY.search(message)
                   and not any(phrase in policy_text for phrase in STRONG_POLICY_PHRASES))
    discovery_hits = {phrase for phrase in DISCOVERY_WORDS if phrase in normalized}
    guide = bool(BUYING_GUIDE.search(message)) and not any(word in normalized for word in PRICE_WORDS)
    if discovery_hits or guide:
        weak = discovery_hits <= WEAK_DISCOVERY_WORDS and not guide and (not has_policy or weak_policy)
        return "discovery", weak
    has_price_context = has_price and (
        bool(FLAT_PATTERN.search(message))
        or bool(MAISONETTE.search(message))
        or any(word in normalized for word in (
            "price", "median", "benchmark", "going for", "cost", "the damage", "listed at",
            "go for", "goes for", "sell for", "sells for",
        ))
        or (not has_policy and (bool(PRICE_SUBJECT.search(message)) or _names_a_town(message)))
    )
    has_explicit_price_stat = any(
        word in normalized
        for word in (
            "price", "median", "benchmark", "going for", "cost", "the damage", "listed at", "sold", "what did",
        )
    )
    has_mixed_policy = any(
        word in policy_text for word in POLICY_WORDS if word not in {"lease"}
    ) or bool(BUY_ELIGIBILITY.search(message))
    if has_price_context and "grant" in normalized and not has_explicit_price_stat:
        return "policy", False
    if has_price_context and has_mixed_policy:
        return "mixed", False
    if has_price_context:
        return "price", False
    if has_policy:
        return "policy", weak_policy
    return None, False


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


# A known town named anywhere ("how much does toa payoh lorong 1 ... go for?"); used only
# when no "in / at / near <town>" phrase is found.
BARE_TOWN_PATTERN = re.compile(
    r"\b(" + "|".join(r"[\s/]+".join(map(re.escape, re.split(r"[\s/]+", name))) for name in _TOWN_NAMES)
    + r")\b",
    re.IGNORECASE,
)


def _canonical_town(text: str) -> str:
    name = " ".join(re.split(r"[\s/]+", text.strip().upper()))
    if name in TOWN_ALIASES:
        return TOWN_ALIASES[name]
    return "KALLANG/WHAMPOA" if name == "KALLANG WHAMPOA" else name


EXTRACTED_FIELDS = ("user_age", "income", "citizenship", "town", "flat_type", "first_timer", "household_type",
                    "lease_band", "storey_band")


def price_bands(message: str) -> dict:
    """Only the tool's documented bands; never round an arbitrary floor/lease into a band."""
    lease = None
    for pattern, band in (
        (r"\bnewer\s+(?:(?:[1-5][- ]room|executive|resale|(?:high|low|mid|middle)[- ]floors?)\s+)*flats?\b|\b80\s*\+\s*(?:years?|yrs?)\b", "80_plus"),
        (r"\b(?:under|below|less than)\s+60\s*(?:years?|yrs?)\b", "under_60"),
        (r"\b60\s*(?:to|[-–])\s*79\s*(?:years?|yrs?)\b", "60_79"),
    ):
        if re.search(pattern, message, re.I):
            lease = band
            break
    floor = re.search(r"\b(low|mid|middle|high)[- ]floors?\b", message, re.I)
    return {"lease_band": lease,
            "storey_band": {"middle": "mid"}.get(floor.group(1).lower(), floor.group(1).lower()) if floor else None}


def extract_fields(message: str, bare_town: bool = False) -> dict:
    """`bare_town`: also accept a town named without "in/at/near" (price questions only)."""
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
    def not_parents_town(match) -> bool:
        return not re.search(
            r"(?:parents?|mum|mom)\s+(?:stay|are|is|live|lives)?\s*"
            r"(?:in|near)?\s*$",
            message[max(0, match.start() - 35):match.start()],
            re.IGNORECASE,
        )

    town_match = next((m for m in TOWN_PATTERN.finditer(message) if not_parents_town(m)), None)
    if town_match is None and bare_town:
        town_match = next((m for m in BARE_TOWN_PATTERN.finditer(message) if not_parents_town(m)), None)
    flat_matches = list(FLAT_PATTERN.finditer(message))
    def target_flat(match):
        prefix = message[max(0, match.start() - 70):match.start()]
        buying = re.search(r"\b(?:buy(?:ing)?|want(?:\s+to\s+buy)?|looking\s+for|upgrad(?:e|ing)\s+to)\s+"
                           r"(?:(?:a|an|the|new|resale|another)\s+)*$", prefix, re.I)
        pricing = re.search(r"^\s+(?:prices?|costs?)\b", message[match.end():], re.I)
        return bool(buying or pricing)
    flat_match = next((m for m in flat_matches if target_flat(m)), flat_matches[0] if flat_matches else None)
    # In a move, the target flat's location wins over the current home's location.
    if flat_match and target_flat(flat_match):
        target_town = next((m for m in TOWN_PATTERN.finditer(message, flat_match.end()) if not_parents_town(m)), None)
        if target_town:
            town_match = target_town
    flat_type = flat_match.group(1).upper() if flat_match else None
    if flat_match and flat_match.group(2):
        flat_type = f"{flat_match.group(2)} ROOM"
    if flat_type is None and MAISONETTE.search(message):
        flat_type = "EXECUTIVE"  # see MAISONETTE_NOTE
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
        **price_bands(message),
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
    lease_band: LeaseBand | None = None
    storey_band: StoreyBand | None = None
    # An assumption the answer must state (e.g. maisonettes counted as Executive flats).
    router_note: str | None = None
    # "no_match": no rule fired, so the question was declined by default, not by a rule.
    intent_source: IntentSource = "rules"
    # A weak rule match (generic keywords only) the graph should ask the LLM to confirm.
    needs_confirmation: bool = False


def route_query(message: str, known: dict | None = None, context_question: str | None = None,
                fallback: FallbackDecision | None = None) -> RouterOutput:
    """Classify and extract. Values found in the message win; `known` fills gaps.

    `fallback` is the LLM's decision, asked for by the graph after a first call returned
    intent_source="no_match" or needs_confirmation=True.
    - No rule matched: a confident intent is used as is; a low-confidence or unusable one asks
      the user which topic they mean instead of declining.
    - Weak rule match: the LLM can only veto it, with a confident "unanswerable". Any other
      answer, or an error, keeps the rule's intent. It never switches one intent for another.
    - Strong rule match: the decision is ignored.
    """
    known = known or {}
    intent, weak = rule_match(context_question or message)
    weak = weak and context_question is None  # a follow-up keeps its earlier question's route
    intent_source: IntentSource = "rules"
    if weak and fallback is not None:
        if fallback.intent == "unanswerable" and fallback.confidence == "high":
            intent, intent_source = "unanswerable", "llm_declined"
        elif fallback.intent is not None:
            intent_source = "rules_confirmed"
    elif intent is None:
        intent, intent_source = "unanswerable", "no_match"
        if fallback is not None:
            if fallback.intent is None:
                intent_source = "llm_error"
            elif fallback.confidence == "high":
                intent, intent_source = fallback.intent, "llm"
            else:
                intent_source = "llm_unsure"
    extracted = extract_fields(message, bare_town=intent in ("price", "mixed"))
    values = {
        field: extracted[field] if extracted[field] is not None else known.get(field)
        for field in EXTRACTED_FIELDS
    }
    if context_question:
        for field, value in price_bands(context_question).items():
            if values[field] is None:
                values[field] = value
    period = extract_month_range(message) or (extract_month_range(context_question) if context_question else None)
    values["start_month"], values["end_month"] = period or (known.get("start_month"), known.get("end_month"))
    missing = missing_fields(intent, message, values)
    if re.fullmatch(r"\s*(?:i (?:want|would like) to know about|tell me about|what is|explain)\s+hdb[?.! ]*", message, re.I):
        missing = ["topic"]
    if intent_source in ("llm_unsure", "llm_error"):
        missing = ["topic"]  # ask which topic they mean rather than decline
    if missing:
        route, status = "clarify", "clarify"
    elif intent == "unanswerable":
        route, status = "abstain", "abstain"
    else:
        route, status = route_for_intent(intent), "continue"
    notes = []
    if MAISONETTE.search(message) and not FLAT_PATTERN.search(message) and values.get("flat_type") == "EXECUTIVE":
        notes.append(MAISONETTE_NOTE)
    if intent in ("price", "mixed") and ADDRESS_BLOCK.search(message):
        notes.append(BLOCK_NOTE)
    note = " ".join(notes) or None
    return RouterOutput(intent=intent, route=route, status=status, missing_fields=missing,
                        router_note=note, intent_source=intent_source,
                        needs_confirmation=weak and fallback is None, **values)
