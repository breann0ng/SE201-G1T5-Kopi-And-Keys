"""Restore one continuous source excerpt without weakening grant-relationship checks."""
import json
from datetime import date

import pytest

from kopi_keys.components.policy_synthesis import PolicyClaim, PolicySummariser, connected_grant_quotes
from kopi_keys.components.verifier import verify
from kopi_keys.llm import Generation
from kopi_keys.schemas import Draft, PolicyPassage
from kopi_keys.state import GraphState


QUESTION = "Can EHG and PHG be combined?"
EHG = "For EHG, you must first qualify for the CPF Housing Grant for Resale Flats."
PHG = "You may also apply for PHG if its eligibility conditions are met."


def synthesise(text, quotes, *, missing=(), profile=None, ids=None):
    source = PolicyPassage(id="fictional", title="EHG and PHG conditions", text=text,
        source_url="demo://connected-grants", snapshot_id="fictional", verified_on=date(2026, 11, 9))
    class Engine:
        def complete(self, messages):
            return Generation(model="fixture", text=json.dumps({"claims": [
                {"citation_id": cid, "supporting_quote": quote} for cid, quote in zip(ids or [source.id] * len(quotes), quotes)],
                "missing_evidence": list(missing)}))
    state = GraphState(message=QUESTION, route="policy", passages=[source], **(profile or {}))
    claims, _, errors = PolicySummariser(Engine()).generate(state)
    return state.model_copy(update={"draft": Draft(kind="answer", claims=claims), "synthesis_errors": errors})


@pytest.mark.parametrize("quotes", [[EHG, PHG], [PHG, EHG]])
def test_adjacent_selected_sentences_become_one_original_source_excerpt(quotes):
    state = synthesise(EHG + " " + PHG, quotes)
    assert len(state.draft.claims) == 1
    assert state.draft.claims[0].supporting_quote == EHG + " " + PHG
    assert not verify(state)


def test_explicit_missing_evidence_cannot_be_hidden_by_joining():
    state = synthesise(EHG + " " + PHG, [EHG, PHG], missing=["a separate required condition"])
    assert any("Missing policy evidence" in e for e in verify(state))


@pytest.mark.parametrize("text,quotes", [
    (EHG + " This additional condition must not be skipped. " + PHG, [EHG, PHG]),
    (EHG + " " + PHG, [EHG.replace("must first", "need not"), PHG]),
    (EHG + " " + PHG + " " + EHG, [EHG, PHG]),
    (EHG + " " + PHG, [EHG, EHG]),
])
def test_disconnected_changed_repeated_or_overlapping_quotes_do_not_get_joined(text, quotes):
    state = synthesise(text, quotes)
    assert len(state.draft.claims) == 2
    assert verify(state)


def test_adjacent_descriptions_without_a_connection_are_not_treated_as_stacking():
    left, right = "EHG has its own eligibility conditions.", "PHG has separate eligibility conditions."
    state = synthesise(left + " " + right, [left, right])
    assert len(state.draft.claims) == 2
    assert any("combination rule" in e for e in verify(state))


def test_joining_does_not_conceal_an_opposite_household_scope():
    left, right = "For families, " + EHG, "For singles, " + PHG
    state = synthesise(left + " " + right, [left, right], profile={"household_type": "single"})
    assert len(state.draft.claims) == 2
    assert any("opposite household scope" in e for e in verify(state))


def test_quotes_from_different_sources_cannot_be_stitched_into_a_relationship():
    state = synthesise(EHG + " " + PHG, [EHG, PHG])
    source = state.passages[0]
    other = source.model_copy(update={"id": "another-source"})
    selected = [PolicyClaim(citation_id=source.id, supporting_quote=EHG),
                PolicyClaim(citation_id=other.id, supporting_quote=PHG)]
    result = connected_grant_quotes(selected, {source.id: source, other.id: other}, state, QUESTION)
    assert result == selected
