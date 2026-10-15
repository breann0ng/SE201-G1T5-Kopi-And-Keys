"""Intent classification and canonical route selection."""

import re

from ..schemas import Intent, Route


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
)
DISCOVERY_WORDS = (
    "what can i afford", "where should i buy", "help me decide", "recommend",
    "what should i look into", "what should we look into", "where do we start",
    "what's the catch", "what is the catch",
)
UNANSWERABLE_PATTERNS = (
    "will this flat be worth", "buy now or wait", "recommend a good property agent",
    "what will it actually sell for",
)


def classify_intent(message: str) -> Intent:
    normalized = message.casefold()
    if any(pattern in normalized for pattern in UNANSWERABLE_PATTERNS):
        return "unanswerable"
    has_price = any(word in normalized for word in PRICE_WORDS)
    has_policy = any(word in normalized for word in POLICY_WORDS)
    is_discovery = any(phrase in normalized for phrase in DISCOVERY_WORDS)
    if is_discovery:
        return "discovery"
    has_price_context = has_price and (
        bool(FLAT_PATTERN.search(message))
        or any(word in normalized for word in (
            "price", "median", "benchmark", "going for", "cost", "damage", "listed at",
        ))
    )
    has_explicit_price_stat = any(
        word in normalized
        for word in (
            "price", "median", "benchmark", "going for", "cost", "damage", "listed at", "sold", "what did",
        )
    )
    has_mixed_policy = any(
        word in normalized for word in POLICY_WORDS if word not in {"lease"}
    )
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
