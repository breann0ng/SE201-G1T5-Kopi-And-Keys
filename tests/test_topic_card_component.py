"""The graph-facing topic-card helpers (components/topic_cards.py).

Written after mutation testing: these branches decide which cards are suggested, when the
website asks for a profile detail, and which income-ceiling notes are shown, and most of
them could be flipped without a test failing. Uses the repo's cards for the ACTIVE snapshot.
"""
from decimal import Decimal

import pytest

from kopi_keys.components import topic_cards as tc
from kopi_keys.schemas import HistoryTurn
from kopi_keys.state import GraphState


@pytest.fixture(scope="module")
def cards():
    return tc.load_cards()


def by_id(cards, *ids):
    found = {c.card_id: c for c in cards}
    return [found[i] for i in ids]


# --- loading and profile mapping ---------------------------------------------

def test_missing_card_folder_warns_and_returns_no_cards(tmp_path):
    with pytest.warns(UserWarning, match="No topic cards"):
        assert tc.load_cards(tmp_path / "nope") == []


def test_private_property_is_read_from_the_users_words_only():
    said_by_bot = GraphState(message="what grants?", history=[
        HistoryTurn(role="assistant", content="Do you own a condo or other private property?")])
    said_by_user = GraphState(message="what grants?", history=[
        HistoryTurn(role="user", content="we own a condo")])
    assert tc.profile_from_state(said_by_bot)["owns_private_property"] is not True
    assert tc.profile_from_state(said_by_user)["owns_private_property"] is True


# --- required_fields ---------------------------------------------------------

def test_required_fields_only_for_the_wanted_cards_in_order_without_duplicates(cards):
    assert tc.required_fields([], cards) == []
    assert tc.required_fields(["CARD_HFE_LETTER"], cards) == ["household_type", "citizenship"]
    both = tc.required_fields(["CARD_HFE_LETTER", "CARD_FAMILY_GRANT"], cards)
    assert both == ["citizenship", "household_type", "first_timer", "household_income", "flat_type"]


# --- personal_eligibility_fields ---------------------------------------------

def test_general_question_asks_for_nothing(cards):
    assert tc.personal_eligibility_fields(GraphState(message="What is the EHG?"), cards) == []


def test_personal_ehg_question_asks_for_the_ehg_inputs_that_are_missing(cards):
    state = GraphState(message="Can I get the enhanced CPF housing grant?", citizenship="SC/SPR", user_age=30)
    assert tc.personal_eligibility_fields(state, cards) == ["household_type", "first_timer", "income"]


def test_personal_loan_question_needs_an_eligibility_word(cards):
    loan = GraphState(message="Am I eligible for an HDB loan?")
    assert tc.personal_eligibility_fields(loan, cards) == ["citizenship", "household_type", "income", "user_age"]
    no_word = GraphState(message="Can I see loan interest rates for me?")
    assert tc.personal_eligibility_fields(no_word, cards) == []


def test_followup_question_is_used_instead_of_the_message(cards):
    state = GraphState(message="30", followup_question="Can I get the EHG?")
    assert "citizenship" in tc.personal_eligibility_fields(state, cards)


# --- discovery_question_field -------------------------------------------------

def test_discovery_with_empty_profile_asks_for_citizenship(cards):
    assert tc.discovery_question_field(GraphState(message="what grants?", intent="discovery"), cards) == "citizenship"


def test_only_discovery_questions_ask(cards):
    assert tc.discovery_question_field(GraphState(message="what grants?", intent="policy"), cards) is None


def test_no_question_while_the_user_is_answering_a_clarification(cards):
    state = GraphState(message="SC", intent="discovery", followup_question="what grants?")
    assert tc.discovery_question_field(state, cards) is None


def test_no_question_once_a_card_matches(cards):
    state = GraphState(message="what grants?", intent="discovery", citizenship="SC/SPR",
                       household_type="couple_family", first_timer=True, user_age=30, income=Decimal(7000))
    assert tc.discovery_question_field(state, cards) is None


def test_field_asked_before_is_not_asked_again(cards):
    asked = HistoryTurn(role="assistant", content="Please provide: citizenship.")
    state = GraphState(message="what grants?", intent="discovery", history=[asked])
    assert tc.discovery_question_field(state, cards) is None


def test_other_assistant_text_does_not_count_as_asking(cards):
    mentioned = HistoryTurn(role="assistant", content="Grants depend on citizenship.")
    user_said = HistoryTurn(role="user", content="Please provide: citizenship.")
    state = GraphState(message="what grants?", intent="discovery", history=[mentioned, user_said])
    assert tc.discovery_question_field(state, cards) == "citizenship"


# --- suggestion_cards ---------------------------------------------------------

def test_suggestions_keep_order_skip_unknown_ids_and_stop_at_three(cards):
    ids = ["CARD_UNKNOWN", "CARD_PHG", "CARD_HFE_LETTER", "CARD_HDB_LOAN", "CARD_EHG"]
    picked = tc.suggestion_cards(ids, cards)
    assert [c.card_id for c in picked] == ["CARD_PHG", "CARD_HFE_LETTER", "CARD_HDB_LOAN"]


def test_suggestions_skip_what_the_question_already_asks_about(cards):
    picked = tc.suggestion_cards(["CARD_PHG", "CARD_HDB_LOAN", "CARD_EHG"], cards, "How does the HDB LOAN work?")
    assert [c.card_id for c in picked] == ["CARD_PHG", "CARD_EHG"]


def test_suggestions_skip_cards_without_an_overview(cards):
    no_overview = by_id(cards, "CARD_PHG")[0].model_copy(update={"overview": None})
    assert tc.suggestion_cards(["CARD_PHG"], [no_overview]) == []


# --- income_ceiling_checks ----------------------------------------------------

FAMILY = dict(message="what grants can we get?", income=Decimal(7000), first_timer=True,
              household_type="couple_family")


def schemes(state, card_ids=(), topic=None):
    return [c.scheme for c in tc.income_ceiling_checks(state, list(card_ids), topic)]


def test_grant_question_lists_the_households_main_grants():
    assert schemes(GraphState(**FAMILY)) == ["cpf_housing_grant_family", "enhanced_cpf_housing_grant_family"]
    single = GraphState(**{**FAMILY, "household_type": "single"})
    assert schemes(single) == ["cpf_housing_grant_single", "enhanced_cpf_housing_grant_single"]


@pytest.mark.parametrize("change", [{"income": None}, {"first_timer": False}, {"subsidy_status": "mixed"}])
def test_no_notes_without_income_for_second_timers_or_mixed_households(change):
    assert schemes(GraphState(**{**FAMILY, **change})) == []


def test_unrelated_question_gets_no_notes():
    assert schemes(GraphState(**{**FAMILY, "message": "hello"})) == []


def test_grants_topic_gets_notes_even_without_grant_words():
    state = GraphState(**{**FAMILY, "message": "hello"})
    assert schemes(state, topic="grants") == ["cpf_housing_grant_family", "enhanced_cpf_housing_grant_family"]


def test_discovery_with_a_matched_grant_card_notes_only_that_grant():
    state = GraphState(**{**FAMILY, "message": "hello", "intent": "discovery"})
    assert schemes(state, ["CARD_FAMILY_GRANT"]) == ["cpf_housing_grant_family"]
    assert schemes(state, []) == []


def test_ehg_question_notes_only_the_ehg():
    assert schemes(GraphState(**{**FAMILY, "message": "tell me about the ehg"})) == ["enhanced_cpf_housing_grant_family"]


def test_followup_question_decides_whether_grants_are_asked_about():
    assert schemes(GraphState(**{**FAMILY, "message": "x", "followup_question": "which grant?"})) != []
    assert schemes(GraphState(**{**FAMILY, "message": "which grant?", "followup_question": "hello"})) == []


def test_each_ceiling_is_listed_once_with_its_figure():
    checks = tc.income_ceiling_checks(GraphState(**FAMILY), ["CARD_FAMILY_GRANT", "CARD_EHG"], "grants")
    assert [c.scheme for c in checks] == ["cpf_housing_grant_family", "enhanced_cpf_housing_grant_family"]
    assert checks[0].ceiling == Decimal(16000) and checks[0].verified
