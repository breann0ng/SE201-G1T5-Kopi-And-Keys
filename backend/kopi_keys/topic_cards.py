"""Deterministic topic-card matching for the Stage 1 code gateway.

Code decides which cards are relevant; an LLM may only word them later (proposal,
Appendix B). Rules, matching data/topic_cards/README.md:

- trigger_conditions: any-of within a field, all-of across fields.
- A trigger field the profile has not filled in does not rule a card out: the
  card is *blocked* on that field, so the gateway can ask for it.
- required_fields decide eligibility: a missing one blocks the card.
  amount_fields only change which amount applies (e.g. flat type for the CPF
  Housing Grant): a missing one does not block the card, it is reported in
  MatchResult.amount_missing so the answer can say the amount depends on it.
- Cards with no triggers ({}) are chosen by topic or intent, never by profile
  alone; pass them in `topics`.
- ask_next is the one missing field that unblocks the most cards (one
  question per turn), ties broken by FIELD_PRIORITY. With no blocked card it is
  the amount field missing from the most matched cards, or None.
- exclude_if: a known profile fact that rules a card out regardless of other
  fields (e.g. owning private property rules out the CPF grants), with the
  reason and the chunk that states the rule, reported in MatchResult.ruled_out.
  owns_private_property is not a sidebar field yet; owns_private_property()
  reads it from the user's own words ("we have a condo").
- Matched cards are returned in card priority order (grant stack first).
- income_schemes: a known household income above every ceiling the card's
  schemes state (rules/income_ceilings.json, including HDB's variants such as
  $24,000 for extended families) rules the card out, with a reason. Within the
  near-boundary margin, or with an unverified ceiling, the card is kept.

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
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .rules import IncomeRuleError, check_income_ceiling
from .rules.income import NEAR_BOUNDARY_FRACTION

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def snapshot_cards_dir(snapshot: str | None = None, data_dir: Path = DATA_DIR) -> Path:
    """data/topic_cards/<snapshot>/: one folder per policy snapshot, so cards built for a
    candidate snapshot never replace the cards the advisor serves. Default: ACTIVE."""
    if snapshot is None:
        snapshot = (data_dir / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
    return data_dir / "topic_cards" / snapshot

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


class ExcludeRule(BaseModel):
    """A profile fact that rules the card out, cited to the chunk stating the rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    values: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    chunk_id: str


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: str = Field(pattern=r"^CARD_[A-Z_]+$")
    topic_name: str = Field(min_length=1)
    trigger_conditions: dict[str, list[str]]
    required_fields: list[str] = Field(min_length=1)
    # Fields that only select the amount, never eligibility; missing ones don't block.
    amount_fields: list[str] = Field(default_factory=list)
    supporting_chunk_ids: list[str] = Field(min_length=1)
    question_template: str = Field(min_length=1)
    snapshot_date: date
    overview: OverviewQuote | None = None
    # Household ("family" / "single") -> scheme in rules/income_ceilings.json.
    income_schemes: dict[Literal["family", "single"], str] = Field(default_factory=dict)
    group: Literal["grant", "eligibility", "loan", "buying"] | None = None
    priority: int = 100  # lower shows first
    exclude_if: list[ExcludeRule] = Field(default_factory=list)


@dataclass(frozen=True)
class BlockedCard:
    card: TopicCard
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class RuledOutCard:
    card: TopicCard
    reason: str


@dataclass(frozen=True)
class MatchResult:
    matched: list[TopicCard] = field(default_factory=list)
    blocked: list[BlockedCard] = field(default_factory=list)
    ask_next: str | None = None
    ruled_out: list[RuledOutCard] = field(default_factory=list)
    # Matched card ID -> amount fields the profile lacks (the amount can't be stated yet).
    amount_missing: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def matched_ids(self) -> list[str]:
        return [c.card_id for c in self.matched]


class TopicCardError(ValueError):
    """A card file is invalid or uses a value outside the shared vocabulary."""


def load_cards(
    cards_dir: Path | None = None,
    vocab_path: Path = DATA_DIR / "schema" / "vocab.json",
) -> list[TopicCard]:
    """Load and validate every card, failing fast on schema or vocabulary errors.

    cards_dir defaults to the ACTIVE snapshot's folder (snapshot_cards_dir()).
    """
    cards_dir = snapshot_cards_dir() if cards_dir is None else cards_dir
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


_AMOUNT = re.compile(r"\$([\d,]+)")


def income_rule_out(card: TopicCard, income: Any) -> str | None:
    """Why this household income rules the card out, or None.

    Conservative: only when the income is above the highest amount any of the card's
    ceilings states, variants included, and outside the near-boundary margin. An
    unknown scheme, an unverified ceiling or an invalid income never rules a card out.
    """
    highest, label, amount = None, "", None
    for scheme in card.income_schemes.values():
        try:
            check = check_income_ceiling(scheme, income)
        except IncomeRuleError:
            return None
        if not check.verified or check.ceiling is None:
            return None
        stated = [check.ceiling] + [Decimal(a.replace(",", "")) for c in check.conditions for a in _AMOUNT.findall(c)]
        if highest is None or max(stated) > highest:
            highest, label, amount = max(stated), check.label, check.income
    if highest is None or amount <= highest * (1 + NEAR_BOUNDARY_FRACTION):
        return None
    return f"income of ${amount:,.0f} is above the highest {label} ceiling of ${highest:,.0f}"


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
    ruled_out_by_income: list[RuledOutCard] = []
    amount_missing: dict[str, tuple[str, ...]] = {}
    income = _value(profile, "household_income")
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
        excluded = next((r for r in card.exclude_if if _value(profile, r.field) in r.values), None)
        if excluded is not None:
            ruled_out_by_income.append(RuledOutCard(card, f"{excluded.reason} ({excluded.chunk_id})"))
            continue
        reason = income_rule_out(card, income) if card.income_schemes and income is not None else None
        if reason is not None:
            ruled_out_by_income.append(RuledOutCard(card, reason))
            continue
        missing += [f for f in card.required_fields if _value(profile, f) is None and f not in missing]
        if missing:
            blocked.append(BlockedCard(card, tuple(missing)))
            continue
        matched.append(card)
        lacking = tuple(f for f in card.amount_fields if _value(profile, f) is None)
        if lacking:
            amount_missing[card.card_id] = lacking

    matched.sort(key=lambda c: c.priority)  # stable: file order within a priority
    ask_next = None
    counts = Counter(f for b in blocked for f in b.missing_fields) or Counter(
        f for fields in amount_missing.values() for f in fields)
    if counts:
        rank = {f: i for i, f in enumerate(FIELD_PRIORITY)}
        ask_next = min(counts, key=lambda f: (-counts[f], rank.get(f, len(rank)), f))
    return MatchResult(matched=matched, blocked=blocked, ask_next=ask_next, ruled_out=ruled_out_by_income,
                       amount_missing=amount_missing)


# --- Facts read from the user's own words --------------------------------
# Until the profile has an owns_private_property field, a first-person statement of
# owning a condo / private property sets it. Only present ownership counts: "we sold
# our condo" leaves it unknown (the 30-month disposal rule depends on the date), and a
# parent's condo is a PHG proximity reference, not the buyer's property. Executive
# condos are left out: whether one counts as private property depends on its age.

_PRIVATE_HOME = (r"(?:(?<!executive )condo(?:minium)?s?|private (?:property|properties|apartment|home|house)"
                 r"|landed (?:house|home|property))")
_KIN = (r"(?:parents?'?|mum'?s?|mom'?s?|mother'?s?|dad'?s?|father'?s?|in-?laws?'?|grand\w*|sister'?s?"
        r"|brother'?s?|son'?s?|daughter'?s?|child(?:ren)?'?s?)")
_OWNS = re.compile(
    r"\b(?:we|i)\s+(?:currently\s+|still\s+|already\s+|now\s+|also\s+|jointly\s+)?(?:own|have|bought)\s+"
    r"(?:a|an|one|our|my)\s+(?:[\w-]+\s+){0,2}?" + _PRIVATE_HOME + r"\b"
    r"|\b(?:my|our)\s+(?!" + _KIN + r"\s)(?:[\w-]+\s+)?" + _PRIVATE_HOME + r"\b",
    re.IGNORECASE,
)
_PAST = re.compile(r"\b(?:sold|disposed of|used to (?:own|have)|previously owned|no longer own)\b", re.IGNORECASE)
_NOT_OWN = re.compile(
    r"\b(?:we|i)\s+(?:have\s+)?(?:never|don'?t|do not|didn'?t|did not)\s+(?:own(?:ed)?|ha(?:ve|d))\b[^.?!]{0,30}?"
    + _PRIVATE_HOME, re.IGNORECASE)


def owns_private_property(text: str) -> bool | None:
    """True if the buyer says they own private property now, False if they say they don't, else None."""
    if _NOT_OWN.search(text):
        return False
    if _PAST.search(text):
        return None
    return True if _OWNS.search(text) else None


def profile_with_message_facts(profile: Mapping[str, Any], text: str) -> dict:
    """The profile plus facts stated in the user's words; profile values always win."""
    out = dict(profile)
    if out.get("owns_private_property") is None:
        fact = owns_private_property(text)
        if fact is not None:
            out["owns_private_property"] = fact
    return out


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
