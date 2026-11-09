"""Sidebar scope regressions: second-timer is not the same as a mixed household."""
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from fakes import FictionalRetriever
from kopi_keys.components.policy_guardrails import household_scope_errors
from kopi_keys.components.policy_synthesis import PolicySummariser
from kopi_keys.components.profile_context import profile_issue
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.components.topic_cards import income_ceiling_checks, load_cards, personal_eligibility_fields
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.llm import Generation
from kopi_keys.schemas import BuyerProfile, ChatRequest, Claim, Draft, HistoryTurn, PolicyPassage
from kopi_keys.state import GraphState, initial_state


QUESTION = "Explain EHG conditions for a person like me"


def profile(status="second_timer", **fields):
    return BuyerProfile(citizenship="SC/SC", household_type="couple_family", age=35,
                        household_income=5000, subsidy_status=status, **fields)


def test_second_timer_personal_ehg_stops_before_retrieval_and_model():
    class NoRetrieval:
        def search(self, *args, **kwargs):
            pytest.fail("No first-timer evidence should be retrieved for this assessment")

    state = run_graph(build_graph(retriever=NoRetrieval(), synthesiser=Synthesiser(None), cards=[]),
                      ChatRequest(message=QUESTION, profile=profile()))
    assert state.response.status == "abstained"
    assert "Second-timer household" in state.response.message
    assert "Mixed first-/second-timer" in state.response.message
    assert state.model_calls == 0
    assert not state.response.citations
    assert not state.response.income_notes
    assert "first-timer applicant, you may be eligible" not in state.response.message


def test_conflicting_household_details_ask_for_correction_instead_of_generic_answer():
    request = ChatRequest(message=QUESTION, profile=BuyerProfile(citizenship="SC_single",
                          household_type="extended_family", subsidy_status="second_timer"))
    result = run_graph(build_graph(retriever=FictionalRetriever(), synthesiser=Synthesiser(None), cards=[]), request)
    assert result.response.status == "clarifying"
    assert "Please correct" in result.response.message
    assert result.model_calls == 0


def test_legacy_false_profile_requires_household_subsidy_clarification():
    result = profile_issue(GraphState(message=QUESTION, first_timer=False, household_type="couple_family"))
    assert result[0] == "clarify"
    assert "mixed" in result[1]


def test_mixed_household_is_not_blanket_rejected_as_second_timer():
    state = GraphState(**initial_state(ChatRequest(message=QUESTION, profile=profile("mixed"))))
    assert state.first_timer is False
    assert state.subsidy_status == "mixed"
    assert profile_issue(state) is None


def test_mixed_single_profile_is_clarified():
    state = GraphState(message=QUESTION, household_type="single", subsidy_status="mixed", first_timer=False)
    issue = profile_issue(state)
    assert issue is not None
    assert issue[0] == "clarify"


def test_person_like_me_requires_missing_profile_fields():
    missing = personal_eligibility_fields(GraphState(message=QUESTION), load_cards())
    assert {"first_timer", "citizenship", "household_type", "income", "user_age"} <= set(missing)


def test_explicit_current_second_timer_profile_wins_over_first_timer_history():
    request = ChatRequest(message=QUESTION, profile=profile(), history=[
        HistoryTurn(role="user", content="We are first-timers, earning $3000."),
    ])
    state = GraphState(**initial_state(request))
    assert state.first_timer is False
    assert state.subsidy_status == "second_timer"
    assert state.income == Decimal("5000.0")


@pytest.mark.parametrize("status", ["second_timer", "mixed"])
def test_no_first_timer_ceiling_note_for_other_subsidy_cohorts(status):
    state = GraphState(message=QUESTION, income=Decimal("5000"), household_type="couple_family",
                       first_timer=False, subsidy_status=status)
    assert income_ceiling_checks(state, ["CARD_EHG"], None) == []


@pytest.mark.parametrize("status,value", [("first_timer", False), ("second_timer", True), ("mixed", True)])
def test_inconsistent_api_subsidy_fields_are_rejected(status, value):
    with pytest.raises(ValidationError, match="same profile"):
        BuyerProfile(first_timer=value, subsidy_status=status)


def test_general_hypothetical_question_is_not_a_second_timer_assessment():
    request = ChatRequest(message="Explain EHG for first-timer families", profile=profile())
    state = run_graph(build_graph(retriever=FictionalRetriever(), synthesiser=Synthesiser(None), cards=[]), request)
    assert state.abstain_reason != "profile_scope"
    assert state.first_timer is True
    assert state.subsidy_status is None


def test_false_first_timer_does_not_disable_opposite_household_guard():
    source = PolicyPassage(id="single", title="EHG for singles", text="Income conditions for singles apply.",
                           source_url="demo://scope", snapshot_id="fixture", verified_on="2026-11-07")
    state = GraphState(message=QUESTION, first_timer=False, household_type="couple_family",
                       passages=[source], draft=Draft(kind="answer", claims=[Claim(
                           text=source.text, supporting_quote=source.text, citation_ids=[source.id])]))
    assert household_scope_errors(state, {source.id: source})


def test_model_receives_distinct_mixed_status():
    source = PolicyPassage(id="ehg", title="EHG for mixed households", text="EHG conditions for mixed households apply.",
                           source_url="demo://scope", snapshot_id="fixture", verified_on="2026-11-07")

    class Engine:
        def complete(self, messages):
            context = json.loads(messages[-1]["content"])
            assert context["profile"]["subsidy_status"] == "mixed"
            assert context["profile"]["first_timer"] is False
            return Generation(text=json.dumps({"claims": [{"citation_id": "ehg", "supporting_quote": source.text}]}), model="fixture")

    PolicySummariser(Engine()).generate(GraphState(message=QUESTION, first_timer=False,
                                                subsidy_status="mixed", passages=[source]))


@pytest.mark.parametrize("prefix,status,citizenship", [
    ("Enhanced CPF Housing Grant (EHG) amount for applicant with non-resident spouse", "first_timer", "SC_single"),
    ("Enhanced CPF Housing Grant amount for couples comprising a first-timer and second-timer households", "first_timer", "SC/SC"),
])
def test_specialised_pdf_table_cannot_be_applied_to_another_personal_profile(prefix, status, citizenship):
    source = PolicyPassage(id="pdf", title="EHG amount for single > Page 2", text=prefix + "\nIncome bands...",
                           source_url="demo://scope", snapshot_id="fixture", verified_on="2026-11-07")
    state = GraphState(message=QUESTION, first_timer=True, subsidy_status=status, citizenship=citizenship,
                       passages=[source], draft=Draft(kind="answer", claims=[Claim(
                           text=source.text, supporting_quote=source.text, citation_ids=[source.id])]))
    assert household_scope_errors(state, {source.id: source})


def test_inconsistent_eligibility_profile_does_not_block_a_pure_price_question():
    state = GraphState(message="Can I know the resale prices of 4 room flats in Tampines?",
                       citizenship="SC_single", household_type="extended_family")
    assert profile_issue(state) is None


@pytest.mark.parametrize("fields", [
    {"citizenship": "SC_single", "household_type": "couple_family"},
    {"citizenship": "SC/SC", "household_type": "single"},
    {"citizenship": "SC/SPR", "household_type": "single"},
    {"citizenship": "SPR/SPR", "household_type": "single"},
    {"citizenship": "SC_single", "subsidy_status": "mixed"},
])
def test_generic_policy_question_stops_on_structurally_conflicting_sidebar(fields):
    class NoRetrieval:
        def search(self, *args, **kwargs):
            pytest.fail("Conflicting profile must be clarified before policy retrieval")
    state = run_graph(build_graph(retriever=NoRetrieval(), synthesiser=Synthesiser(None), cards=[]),
                      ChatRequest(message="Resale eligibility", profile=BuyerProfile(**fields)))
    assert state.response.status == "clarifying" and state.model_calls == 0
    assert "Your situation" in state.response.message
    assert not state.response.citations


def test_consistent_single_profile_is_not_itself_a_discrepancy():
    state = GraphState(message="Resale eligibility", citizenship="SC_single", household_type="single")
    assert profile_issue(state) is None


def test_conflict_is_checked_after_llm_intent_fallback_before_policy_retrieval():
    from kopi_keys.components.intent_fallback import FallbackDecision
    class Classifier:
        def classify(self, message):
            return FallbackDecision(intent="policy", confidence="high", model="fixture")
    class NoRetrieval:
        def search(self, *args, **kwargs):
            pytest.fail("Policy retrieval must not run with an inconsistent profile")
    state = run_graph(build_graph(retriever=NoRetrieval(), synthesiser=Synthesiser(None),
                                 intent_classifier=Classifier(), cards=[]),
                      ChatRequest(message="Help me figure this out", profile=BuyerProfile(
                          citizenship="SC_single", household_type="couple_family")))
    assert state.response.status == "clarifying" and state.model_calls == 1
    assert "Please correct" in state.response.message
