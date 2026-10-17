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
import re
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


class OverviewQuote(BaseModel):
    """One verbatim official sentence summarising the card, for overview answers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    quote: str = Field(min_length=10)


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: str = Field(pattern=r"^CARD_[A-Z_]+$")
    topic_name: str = Field(min_length=1)
    trigger_conditions: dict[str, list[str]]
    required_fields: list[str] = Field(min_length=1)
    supporting_chunk_ids: list[str] = Field(min_length=1)
    question_template: str = Field(min_length=1)
    snapshot_date: date
    overview: OverviewQuote | None = None


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


# --- Overview answers for broad questions ---------------------------------
# "What grants are there?" gets an overview table: each listed card's verbatim
# official sentence (card.overview), cited to its chunk. Questions naming one
# scheme are not broad, so they get the normal quoted answer only.

OVERVIEW_TOPICS = {
    "grants": ("CARD_EHG", "CARD_FAMILY_GRANT", "CARD_SINGLES_GRANT", "CARD_PHG", "CARD_STEPUP_GRANT"),
    "loans": ("CARD_HDB_LOAN", "CARD_INCOME_CEILING", "CARD_LEASE_ELIGIBILITY"),
    "buying": ("CARD_HFE_LETTER", "CARD_NON_CITIZEN_ELIGIBILITY", "CARD_EIP_SPR_QUOTA", "CARD_RESALE_OTP_DEPOSIT"),
}
_TOPIC_WORDS = {
    "grants": r"grants?|subsid(?:y|ies)|schemes?",
    "loans": r"(?:housing )?loans?|financing|mortgages?",
    "buying": r"(?:buying|resale|purchase) (?:process|steps?)|steps? to buy|how to buy",
}
_BROAD = re.compile(
    r"\b(?:what|which|any|all|list|types? of|kinds? of|tell me about|know about|overview of|explain|summar\w*)\b"
    r"[^?.]{0,40}?\b(?P<topic>" + "|".join(f"(?P<{k}>{v})" for k, v in _TOPIC_WORDS.items()) + r")\b",
    re.IGNORECASE,
)
_NAMED_SCHEME = re.compile(
    r"\b(?:ehg|enhanced cpf|phg|proximity|step-?up|singles grant|family grant|hfe|eip|spr quota|option fee)\b",
    re.IGNORECASE,
)


def overview_topic(message: str) -> str | None:
    """The broad topic a question asks about ("grants", "loans", "buying"), or None."""
    if _NAMED_SCHEME.search(message):
        return None
    match = _BROAD.search(message)
    if match is None:
        return None
    return next(name for name in _TOPIC_WORDS if match.group(name))
