"""Rule properties of the card matcher, checked over a grid of generated profiles.

Instead of a few hand-picked examples, every combination of citizenship, household
type, first-timer status, private-property ownership and income (every $500 from
$0 to $30,000) is matched, and properties that must hold for all of them are
asserted. No figures are copied here: ceilings are read from Tasha's
rules/income_ceilings.json through check_income_ceiling, read-only.
"""
from decimal import Decimal
from itertools import product

import pytest

from kopi_keys.rules import check_income_ceiling
from kopi_keys.rules.income import NEAR_BOUNDARY_FRACTION
from kopi_keys.topic_cards import load_cards, match_cards, owns_private_property, profile_with_message_facts

CITIZENSHIP = ["SC/SC", "SC/SPR", "SPR/SPR", "SC/NR", "SC_single", "foreigner_only"]
HOUSEHOLD = ["couple_family", "fiance", "single", "extended_family"]
FIRST_TIMER = [True, False]
OWNS = [True, False, None]
INCOMES = list(range(0, 30_001, 500))
INCOME_CAPPED = {"CARD_EHG", "CARD_FAMILY_GRANT", "CARD_SINGLES_GRANT"}
PRIVATE_EXCLUDED = {"CARD_EHG", "CARD_FAMILY_GRANT", "CARD_SINGLES_GRANT", "CARD_STEPUP_GRANT"}


@pytest.fixture(scope="module")
def cards():
    return load_cards()


def outcome(result, card_id):
    if card_id in result.matched_ids:
        return "eligible"
    if any(b.card.card_id == card_id for b in result.blocked):
        return "needs_info"
    return "ruled_out"


def suggested(result):
    return set(result.matched_ids) | {b.card.card_id for b in result.blocked}


def base_profiles():
    for cit, house, first, owns in product(CITIZENSHIP, HOUSEHOLD, FIRST_TIMER, OWNS):
        profile = {"citizenship": cit, "household_type": house, "first_timer": first, "age": 36}
        if owns is not None:
            profile["owns_private_property"] = owns
        yield profile


def test_raising_income_never_adds_an_income_capped_card(cards):
    for profile in base_profiles():
        previous = None
        for income in INCOMES:
            now = suggested(match_cards({**profile, "household_income": income}, cards)) & INCOME_CAPPED
            if previous is not None:
                assert now <= previous, (profile, income, now - previous)
            previous = now


def test_income_never_changes_the_phg_outcome(cards):
    # The PHG states no income ceiling, so income must never filter it.
    for profile in base_profiles():
        outcomes = {outcome(match_cards({**profile, "household_income": i}, cards), "CARD_PHG") for i in INCOMES}
        assert len(outcomes) == 1, (profile, outcomes)


def test_owning_private_property_rules_out_the_cpf_grants_only(cards):
    for profile in base_profiles():
        profile = {**profile, "owns_private_property": True, "household_income": 5000}
        result = match_cards(profile, cards)
        assert not suggested(result) & PRIVATE_EXCLUDED, profile
        without = match_cards({**profile, "owns_private_property": False}, cards)
        # Every other card is untouched by the exclusion.
        assert suggested(result) == suggested(without) - PRIVATE_EXCLUDED, profile


def test_every_exclusion_has_a_cited_reason(cards):
    profile = {"citizenship": "SC/SC", "household_type": "couple_family", "first_timer": True,
               "owns_private_property": True}
    reasons = {r.card.card_id: r.reason for r in match_cards(profile, cards).ruled_out}
    assert set(reasons) == {"CARD_EHG", "CARD_FAMILY_GRANT"}  # the grants this couple triggers
    assert all("private" in text and "(CHUNK_" in text for text in reasons.values())


def test_matched_cards_come_in_priority_order(cards):
    for profile in base_profiles():
        result = match_cards({**profile, "household_income": 4000, "flat_type": "4-room",
                              "lives_with_or_near_parents_or_child": "with"}, cards)
        priorities = [c.priority for c in result.matched]
        assert priorities == sorted(priorities), profile


@pytest.mark.parametrize("scheme", ["enhanced_cpf_housing_grant_family", "cpf_housing_grant_family"])
def test_ceiling_boundary_and_near_boundary_margin(cards, scheme):
    """At the ceiling the card stays; it is ruled out only above ceiling * (1 + margin).

    The 5% margin is deliberate: HDB assesses income over 12 months, so a stated
    figure just above the ceiling should send the buyer to the HFE letter, not hide the
    grant. Example: the EHG (Families) ceiling of $9,000 rules a card out only above
    $9,450. Note the matcher uses the highest amount any variant states (e.g. the
    extended-family figure), so the cut-off may sit above the base ceiling.
    """
    card_id = {"enhanced_cpf_housing_grant_family": "CARD_EHG",
               "cpf_housing_grant_family": "CARD_FAMILY_GRANT"}[scheme]
    profile = {"citizenship": "SC/SC", "household_type": "couple_family", "first_timer": True, "age": 30}
    ceiling = check_income_ceiling(scheme, 1000).ceiling
    assert outcome(match_cards({**profile, "household_income": int(ceiling)}, cards), card_id) == "eligible"
    # Find the cut-off from the card's own rule, then check both sides of it.
    cutoff = next(i for i in range(int(ceiling), int(ceiling) * 3, 50)
                  if outcome(match_cards({**profile, "household_income": i}, cards), card_id) == "ruled_out")
    assert cutoff > ceiling * (1 + NEAR_BOUNDARY_FRACTION)
    assert outcome(match_cards({**profile, "household_income": cutoff - 50}, cards), card_id) == "eligible"


def test_ehg_family_margin_example():
    assert check_income_ceiling("enhanced_cpf_housing_grant_family", 1000).ceiling == Decimal("9000")
    assert Decimal("9000") * (1 + NEAR_BOUNDARY_FRACTION) == Decimal("9450")


@pytest.mark.parametrize("text, expected", [
    ("We have a condo, thinking of downgrading to HDB resale.", True),
    ("I own a 3-bedroom condominium in Bishan", True),
    ("Our condo is fully paid", True),
    ("We currently own a private property", True),
    ("We sold our condo last year", None),           # 30-month rule depends on the date
    ("My parents' condo is in Tampines", None),       # a PHG proximity reference
    ("my parents condo is 2km away", None),
    ("We live in a condo now", None),                 # renting is not owning
    ("We bought an executive condo", None),           # EC status depends on its age
    ("We don't own any private property", False),
    ("I have never owned a condo", False),
    ("We have a car and two kids", None),
])
def test_private_property_detection(text, expected):
    assert owns_private_property(text) is expected


def test_profile_value_wins_over_the_message():
    assert profile_with_message_facts({"owns_private_property": False}, "we have a condo")["owns_private_property"] is False
    assert profile_with_message_facts({}, "we have a condo")["owns_private_property"] is True
    assert "owns_private_property" not in profile_with_message_facts({}, "4-room in Tampines?")
