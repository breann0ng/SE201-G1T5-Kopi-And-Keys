"""Topic cards: the discovery cards (proposal Appendix B), as the graph sees them.

The card format, loader and matcher live in `kopi_keys/topic_cards.py` (topic-card
owner, Person 4); cards are in data/topic_cards/ (see its README). This module
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
