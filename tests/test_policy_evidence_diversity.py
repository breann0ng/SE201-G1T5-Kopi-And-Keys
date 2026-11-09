"""Context selection must preserve distinct criteria; loan quotes must fit the property scope."""
import json
from datetime import date

from kopi_keys.components.policy_synthesis import PolicySummariser
from kopi_keys.components.verifier import verified_claim_subset, verify
from kopi_keys.llm import Generation
from kopi_keys.schemas import Claim, Draft, PolicyPassage
from kopi_keys.state import GraphState


def passage(cid, text, title="Fictional eligibility conditions"):
    return PolicyPassage(id=cid, title=title, text=text, source_url="demo://diverse-conditions",
        snapshot_id="fictional", verified_on=date(2026, 11, 9))


def test_distinct_table_criteria_under_one_heading_reach_the_model():
    age = passage("age", "| Criteria | Resale flats |\n|---|---|\n| Age | A fictional age condition applies. |")
    property_rule = passage("property", "| Criteria | Resale flats |\n|---|---|\n| Property ownership | A separate fictional ownership condition applies. |")
    duplicate = age.model_copy(update={"id": "age-copy"})
    requests = []
    class Engine:
        def complete(self, messages):
            requests.append(json.loads(messages[-1]["content"]))
            return Generation(model="fixture", text='{"claims": []}')
    PolicySummariser(Engine()).generate(GraphState(message="Explain resale eligibility conditions.",
        route="policy", passages=[age, duplicate, property_rule]))
    assert requests[0]["allowed_citation_ids"] == ["age", "property"]


def test_context_budget_still_limits_distinct_same_heading_criteria(monkeypatch):
    from kopi_keys.components import policy_synthesis
    monkeypatch.setattr(policy_synthesis, "MAX_PASSAGES", 1)
    first = passage("age", "| Criteria | Resale flats |\n|---|---|\n| Age | A fictional age condition applies. |")
    other = first.model_copy(update={"id": "other", "text": first.text.replace("Age", "Property ownership")})
    class Engine:
        def complete(self, messages):
            assert json.loads(messages[-1]["content"])["allowed_citation_ids"] == ["age"]
            return Generation(model="fixture", text='{"claims": []}')
    PolicySummariser(Engine()).generate(GraphState(message="Explain resale eligibility.", route="policy", passages=[first, other]))


def test_same_criterion_different_conditions_are_retained_when_budget_allows():
    first = passage("age-one", "| Criteria | Resale flats |\n|---|---|\n| Age | A first fictional condition applies. |")
    variant = first.model_copy(update={"id": "age-two", "text": first.text.replace("first", "different")})
    class Engine:
        def complete(self, messages):
            assert json.loads(messages[-1]["content"])["allowed_citation_ids"] == ["age-one", "age-two"]
            return Generation(model="fixture", text='{"claims": []}')
    PolicySummariser(Engine()).generate(GraphState(message="Explain resale eligibility.", route="policy", passages=[first, variant]))


OPTIONS = "Housing loans may be offered by HDB or a financial institution, subject to their conditions."
EC_ONLY = "Housing loans are not available for the purchase of Executive Condominium units in this fictional source."


def loan_state(question="How about loans?"):
    source = passage("loans", OPTIONS + " " + EC_ONLY, "Housing loans")
    claims = [Claim(text=text, supporting_quote=text, citation_ids=[source.id]) for text in (OPTIONS, EC_ONLY)]
    return GraphState(message=question, route="policy", passages=[source], draft=Draft(kind="answer", claims=claims))


def test_generic_loan_answer_rejects_unrequested_ec_financing_but_salvages_relevant_options():
    state = loan_state()
    assert any("Executive Condominium purchase" in error for error in verify(state))
    trimmed = verified_claim_subset(state)
    assert trimmed is not None and len(trimmed.claims) == 1
    assert trimmed.claims[0].supporting_quote == OPTIONS
    assert not verify(state.model_copy(update={"draft": trimmed}))


def test_explicit_ec_loan_question_can_use_the_ec_financing_evidence():
    state = loan_state("Are housing loans available for the purchase of Executive Condominium units?")
    state = state.model_copy(update={"draft": state.draft.model_copy(update={"claims": [state.draft.claims[1]]})})
    assert not verify(state)


def test_ec_in_a_past_subsidy_list_is_not_treated_as_ec_purchase_financing():
    quote = "Past subsidies include flats and Executive Condominium units bought from a developer."
    source = passage("subsidies", quote, "Housing loan household conditions")
    state = GraphState(message="What past subsidies affect housing loan eligibility?", route="policy", passages=[source],
        draft=Draft(kind="answer", claims=[Claim(text=quote, supporting_quote=quote, citation_ids=[source.id])]))
    assert not verify(state)


def test_personal_single_profile_rejects_a_required_additional_coapplicant():
    quote = "You must include at least 1 other co-applicant in this fictional scenario."
    source = passage("joint", quote)
    state = GraphState(message="What resale eligibility conditions apply to my sidebar profile?", route="policy",
        citizenship="SC_single", household_type="single", passages=[source],
        draft=Draft(kind="answer", claims=[Claim(text=quote, supporting_quote=quote, citation_ids=[source.id])]))
    assert any("another co-applicant" in e for e in verify(state))
    assert not verify(state.model_copy(update={"message": "Can I buy with another single applicant?"}))
