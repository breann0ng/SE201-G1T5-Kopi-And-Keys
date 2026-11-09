"""Regressions for findings from the merged-system development review."""
from decimal import Decimal

import pytest

from kopi_keys.components.query_router import route_query
from kopi_keys.components.verifier import verify
from kopi_keys.schemas import ChatRequest, Draft, PriceFilters, PriceResult
from kopi_keys.state import GraphState, initial_state


@pytest.mark.parametrize("phrase,lease,floor", [
    ("newer 4-room flats", "80_plus", None),
    ("newer resale flats", "80_plus", None),
    ("4-room flats with under 60 years of lease left", "under_60", None),
    ("4-room flats with 60–79 years left", "60_79", None),
    ("4-room flats with 80+ years left", "80_plus", None),
    ("high-floor 4-room flats", None, "high"),
    ("middle floor 4-room flats", None, "mid"),
    ("low floor 4-room flats", None, "low"),
    ("newer high floor flats", "80_plus", "high"),
    ("4-room flats on the 8th floor", None, None),
    ("new flats", None, None),
])
def test_requested_bands_are_extracted_without_inventing_arbitrary_thresholds(phrase, lease, floor):
    out = route_query(f"What are prices for {phrase} in Bishan?")
    assert (out.lease_band, out.storey_band) == (lease, floor)


def test_router_preserves_api_filters_and_allows_an_explicit_band_change():
    filters = PriceFilters(town="BISHAN", flat_type="4 ROOM", start_month="2026-01",
                           end_month="2026-10", lease_band="80_plus", storey_band="high")
    state = initial_state(ChatRequest(message="What are resale prices?", price_filters=filters))
    out = route_query(state["message"], state)
    assert (out.lease_band, out.storey_band) == ("80_plus", "high")
    out = route_query("What about low floor flats?", out.model_dump(), context_question=state["message"])
    assert (out.lease_band, out.storey_band) == ("80_plus", "low")


def test_clarification_preserves_band_from_original_question():
    question = "What are prices for high floor flats in Bishan?"
    state = initial_state(ChatRequest(message="4-room", history=[
        {"role": "user", "content": question},
        {"role": "assistant", "content": "Please provide: flat type."},
    ]))
    out = route_query(state["message"], state, context_question=state["followup_question"])
    assert out.storey_band == "high" and out.flat_type == "4 ROOM"


@pytest.mark.parametrize("question", [
    "I own a 2-room flat in Bedok and want to buy a 3-room in Tampines. What do they cost?",
    "I am buying a 3-room in Tampines. My current home is a 2-room in Bedok. What are resale prices?",
    "We own a 2-room in Bedok. What are 3-room prices in Tampines?",
])
def test_purchase_target_wins_over_current_home_in_either_order(question):
    out = route_query(question)
    assert (out.flat_type, out.town) == ("3 ROOM", "TAMPINES")


def test_presentational_footnotes_preserve_the_actual_reference_number():
    from kopi_keys.components.policy_guardrails import normalized_policy_text
    original = r"A fictional condition<sup>\[4\]</sup><br>requires the checklist."
    assert normalized_policy_text(original) == "A fictional condition[4] requires the checklist."
    assert normalized_policy_text(original) != normalized_policy_text("A fictional condition[5] requires the checklist.")


def test_policy_relevance_ignores_only_transaction_clause_not_grant_amounts():
    from kopi_keys.components.policy_guardrails import policy_focus
    assert policy_focus("Explain PHG, and what do flats in Bishan cost?") == "Explain PHG, "
    assert "EHG" in policy_focus("Explain PHG and how much EHG can I receive?")


def test_age_wording_and_percentage_conditions_keep_their_policy_aspect():
    from kopi_keys.components.policy_guardrails import score_relevance
    age = score_relevance("I'm single, turning 35 next year. Can I buy anything now?",
                          "At least 35 years old (unmarried or divorced)", "Single buyer eligibility", "Age")
    assert age.score >= 0.2
    amount = score_relevance("If I take an HDB loan, how much do I pay upfront?",
                             "25% of the lower of resale price or value", "Resale transaction",
                             "Housing Loan from HDB Initial Payment")
    assert amount.score >= 0.2
    unrelated = score_relevance("What is the EHG employment condition?", "25% of the price", "EHG")
    assert unrelated.score == 0


def test_mixed_question_does_not_ask_policy_model_to_supply_sql_prices():
    import json
    from datetime import date
    from kopi_keys.components.policy_synthesis import PolicySummariser
    from kopi_keys.llm import Generation
    from kopi_keys.schemas import PolicyPassage
    class Engine:
        def complete(self, messages):
            self.context = json.loads(messages[-1]["content"])
            return Generation(text='{"claims": [], "missing_evidence": []}', model="fixture")
    engine = Engine()
    source = PolicyPassage(id="fictional", title="Fictional EHG", text="The fictional EHG requires a checklist.",
                           source_url="demo://ehg", verified_on=date(2000, 1, 1), snapshot_id="fixture")
    question = "How much EHG can we receive, and how much are 4-room flats in Bedok?"
    PolicySummariser(engine).generate(GraphState(message=question, route="mixed", passages=[source]))
    assert "EHG" in engine.context["question"] and "Bedok" not in engine.context["question"]
    assert "Bedok" not in engine.context["latest_message"]
    assert engine.context["answer_requirements"]["price_handled_separately"] is True


def test_partial_price_period_discloses_actual_data_coverage_without_changing_filters():
    from types import SimpleNamespace
    from kopi_keys.components.synthesiser import Synthesiser
    from kopi_keys.graph import build_graph, run_graph
    from kopi_keys.llm import Generation
    from fakes import FictionalRetriever
    class Tool:
        def info(self):
            return SimpleNamespace(max_month="2026-03")
        def query(self, filters):
            return PriceResult(query_id="fictional", filters=filters, volume=5, mean=Decimal(5),
                               median=Decimal(5), iqr=Decimal(0), minimum=Decimal(5), maximum=Decimal(5))
    class Engine:
        def complete(self, messages):
            return Generation(text="Mean: 5\nMedian: 5\nIQR: 0\nRange: 5 to 5\nVolume: 5 transactions", model="fixture")
    graph = build_graph(retriever=FictionalRetriever(), price_tool=Tool(), synthesiser=Synthesiser(Engine()), cards=[])
    state = run_graph(graph, ChatRequest(message="4-room prices in Bishan in the first half of 2026?"))
    assert state.response.status == "answered"
    assert state.price_result.filters.end_month == "2026-06"
    assert "to Mar 2026" in state.response.message and "only the available sales" in state.response.message


@pytest.mark.parametrize("requested,returned", [
    ("high", None), (None, "high"), ("low", "high"), ("high", "high"),
])
def test_verifier_rejects_wrong_floor_subset_even_when_numbers_are_exact(requested, returned):
    filters = PriceFilters(town="BISHAN", flat_type="4 ROOM", start_month="2026-01",
                           end_month="2026-10", storey_band=returned)
    price = PriceResult(query_id="fixture", filters=filters, volume=5, mean=Decimal(500000),
                        median=Decimal(500000), iqr=Decimal(20000), minimum=Decimal(450000),
                        maximum=Decimal(550000))
    state = GraphState(message="What are the prices?", route="price", town="BISHAN", flat_type="4 ROOM",
                       storey_band=requested, price_result=price, draft=Draft(kind="answer", price_text=
                       "Mean: 500000\nMedian: 500000\nIQR: 20000\nRange: 450000 to 550000\nVolume: 5 transactions"))
    assert bool(verify(state)) == (requested != returned)
