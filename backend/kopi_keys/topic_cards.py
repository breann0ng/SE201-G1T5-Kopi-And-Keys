"""Deterministic topic-card matching for the Stage 1 code gateway.

Code decides which cards are relevant; an LLM may only word them later (proposal,
Appendix B). Rules, matching data/topic_cards/README.md:

- trigger_conditions: any-of within a field, all-of across fields.
- A trigger field the profile has not filled in does not rule a card out: the
  card is *blocked* on that field, so the gateway can ask for it.
- Cards with no triggers ({}) are chosen by topic or intent, never by profile
  alone; pass them in `topics`.
- ask_next is the one missing field that unblocks the most cards (one
  question per turn), ties broken by FIELD_PRIORITY.

Profile values are compared as strings from data/schema/vocab.json, so a
boolean first_timer becomes "true"/"false".
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Order in which to ask when several missing fields unblock the same number of cards.
FIELD_PRIORITY = (
    "citizenship",
    "household_type",
    "first_timer",
    "age",
    "household_income",
    "flat_type",
)


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: str = Field(pattern=r"^CARD_[A-Z_]+$")
    topic_name: str = Field(min_length=1)
    trigger_conditions: dict[str, list[str]]
    required_fields: list[str] = Field(min_length=1)
    supporting_chunk_ids: list[str] = Field(min_length=1)
    question_template: str = Field(min_length=1)
    snapshot_date: date


@dataclass(frozen=True)
class BlockedCard:
    card: TopicCard
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    matched: list[TopicCard] = field(default_factory=list)
    blocked: list[BlockedCard] = field(default_factory=list)
    ask_next: str | None = None

    @property
    def matched_ids(self) -> list[str]:
        return [c.card_id for c in self.matched]


class TopicCardError(ValueError):
    """A card file is invalid or uses a value outside the shared vocabulary."""


def load_cards(
    cards_dir: Path = DATA_DIR / "topic_cards",
    vocab_path: Path = DATA_DIR / "schema" / "vocab.json",
) -> list[TopicCard]:
    """Load and validate every card, failing fast on schema or vocabulary errors."""
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))["fields"]
    cards = []
    for path in sorted(cards_dir.glob("*.json")):
        try:
            card = TopicCard.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise TopicCardError(f"{path.name}: {exc}") from exc
        for key, values in card.trigger_conditions.items():
            if key not in vocab:
                raise TopicCardError(f"{path.name}: trigger field {key!r} not in vocab.json")
            unknown = [v for v in values if v not in vocab[key]["values"]]
            if unknown:
                raise TopicCardError(f"{path.name}: {key} values {unknown} not in vocab.json")
        cards.append(card)
    ids = [c.card_id for c in cards]
    if len(ids) != len(set(ids)):
        raise TopicCardError(f"duplicate card_id in {cards_dir}")
    return cards


def _value(profile: Mapping[str, Any], name: str) -> str | None:
    value = profile.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def match_cards(
    profile: Mapping[str, Any],
    cards: Iterable[TopicCard],
    *,
    topics: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> MatchResult:
    """Match a buyer profile against topic cards.

    profile: BuyerProfile fields plus any extra fields the gateway has collected.
    topics: card IDs selected by intent (e.g. the router saw a lease question);
        these are considered even when they have no trigger conditions.
    exclude: card IDs already answered or suggested in this conversation.
    """
    topics, exclude = set(topics), set(exclude)
    matched: list[TopicCard] = []
    blocked: list[BlockedCard] = []
    for card in cards:
        if card.card_id in exclude:
            continue
        if not card.trigger_conditions and card.card_id not in topics:
            continue
        missing: list[str] = []
        ruled_out = False
        for key, allowed in card.trigger_conditions.items():
            value = _value(profile, key)
            if value is None:
                missing.append(key)
            elif value not in allowed:
                ruled_out = True
                break
        if ruled_out:
            continue
        missing += [f for f in card.required_fields if _value(profile, f) is None and f not in missing]
        if missing:
            blocked.append(BlockedCard(card, tuple(missing)))
        else:
            matched.append(card)

    ask_next = None
    if blocked:
        counts = Counter(f for b in blocked for f in b.missing_fields)
        rank = {f: i for i, f in enumerate(FIELD_PRIORITY)}
        ask_next = min(counts, key=lambda f: (-counts[f], rank.get(f, len(rank)), f))
    return MatchResult(matched=matched, blocked=blocked, ask_next=ask_next)
