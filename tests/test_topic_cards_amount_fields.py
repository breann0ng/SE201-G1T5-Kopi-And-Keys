"""required_fields (eligibility) vs amount_fields (which amount applies).

A missing amount field must not hide a card the buyer qualifies for; it is
reported in MatchResult.amount_missing instead. Figures come from the 2026-10-15
snapshot: flat type sets the CPF Housing Grant amount (CHUNK_GRANTS_20,
CHUNK_SINGLES_01), and living with vs near parents sets the PHG amount
(CHUNK_GRANTS_14). An SC buying with a non-resident spouse can get the Singles
Grant (CHUNK_SINGLES_05).
"""
import pytest

from kopi_keys.components.topic_cards import required_fields
from kopi_keys.topic_cards import load_cards, match_cards


@pytest.fixture(scope="module")
def cards():
    return load_cards()


def card(cards, card_id):
    return next(c for c in cards if c.card_id == card_id)


SINGLE = {"citizenship": "SC_single", "household_type": "single", "age": 38,
          "household_income": 4500, "first_timer": True}
COUPLE = {"citizenship": "SC/SC", "household_type": "couple_family", "age": 30,
          "household_income": 8000, "first_timer": True}


def test_amount_fields_are_not_eligibility_fields(cards):
    for c in cards:
        assert not set(c.amount_fields) & set(c.required_fields), c.card_id
    assert card(cards, "CARD_FAMILY_GRANT").amount_fields == ["flat_type"]
    assert card(cards, "CARD_SINGLES_GRANT").amount_fields == ["flat_type"]
    assert card(cards, "CARD_PHG").amount_fields == ["distance_to_parents_or_child"]


def test_missing_flat_type_no_longer_hides_the_singles_grant(cards):
    result = match_cards(SINGLE, cards)
    assert "CARD_SINGLES_GRANT" in result.matched_ids
    assert result.amount_missing["CARD_SINGLES_GRANT"] == ("flat_type",)


def test_known_flat_type_leaves_no_amount_gap(cards):
    result = match_cards({**COUPLE, "flat_type": "4-room"}, cards)
    assert "CARD_FAMILY_GRANT" in result.matched_ids
    assert "CARD_FAMILY_GRANT" not in result.amount_missing


def test_missing_eligibility_field_still_blocks(cards):
    profile = {k: v for k, v in COUPLE.items() if k != "household_income"}
    result = match_cards(profile, cards)
    blocked = {b.card.card_id: b.missing_fields for b in result.blocked}
    assert "household_income" in blocked["CARD_FAMILY_GRANT"]
    assert "CARD_FAMILY_GRANT" not in result.matched_ids


def test_ask_next_falls_back_to_an_amount_field(cards):
    # Every card this couple triggers is matched or blocked; with nothing blocked on
    # eligibility, the next question is the amount field most matched cards lack.
    profile = {**COUPLE, "lives_with_or_near_parents_or_child": "with"}
    result = match_cards(profile, cards)
    assert result.blocked == []
    assert result.ask_next in {"flat_type", "distance_to_parents_or_child"}


def test_personal_clarification_still_asks_for_amount_fields(cards):
    # The graph's clarification path reads required_fields(); it must keep asking for
    # flat type before stating a grant amount.
    assert "flat_type" in required_fields(["CARD_FAMILY_GRANT"], cards)


def test_sc_with_non_resident_spouse_can_get_the_singles_grant(cards):
    profile = {"citizenship": "SC/NR", "household_type": "couple_family", "age": 30,
               "household_income": 6000, "first_timer": True}
    assert "CARD_SINGLES_GRANT" in match_cards(profile, cards).matched_ids


def test_fiance_couple_is_not_offered_the_singles_grant(cards):
    profile = {"citizenship": "SC/NR", "household_type": "fiance", "first_timer": True}
    result = match_cards(profile, cards)
    suggested = set(result.matched_ids) | {b.card.card_id for b in result.blocked}
    assert "CARD_SINGLES_GRANT" not in suggested
