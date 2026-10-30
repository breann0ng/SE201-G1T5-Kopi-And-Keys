"""Abstention Output: fixed decline messages, one per reason.

Diagram box: "Abstention Output". Abstention is reached when the router finds
the question unsupported, when no usable evidence was retrieved, when the
model engine fails, or when the Verifier rejects the draft twice. Messages are
fixed text so a decline never carries unverified facts.
"""

from typing import Literal


AbstainReason = Literal[
    "unsupported",
    "no_evidence",
    "no_transactions",
    "price_out_of_range",
    "engine_unavailable",
    "verification_failed",
]

MESSAGES: dict[str, str] = {
    "unsupported": "I can help with HDB resale policy and resale price questions only.",
    "no_evidence": "I could not find suitable policy evidence or price data to answer this.",
    "no_transactions": "No matching resale transactions were found for the requested filters.",
    "price_out_of_range": "Our resale records have no sales for the period you asked about.",
    "engine_unavailable": "I could not generate an answer because the language model engine was unavailable.",
    "verification_failed": "I could not verify the drafted answer against its sources, so I will not show it.",
}
# Reasons whose detail is already a complete plain-English message (written in code, not by
# the model), shown on its own instead of appended to the fixed text.
DETAIL_ONLY = {"price_out_of_range"}


def abstention_message(reason: str, detail: str | None = None) -> str:
    if reason in DETAIL_ONLY and detail:
        return detail
    message = MESSAGES.get(reason, MESSAGES["no_evidence"])
    return f"{message} ({detail})" if detail else message
