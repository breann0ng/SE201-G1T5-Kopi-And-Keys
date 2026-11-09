"""Observed model table wrappers and UI-profile references, using fictional rules."""

import json
from datetime import date

import pytest

from kopi_keys.components.policy_guardrails import policy_focus, score_relevance
from kopi_keys.components.policy_synthesis import PolicySummariser, table_claim
from kopi_keys.components.profile_context import personal_question, profile_issue
from kopi_keys.components.verifier import verify
from kopi_keys.llm import Generation
from kopi_keys.schemas import Claim, Draft, PolicyPassage
from kopi_keys.state import GraphState


CELL = "Applicants must meet the fictional age condition. Preserve this exception too."
SOURCE = PolicyPassage(id="fictional-table", title="Fictional resale eligibility",
    source_url="demo://quote-context", snapshot_id="fictional", verified_on=date(2026, 11, 9),
    text="| Criteria | New Flats | Resale Standard <sup>\\[2\\]</sup> Flats |\n|---|---|---|\n"
         f"| Age | A different condition applies. | {CELL} |")


@pytest.mark.parametrize("prefix", ["Resale Standard [2] Flats", "Resale Standard Flats"])
def test_exact_source_column_wrapper_is_resolved_to_full_source_cell(prefix):
    claim = table_claim(SOURCE, prefix + ": Applicants must meet the fictional age condition.", "Resale eligibility")
    assert claim is not None
    assert claim.supporting_quote == CELL  # omitted qualification is restored, never discarded
    assert claim.source_scope == "Resale Standard Flats"
    state = GraphState(message="Resale eligibility", route="policy", passages=[SOURCE], draft=Draft(kind="answer", claims=[claim]))
    assert not verify(state)


@pytest.mark.parametrize("quote", [
    "Invented category: Applicants must meet the fictional age condition.",
    "New Flats: Applicants must meet the fictional age condition.",
    "Resale Standard [2] Flats: Applicants do not need the fictional age condition.",
    "Resale Standard [2] Flats: ",
])
def test_wrong_column_changed_wording_and_empty_wrappers_remain_unverified(quote):
    assert table_claim(SOURCE, quote, "Resale eligibility") is None
    state = GraphState(message="Resale eligibility", route="policy", passages=[SOURCE],
        draft=Draft(kind="answer", claims=[Claim(text=quote, supporting_quote=quote, citation_ids=[SOURCE.id])]))
    assert verify(state)


def test_wrapper_resolution_needs_a_unique_cell_and_passes_through_real_synthesis():
    duplicated = SOURCE.model_copy(update={"text": SOURCE.text + f"\n| Another criterion | Other. | {CELL} |"})
    assert table_claim(duplicated, "Resale Standard [2] Flats: " + CELL, "Resale eligibility") is None
    class Engine:
        def complete(self, messages):
            return Generation(text=json.dumps({"claims": [{"citation_id": SOURCE.id,
                "supporting_quote": "Resale Standard [2] Flats: Applicants must meet the fictional age condition."}]}), model="fixture")
    state = GraphState(message="Resale eligibility", route="policy", passages=[SOURCE])
    claims, _, errors = PolicySummariser(Engine()).generate(state)
    assert not errors and claims[0].supporting_quote == CELL
    assert not verify(state.model_copy(update={"draft": Draft(kind="answer", claims=claims)}))


@pytest.mark.parametrize("question", [
    "What resale eligibility conditions apply to my sidebar profile?",
    "Based on my sidebar profile, what are the resale eligibility conditions?",
    "What resale eligibility conditions are relevant to our current profile details?",
])
def test_profile_ui_references_do_not_make_real_conditions_irrelevant(question):
    quote = "Applicants must meet the published citizenship and age conditions."
    assert score_relevance(question, quote, SOURCE.title).score >= 0.2


def test_profile_reference_removal_preserves_specific_policy_requirements():
    focused = policy_focus("Based on my sidebar profile, what are the EHG employment conditions?")
    assert "EHG employment conditions" in focused
    assert score_relevance(focused, "Applicants must be citizens.", "EHG").score == 0
    assert score_relevance(focused, "Applicants must meet the employment conditions.", "EHG").score >= 0.2
    assert personal_question("Explain EHG conditions for my sidebar profile")
    assert profile_issue(GraphState(message="Explain EHG conditions for my sidebar profile",
        household_type="single", citizenship="SC_single", first_timer=False, subsidy_status="second_timer"))[0] == "abstain"
