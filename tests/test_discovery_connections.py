"""Topic cards connected to answers: sidebar hint, suggestions, income-ceiling notes; quote checks."""
import pytest

from kopi_keys.components.policy_retrieval import KeywordPolicyRetriever
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest
from kopi_keys.topic_cards import load_cards

COUPLE = {"citizenship": "SC/SC", "age": 30, "household_income": 7000, "first_timer": True,
          "household_type": "couple_family"}
DISCOVERY = "We are first-timers. What should we know before buying a resale flat?"


@pytest.fixture(scope="module")
def graph():
    return build_graph(retriever=KeywordPolicyRetriever(), synthesiser=Synthesiser(None), cards=load_cards())


def ask(graph, message, profile=None, history=()):
    return run_graph(graph, ChatRequest(message=message, profile=profile or {}, history=list(history)))


def test_discovery_without_details_answers_and_hints_at_the_sidebar(graph):
    state = ask(graph, DISCOVERY)
    assert state.response.status == "answered"  # option ii: never held back by a question
    assert state.response.profile_hint
    assert not any("ask_next" in step for step in state.trace)


def test_no_sidebar_hint_once_the_profile_matches_cards(graph):
    assert not ask(graph, DISCOVERY, COUPLE).response.profile_hint


def test_verifier_rejects_a_quote_that_is_only_an_introduction():
    from kopi_keys.components.verifier import verify
    from kopi_keys.schemas import Claim, Draft, PolicyPassage
    from kopi_keys.state import GraphState
    from datetime import date

    text = "The HDB housing loan amount is determined based on the following: your income and age."
    source = PolicyPassage(id="P1", title="Loan", text=text, source_url="https://www.hdb.gov.sg/x",
                           verified_on=date(2026, 10, 15), snapshot_id="t")
    def errors(quote):
        claim = Claim(text=quote, citation_ids=["P1"], supporting_quote=quote)
        return verify(GraphState(message="q", route="policy", passages=[source],
                                 draft=Draft(kind="answer", claims=[claim])))
    assert any("ends with ':'" in e for e in errors("The HDB housing loan amount is determined based on the following:"))
    assert not errors("your income and age")


def test_matched_cards_become_cited_suggestions(graph):
    state = ask(graph, "How long is an HFE letter valid?", COUPLE)
    ids = {p.id for p in state.passages}
    assert [s.card_id for s in state.response.suggestions] == ["CARD_EHG"]
    assert all(cid in ids for s in state.response.suggestions for cid in s.citation_ids)
    assert state.verification_passed


def test_no_suggestion_for_the_scheme_the_question_already_asks_about(graph):
    state = ask(graph, "How much EHG can I get?", COUPLE)
    assert "CARD_EHG" not in [s.card_id for s in state.response.suggestions]


def test_grant_questions_get_verified_income_notes_and_other_questions_do_not(graph):
    grants = ask(graph, "How much EHG can I get?", COUPLE).response.income_notes
    assert [n.scheme for n in grants] == ["enhanced_cpf_housing_grant_family"]
    assert grants[0].within_ceiling and grants[0].ceiling == "9,000"
    assert "only HDB's HFE letter confirms eligibility" in grants[0].message
    assert not ask(graph, "How long is an HFE letter valid?", COUPLE).response.income_notes
    assert not ask(graph, "How much EHG can I get?").response.income_notes  # no income stated


def test_verifier_accepts_a_word_the_source_hyphenates_across_lines():
    from datetime import date

    from kopi_keys.components.verifier import verify
    from kopi_keys.schemas import Claim, Draft, PolicyPassage
    from kopi_keys.state import GraphState

    source = PolicyPassage(id="P1", title="EHG", text="EHG amount for first-\ntimer households", snapshot_id="t",
                           source_url="https://www.hdb.gov.sg/x", verified_on=date(2026, 10, 15))
    def errors(quote):
        claim = Claim(text=quote, citation_ids=["P1"], supporting_quote=quote)
        return verify(GraphState(message="q", route="policy", passages=[source],
                                 draft=Draft(kind="answer", claims=[claim])))
    assert not errors("EHG amount for first-timer households")
    assert errors("EHG amount for second-timer households")  # still exact otherwise


def test_one_reply_can_answer_several_requested_numbers():
    """'22, 50000' to 'Please provide: age, household income.' resumes the original question."""
    from kopi_keys.schemas import ChatRequest
    from kopi_keys.state import initial_state

    history = [
        {"role": "user", "content": "Am I eligible for the Enhanced CPF Housing Grant?"},
        {"role": "assistant", "content": "Please provide: age, household income."},
    ]
    state = initial_state(ChatRequest(message="22, 50000", profile={}, history=history))
    assert state["followup_question"] == "Am I eligible for the Enhanced CPF Housing Grant?"
    assert (state["user_age"], state["income"]) == (22, 50000)


def test_worked_examples_are_recognised():
    """Added 2026-10-17 (Sandra): HDB's fictional households are ranked below the rules."""
    import json
    from pathlib import Path
    from kopi_keys.components.policy_retrieval import is_worked_example

    chunks = Path(__file__).resolve().parents[1] / "data/policy_chunks/2026-10-15/chunks.jsonl"
    found = sorted(c["chunk_id"] for c in map(json.loads, chunks.read_text(encoding="utf-8").splitlines())
                   if is_worked_example(c["content"]))
    assert found == ["CHUNK_EHG_12", "CHUNK_EHG_14", "CHUNK_EHG_23", "CHUNK_EHG_26"]
