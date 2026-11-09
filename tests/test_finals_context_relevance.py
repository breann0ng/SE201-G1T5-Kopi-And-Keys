"""Development regressions for shorthand, sidebar conflicts and scoped relevance rescue."""
from datetime import date

import pytest

from kopi_keys.components.profile_context import message_profile_conflict, profile_issue
from kopi_keys.components.query_router import EXTRACTED_FIELDS, extract_fields, route_query
from kopi_keys.components.policy_synthesis import table_claim
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.components.topic_cards import load_cards, personal_eligibility_fields
from kopi_keys.components.verifier import policy_relevance_scores, table_row_answers_question, verify
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest, Draft, PolicyPassage, PriceResult
from kopi_keys.state import GraphState, initial_state


@pytest.mark.parametrize("flat", ["3rm", "3 rm", "3-rm", "3rooms", "3room", "3-room"])
def test_explicit_room_alias_replaces_an_earlier_four_room_filter(flat):
    request = ChatRequest(message=f"Price of {flat} in AMK", history=[
        {"role": "user", "content": "4-room prices in Bedok"},
        {"role": "assistant", "content": "4-room flats in Bedok."},
    ])
    state = GraphState(**initial_state(request))
    known = {f: getattr(state, f) for f in (*EXTRACTED_FIELDS, "start_month", "end_month")}
    result = route_query(state.message, known, context_question=state.followup_question)
    assert result.route == "price" and result.flat_type == "3 ROOM" and result.town == "ANG MO KIO"


@pytest.mark.parametrize("scheme", ["Family Grant", "Family Grants"])
def test_family_grant_name_does_not_state_the_users_household(scheme):
    question = f"Can I stack the {scheme}, EHG and PHG?"
    assert extract_fields(question)["household_type"] is None
    assert extract_fields(f"For families, can the {scheme} and EHG be combined?")["household_type"] == "couple_family"
    assert route_query(question, {"household_type": "single"}).household_type == "single"


@pytest.mark.parametrize("relationship", ["wife", "husband", "spouse"])
def test_single_sidebar_and_a_current_spouse_are_clarified_before_tools(relationship):
    class NoRetrieval:
        def search(self, *args, **kwargs):
            pytest.fail("Do not search using a contradictory household")
    request = ChatRequest(message=f"My {relationship} is PR and I'm Singaporean, can we buy resale?",
        profile={"citizenship": "SC_single", "household_type": "single"})
    state = run_graph(build_graph(retriever=NoRetrieval(), synthesiser=Synthesiser(None), cards=[]), request)
    assert state.response.status == "clarifying" and state.model_calls == 0
    assert "sidebar" in state.response.message and "spouse" in state.response.message
    assert "not been changed automatically" in state.response.message


@pytest.mark.parametrize("message", [
    "My late wife was PR; can I buy resale?", "My wife is deceased; can I buy resale?",
    "My friend and his wife are PR; can they buy resale?",
])
def test_past_spouses_and_other_peoples_households_are_not_sidebar_contradictions(message):
    assert message_profile_conflict(GraphState(message=message, citizenship="SC_single", household_type="single")) is None


@pytest.mark.parametrize("message", [
    "If I marry, my wife is PR and I'm Singaporean; can we buy resale?",
    "If I get married, my husband is PR; can we buy resale?",
    "Suppose I were married and my spouse is PR; can we buy resale?",
    "If I were to marry, my wife holds PR; can we buy resale?",
    "Imagine we get married and my spouse has PR; can we buy resale?",
    "If I'm married, my wife is PR; can we buy resale?",
])
def test_hypothetical_marriage_does_not_assert_a_current_spouse(message):
    state = GraphState(message=message, citizenship="SC_single", household_type="single")
    assert message_profile_conflict(state) is None
    assert profile_issue(state) is None


@pytest.mark.parametrize("message", [
    "If my income changes, my wife is PR and I'm Singaporean; can we buy resale?",
    "If I marry, my wife is PR. My wife is PR already; can we buy resale?",
    "If I marry, my wife is PR, but my spouse is PR already; can we buy resale?",
])
def test_unrelated_conditions_and_separate_current_spouse_statements_still_conflict(message):
    state = GraphState(message=message, citizenship="SC_single", household_type="single")
    assert message_profile_conflict(state) is not None
    assert profile_issue(state)[0] == "clarify"


def test_consistent_couple_or_empty_sidebar_does_not_trigger_message_conflict():
    message = "My wife is PR and I'm Singaporean, can we buy resale?"
    assert message_profile_conflict(GraphState(message=message)) is None
    assert message_profile_conflict(GraphState(message=message, citizenship="SC/SPR", household_type="couple_family")) is None


def test_general_stacking_needs_no_personal_amount_inputs_but_assessment_still_does():
    cards = load_cards()
    assert personal_eligibility_fields(GraphState(message="Can I stack the Family Grant, EHG and PHG?"), cards) == []
    for question in ("Can I combine EHG and PHG, and am I eligible?", "Can I stack EHG and PHG and how much can I receive?"):
        assert personal_eligibility_fields(GraphState(message=question), cards)


def scoped_state(question, criterion, requirement, title="HDB housing loan"):
    source = PolicyPassage(id="fictional", title=title, source_url="demo://scoped-relevance",
        text=f"| Criteria | Housing loan |\n|---|---|\n| {criterion} | {requirement} |",
        snapshot_id="fictional", verified_on=date(2026, 11, 9))
    claim = table_claim(source, requirement, question)
    assert claim is not None
    return GraphState(message=question, route="policy", passages=[source], draft=Draft(kind="answer", claims=[claim]))


def test_loan_income_table_cannot_answer_an_ehg_income_question():
    state = scoped_state("What is the EHG income ceiling?", "Monthly household income ceiling",
        "Household income must not exceed this fictional loan ceiling.")
    assert policy_relevance_scores(state)[0]["score"] == 0
    assert any("Low policy relevance" in e for e in verify(state))


def test_generic_citizenship_row_cannot_bypass_a_named_grants_relevance():
    state = scoped_state("What is the EHG citizenship requirement?", "Citizenship", "You must be an SC or SPR.")
    assert not table_row_answers_question(state.message, state.draft.claims[0])
    assert any("Low policy relevance" in e for e in verify(state))


def test_citizenship_label_does_not_answer_a_missing_residency_duration():
    question = ("Before planning viewings, arranging our paperwork, checking neighbourhoods and making preparations, "
                "how long must my PR spouse have residency to buy resale?")
    state = scoped_state(question, "Citizenship", "You must be an SC or SPR.")
    assert policy_relevance_scores(state)[0]["score"] < 0.2
    assert not table_row_answers_question(state.message, state.draft.claims[0])
    assert any("Low policy relevance" in e for e in verify(state))


def test_citizenship_row_with_a_real_duration_remains_eligible_for_context_rescue():
    state = scoped_state("How long must my PR spouse have residency to buy resale?", "Citizenship",
        "An SPR household must hold SPR status for 3 years in this fictional example.")
    assert table_row_answers_question(state.message, state.draft.claims[0])
    assert not verify(state)


def test_zero_sales_reports_filters_and_widening_without_a_model_call():
    class EmptyPrices:
        def query(self, filters):
            return PriceResult(query_id="empty", filters=filters, volume=0)
    state = run_graph(build_graph(price_tool=EmptyPrices(), synthesiser=Synthesiser(None), cards=[]),
        ChatRequest(message="1-room flat prices in Bukit Timah in 2025"))
    assert state.response.status == "abstained" and state.model_calls == 0
    assert "abstention:no_transactions" in state.response.trace
    assert "No matching resale transactions" in state.response.message and "wider date range" in state.response.message
