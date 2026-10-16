"""Topic cards: PLACEHOLDER for the discovery cards (proposal Appendix B).

Owner: to be built by the topic-card / policy-snapshot owner.

What belongs here:
1. `TopicCard`: one reviewed JSON card under data/topic_cards/.
2. `load_cards`: load and validate cards at startup (schema, and that every
   supporting chunk ID exists in the policy snapshot).
3. `match_cards`: compare the buyer profile with each card's triggers and drop
   cards already answered or suggested. Relevance is decided here, in code.
4. `required_fields`: the profile fields the matched cards need. This should
   replace the hard-coded REQUIRED_FIELDS gate in query_router.py.

The graph already calls `match_cards` and stores the result in
`state.candidate_card_ids`. The Synthesiser may only suggest those IDs, and
the Verifier rejects any other ID.
"""

from pathlib import Path

from pydantic import Field

from ..schemas import Contract
from ..state import GraphState


CARD_DIR = Path(__file__).resolve().parents[3] / "data" / "topic_cards"


class TopicCard(Contract):
    id: str = Field(min_length=1)
    title: str
    triggers: dict = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    question_template: str


def load_cards(directory: Path = CARD_DIR) -> list[TopicCard]:
    """Load every *.json card. Chunk-ID validation is still to be written."""
    if not directory.exists():
        return []
    return [TopicCard.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))]


def match_cards(state: GraphState, cards: list[TopicCard]) -> list[str]:
    """PLACEHOLDER: return the IDs of cards relevant to this buyer. None yet."""
    return []


def required_fields(card_ids: list[str], cards: list[TopicCard]) -> list[str]:
    """PLACEHOLDER: fields the matched cards need before they can be judged."""
    return []
