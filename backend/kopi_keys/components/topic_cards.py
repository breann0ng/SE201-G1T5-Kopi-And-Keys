"""Topic cards: the discovery cards (proposal Appendix B), as the graph sees them.

The card format, loader and matcher live in `kopi_keys/topic_cards.py` (topic-card
owner, Sandra); cards are in data/topic_cards/ (see its README). This module
keeps the interface graph.py already calls:

1. `TopicCard` / `load_cards`: load and validate cards at startup (schema, and
   that every trigger value is in data/schema/vocab.json). Chunk IDs are checked
   against the policy snapshot by scripts/scraping/validate.py.
2. `match_cards`: compare the buyer profile in GraphState with each card's
   triggers. Relevance is decided here, in code. Returns only fully matched
   cards; cards still missing a field are left to `required_fields`.
3. `required_fields`: the profile fields the given cards need.

The graph stores the result in `state.candidate_card_ids`. The Synthesiser may
only suggest those IDs, and the Verifier rejects any other ID.

Merge note (2026-10-16): the placeholder format here (`id` / `title` /
`triggers` / `chunk_ids`) was replaced by the card owner's format
(`card_id` / `topic_name` / `trigger_conditions` / `supporting_chunk_ids`).
"""

from collections.abc import Iterable

from ..state import GraphState
from ..topic_cards import DATA_DIR, MatchResult, TopicCard, load_cards as _load_cards
from ..topic_cards import match_cards as _match_cards


CARD_DIR = DATA_DIR / "topic_cards"

__all__ = ["CARD_DIR", "TopicCard", "load_cards", "match_cards", "match_profile",
           "profile_from_state", "required_fields"]


def load_cards(directory=CARD_DIR) -> list[TopicCard]:
    """Load every *.json card; raises TopicCardError on an invalid card."""
    if not directory.exists():
        return []
    return _load_cards(cards_dir=directory)


def profile_from_state(state: GraphState) -> dict:
    """Map GraphState names onto the card vocabulary (data/schema/vocab.json)."""
    return {
        "citizenship": state.citizenship,
        "first_timer": state.first_timer,
        "household_type": state.household_type,
        "age": state.user_age,
        "household_income": state.income,
        "town": state.town,
        "flat_type": state.flat_type,
    }


def match_profile(state: GraphState, cards: Iterable[TopicCard], **kwargs) -> MatchResult:
    """Full result: matched cards, cards blocked on missing fields, and ask_next."""
    return _match_cards(profile_from_state(state), cards, **kwargs)


def match_cards(state: GraphState, cards: list[TopicCard]) -> list[str]:
    """IDs of the cards whose triggers and required fields are all satisfied."""
    return match_profile(state, cards).matched_ids


def required_fields(card_ids: list[str], cards: list[TopicCard]) -> list[str]:
    """Fields the given cards need, in first-seen order, without duplicates."""
    wanted = set(card_ids)
    fields: list[str] = []
    for card in cards:
        if card.card_id in wanted:
            fields += [f for f in card.required_fields if f not in fields]
    return fields


def personal_eligibility_fields(state: GraphState, cards: list[TopicCard]) -> list[str]:
    """Ask for a card's inputs before attempting a personal eligibility answer.

    A general question about PR couples is not a request to assess this user.
    Card requirements describe necessary inputs, not a complete eligibility rule.
    """
    import re

    query = (state.followup_question or state.message).casefold()
    if not re.search(r"\b(?:am i|are we|do i qualify|do we qualify|can i|can we)\b", query):
        return []
    wanted = []
    if "ehg" in query or "enhanced cpf housing grant" in query:
        wanted = ["CARD_EHG"]
    elif "loan" in query and any(word in query for word in ("eligible", "qualify", "can i get", "can we get")):
        wanted = ["CARD_HDB_LOAN"]
    names = {"age": "user_age", "household_income": "income"}
    return [names.get(f, f) for f in required_fields(wanted, cards)
            if getattr(state, names.get(f, f), None) is None]


# --- Discovery: the one detail that would unlock the most cards -----------
# Team decision (option ii): discovery questions are never held back by a clarifying
# question. When no card matches yet and the matcher's ask_next is a sidebar field, the
# answer carries profile_hint and the website asks the user to fill in "Your situation".

# Card vocabulary -> GraphState field, for the details the website can ask about.
_ASKABLE = {"citizenship": "citizenship", "household_type": "household_type", "first_timer": "first_timer",
            "age": "user_age", "household_income": "income"}


def discovery_question_field(state: GraphState, cards: list[TopicCard]) -> str | None:
    """The sidebar field that would unlock the most cards for a discovery question, or None."""
    if state.intent != "discovery" or state.followup_question:
        return None  # not discovery, or the user is already answering a clarification
    result = match_profile(state, cards)
    field = _ASKABLE.get(result.ask_next or "")
    if result.matched or field is None:
        return None
    asked = [t.content for t in state.history if t.role == "assistant" and t.content.startswith("Please provide:")]
    from .synthesiser import FIELD_LABELS

    if any(FIELD_LABELS.get(field, field) in text for text in asked):
        return None  # asked before in this conversation: answer with what we have
    return field


# --- Suggestions: matched cards the answer didn't cover --------------------

MAX_SUGGESTIONS = 3  # proposal Appendix B


# Words that mean the question is already about a card, so suggesting it would repeat the answer.
_CARD_WORDS = {
    "CARD_EHG": ("ehg", "enhanced cpf"), "CARD_PHG": ("phg", "proximity"),
    "CARD_FAMILY_GRANT": ("family grant", "cpf housing grant"), "CARD_SINGLES_GRANT": ("singles grant",),
    "CARD_STEPUP_GRANT": ("step-up", "step up"), "CARD_HFE_LETTER": ("hfe",),
    "CARD_EIP_SPR_QUOTA": ("eip", "quota", "ethnic"), "CARD_RESALE_OTP_DEPOSIT": ("option to purchase", "otp", "option fee"),
    "CARD_HDB_LOAN": ("loan",), "CARD_LEASE_ELIGIBILITY": ("lease",), "CARD_INCOME_CEILING": ("income ceiling",),
}


def suggestion_cards(card_ids: list[str], cards: list[TopicCard], question: str = "") -> list[TopicCard]:
    """Up to three matched cards with a verbatim overview quote, excluding what the question asks about."""
    by_id = {card.card_id: card for card in cards}
    asked = question.casefold()
    picked = [by_id[i] for i in card_ids if i in by_id and by_id[i].overview is not None
              and not any(word in asked for word in _CARD_WORDS.get(i, ()))]
    return picked[:MAX_SUGGESTIONS]


# --- Income-ceiling notes (Tasha's rules) ----------------------------------
# Grant cards -> ceiling scheme in rules/income_ceilings.json, by household type.
_CEILING_SCHEMES = {
    "CARD_FAMILY_GRANT": {"family": "cpf_housing_grant_family"},
    "CARD_SINGLES_GRANT": {"single": "cpf_housing_grant_single"},
    "CARD_EHG": {"family": "enhanced_cpf_housing_grant_family", "single": "enhanced_cpf_housing_grant_single"},
}
_GRANT_WORDS = ("grant", "ehg", "subsid")


def income_ceiling_checks(state: GraphState, card_ids: list[str], topic: str | None) -> list:
    """Tasha's ceiling checks for the grants in play, verified ceilings only. Never a verdict."""
    from ..rules import IncomeRuleError, check_income_ceiling

    if state.income is None:
        return []
    question = (state.followup_question or state.message).casefold()
    matched_grants = [c for c in _CEILING_SCHEMES if c in card_ids]
    asks_about_grants = topic == "grants" or any(word in question for word in _GRANT_WORDS)
    discovery_with_grants = state.intent == "discovery" and bool(matched_grants)
    if not (asks_about_grants or discovery_with_grants):
        return []
    household = "single" if state.household_type == "single" else "family"
    # Grants in play: matched grant cards, all grants for an overview, else the household's main grants.
    if topic == "grants":
        grant_cards = list(_CEILING_SCHEMES)
    elif matched_grants:
        grant_cards = matched_grants
    elif "ehg" in question or "enhanced" in question:
        grant_cards = ["CARD_EHG"]
    else:
        grant_cards = ["CARD_FAMILY_GRANT", "CARD_SINGLES_GRANT", "CARD_EHG"]
    checks, seen = [], set()
    for card_id in grant_cards:
        scheme = _CEILING_SCHEMES[card_id].get(household)
        if scheme is None or scheme in seen:
            continue
        seen.add(scheme)
        try:
            check = check_income_ceiling(scheme, state.income)
        except IncomeRuleError:
            continue
        if check.verified and check.ceiling is not None:
            checks.append(check)
    return checks
