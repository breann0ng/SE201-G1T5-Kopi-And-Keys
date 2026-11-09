"""Short price follow-ups ("what about 2015", "how about 5-room?") reuse the previous question."""

import csv
from datetime import date

import pytest

from fakes import FictionalRetriever
from kopi_keys.components.price_query import SqlitePriceTool
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.ingest import resale_db as importer
from kopi_keys.schemas import ChatRequest, HistoryTurn
from kopi_keys.state import initial_state

FIRST = "What were 4-room flats in Tampines selling for in 2028?"
ROW = {
    "month": "2025-01", "town": "TAMPINES", "flat_type": "4 ROOM", "block": "101",
    "street_name": "TAMPINES ST 11", "storey_range": "04 TO 06", "floor_area_sqm": "92",
    "flat_model": "Model A", "lease_commence_date": "1985", "remaining_lease": "59 years 03 months",
    "resale_price": "500000",
}


@pytest.fixture
def graph(tmp_path):
    rows = [ROW, {**ROW, "flat_type": "5 ROOM", "resale_price": "650000"},
            {**ROW, "town": "BEDOK", "resale_price": "450000"}, {**ROW, "month": "2025-07"}]
    csv_path = tmp_path / "resale.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=importer.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    importer.build(csv_path, tmp_path / "db.sqlite", today=date(2026, 10, 15), downloaded_on=date(2026, 10, 15))
    return build_graph(retriever=FictionalRetriever(), price_tool=SqlitePriceTool(tmp_path / "db.sqlite"),
                       synthesiser=Synthesiser(engine=None), cards=[])


# The assistant's reply does not decide the carry-over; this is what FIRST gets.
FIRST_REPLY = ("Our records cover sales from Jan 2017 to Jul 2025, so there are no sales for Jan 2028 onwards. "
               "Past sales can't tell you what future prices will be.")


def follow_up(message, first=FIRST):
    return ChatRequest(message=message, history=[HistoryTurn(role="user", content=first),
                                                 HistoryTurn(role="assistant", content=FIRST_REPLY)])


def test_period_follow_up_keeps_town_and_flat_and_uses_the_new_period(graph):
    state = run_graph(graph, follow_up("what about sales in 2015"))
    assert (state.route, state.town, state.flat_type) == ("price", "TAMPINES", "4 ROOM")
    assert (state.start_month, state.end_month) == ("2015-01", "2015-12")
    assert state.abstain_reason == "price_out_of_range"
    assert state.response.message == ("Our records cover sales from Jan 2017 to Jul 2025, "
                                      "so there are no sales before Jan 2017.")


def test_flat_type_follow_up_overrides_the_remembered_flat_type(graph):
    state = run_graph(graph, follow_up("how about 5-room?"))
    assert (state.route, state.town, state.flat_type) == ("price", "TAMPINES", "5 ROOM")


def test_town_follow_up_overrides_the_remembered_town(graph):
    state = run_graph(graph, follow_up("and in Bedok?"))
    assert (state.route, state.town, state.flat_type) == ("price", "BEDOK", "4 ROOM")


def test_a_bare_period_is_a_follow_up():
    assert initial_state(follow_up("2019?"))["followup_question"] == FIRST


@pytest.mark.parametrize("message", ["what about next year", "what about next year?", "is mine worth more?"])
def test_forecasts_and_valuations_still_abstain(graph, message):
    assert initial_state(follow_up(message)).get("followup_question") is None
    state = run_graph(graph, follow_up(message))
    assert state.route == "abstain" and state.response.status == "abstained"


def test_unrelated_new_question_does_not_inherit_the_price_question(graph):
    assert initial_state(follow_up("What is the EHG?")).get("followup_question") is None
    assert run_graph(graph, follow_up("What is the EHG?")).route == "policy"


def test_no_carry_over_after_a_policy_question():
    request = follow_up("what about 2015", first="How long is an HFE letter valid for?")
    assert initial_state(request).get("followup_question") is None


FLOOR_AND_LEASE = "how about 16th floor and what are the remaining lease restrictions?"


def floor_history(message):
    return ChatRequest(message=message, history=[
        HistoryTurn(role="user", content="What are resale prices for 4-room flats in Tampines?"),
        HistoryTurn(role="assistant", content="Historical transaction summary."),
        HistoryTurn(role="user", content=FLOOR_AND_LEASE),
        HistoryTurn(role="assistant", content="Which floor band would you like to compare?"),
    ])


@pytest.mark.parametrize("message", [FLOOR_AND_LEASE, "what about floor 16?", "16th floor"])
def test_exact_floor_followup_clarifies_tool_limit_without_model_calls(graph, message):
    state = run_graph(graph, follow_up(message))
    assert state.response.status == "clarifying"
    assert state.missing_fields == ["floor_scope"] and state.model_calls == 0
    assert state.price_result is None and state.storey_band is None
    assert "cannot filter transactions to one exact floor" in state.response.message
    assert "high floors (13+)" in state.response.message
    if "lease" in message:
        assert "CPF usage" in state.response.message and "grant eligibility" in state.response.message


def test_year_after_floor_lease_clarification_explains_data_coverage(graph):
    state = run_graph(graph, floor_history("how about the data in 2027"))
    assert state.followup_question == "What are resale prices for 4-room flats in Tampines?"
    assert (state.town, state.flat_type) == ("TAMPINES", "4 ROOM")
    assert state.abstain_reason == "price_out_of_range" and state.model_calls == 0
    assert "Jan 2017 to Jul 2025" in state.response.message
    assert "Jan 2027" in state.response.message
    assert "Past sales can't tell you what future prices will be" in state.response.message


def test_answering_floor_clarification_uses_only_the_requested_supported_band(graph):
    state = run_graph(graph, floor_history("high floor"))
    assert state.route == "price" and state.storey_band == "high"
    assert state.price_result.filters.storey_band == "high"
    assert state.response.status == "abstained"  # fixture has no high-floor transactions
    assert "No matching" in state.response.message


def test_an_unrelated_policy_question_still_resets_price_followup_context():
    request = floor_history("how about the data in 2027")
    request.history.extend([
        HistoryTurn(role="user", content="What is the EHG?"),
        HistoryTurn(role="assistant", content="Grant overview."),
    ])
    assert initial_state(request).get("followup_question") is None


@pytest.mark.parametrize("message", [
    "How about the 16th floor; can you predict prices next year?",
    "How about recommending a good property agent in Tampines?",
    "How about the 16th floor; should I buy now or wait?",
])
def test_price_context_does_not_bypass_scope_guards(graph, message):
    request = floor_history(message)
    assert initial_state(request).get("followup_question") is None
    state = run_graph(graph, request)
    assert state.response.status == "abstained" and state.route == "abstain"


@pytest.mark.parametrize("reply,band", [
    ("13+", "high"), ("High floors (13+)", "high"), ("high", "high"),
    ("7–12", "mid"), ("Mid floors (7–12)", "mid"),
    ("1-6", "low"), ("Low floors (1–6)", "low"),
])
def test_floor_clarification_accepts_the_displayed_band_labels(reply, band):
    from kopi_keys.components.query_router import route_query
    request = floor_history(reply)
    request.history[-1] = HistoryTurn(role="assistant", content=(
        "I can compare low floors (1–6), mid floors (7–12), or high floors (13+), "
        "but cannot filter transactions to one exact floor. Which floor band would you like to compare?"))
    state = initial_state(request)
    routed = route_query(request.message, state, context_question=state.get("followup_question"))
    assert routed.route == "price" and routed.storey_band == band
    assert (routed.town, routed.flat_type) == ("TAMPINES", "4 ROOM")


def test_full_floor_band_lease_and_year_conversation(graph):
    # Use the actual emitted clarification rather than a hand-written approximation.
    history = [HistoryTurn(role="user", content="What are resale prices for 4-room flats in Tampines?"),
               HistoryTurn(role="assistant", content="Historical transaction summary.")]
    states = []
    for message in (FLOOR_AND_LEASE, "13+", "lease rules", "how about data in 2027?"):
        state = run_graph(graph, ChatRequest(message=message, history=history))
        states.append(state)
        history += [HistoryTurn(role="user", content=message),
                    HistoryTurn(role="assistant", content=state.response.message)]
    assert states[0].response.asking_for == "storey_band"
    assert states[1].route == "price" and states[1].price_result.filters.storey_band == "high"
    assert states[2].response.status == "clarifying" and states[2].response.asking_for == "lease_topic"
    assert "CPF usage" in states[2].response.message and states[2].model_calls == 0
    assert states[3].abstain_reason == "price_out_of_range"
    assert states[3].storey_band == "high" and states[3].model_calls == 0
    assert "Jan 2017 to Jul 2025" in states[3].response.message


def test_floor_number_is_not_reinterpreted_as_a_band_outside_floor_clarification():
    request = ChatRequest(message="13+", history=[
        HistoryTurn(role="user", content="Am I eligible for EHG?"),
        HistoryTurn(role="assistant", content="Please provide: age."),
    ])
    state = initial_state(request)
    assert state.get("storey_band") is None and state.get("followup_question") is None


@pytest.mark.parametrize("choice,term", [("CPF usage", "CPF"), ("HDB loans", "loan"), ("Grant eligibility", "grant")])
def test_lease_topic_reply_becomes_a_scoped_policy_question(choice, term):
    from kopi_keys.components.query_router import route_query
    from kopi_keys.components.synthesiser import Synthesiser
    from kopi_keys.state import GraphState
    routed = route_query("lease rules")
    assert routed.route == "clarify"
    prompt = Synthesiser(None).synthesise(GraphState(message="lease rules", **routed.model_dump(exclude={"needs_confirmation"}))).draft.message
    request = ChatRequest(message=choice, history=[
        HistoryTurn(role="user", content="lease rules"), HistoryTurn(role="assistant", content=prompt),
    ])
    state = initial_state(request)
    assert "lease" in state["followup_question"].lower() and term.lower() in state["followup_question"].lower()
    assert route_query(choice, state, context_question=state["followup_question"]).route == "policy"


def test_period_reply_can_return_to_prices_after_a_scoped_lease_topic(graph):
    history = floor_history("lease rules").history
    scope = run_graph(graph, ChatRequest(message="lease rules", history=history))
    history += [HistoryTurn(role="user", content="lease rules"),
                HistoryTurn(role="assistant", content=scope.response.message),
                HistoryTurn(role="user", content="CPF usage"),
                HistoryTurn(role="assistant", content="No evidence in this fictional fixture.")]
    state = run_graph(graph, ChatRequest(message="how about data in 2027?", history=history))
    assert state.route == "price" and state.abstain_reason == "price_out_of_range"
    assert (state.town, state.flat_type) == ("TAMPINES", "4 ROOM")


def test_new_price_question_does_not_resurrect_an_older_floor_filter():
    from kopi_keys.components.query_router import route_query
    request = ChatRequest(message="how about data in 2027?", history=[
        HistoryTurn(role="user", content="What are high-floor 4-room prices in Tampines?"),
        HistoryTurn(role="assistant", content="High-floor summary."),
        HistoryTurn(role="user", content="What are 3-room prices in Bedok?"),
        HistoryTurn(role="assistant", content="All floors summary."),
    ])
    state = initial_state(request)
    routed = route_query(request.message, state, context_question=state["followup_question"])
    assert (routed.town, routed.flat_type, routed.storey_band) == ("BEDOK", "3 ROOM", None)


@pytest.mark.parametrize("message", [
    "what happens if i want to buy 16th floor?",
    "I would like a flat on the 16th floor instead",
    "What if I choose floor 16?",
])
def test_floor_followups_do_not_require_a_fixed_opener(graph, message):
    request = follow_up(message, first=(
        "I own a 4 room flat in Toa Payoh and want to buy a 3-room flat in Tampines. What do they cost?"))
    state = run_graph(graph, request)
    assert state.response.status == "clarifying" and state.response.asking_for == "storey_band"
    assert (state.town, state.flat_type) == ("TAMPINES", "3 ROOM")
    assert state.model_calls == 0


@pytest.mark.parametrize("reply,term", [
    ("resale elgibility", "eligibility"), ("Resale eligibility", "eligibility"),
    ("Housing grants", "grants"), ("HDB loans", "loan"), ("CPF and lease rules", "lease"),
])
def test_general_topic_clarification_reply_is_scoped_without_llm_classification(reply, term):
    from kopi_keys.components.query_router import TOPIC_SCOPE_MESSAGE, route_query
    state = initial_state(ChatRequest(message=reply, history=[
        HistoryTurn(role="user", content="I want to know about HDB"),
        HistoryTurn(role="assistant", content=TOPIC_SCOPE_MESSAGE),
    ]))
    assert term in state["followup_question"].lower()
    routed = route_query(reply, state, context_question=state["followup_question"])
    assert routed.route == "policy" and not routed.needs_confirmation


def test_topic_alias_is_not_globally_rewritten():
    assert initial_state(ChatRequest(message="resale elgibility")).get("followup_question") is None


def test_changed_period_survives_town_and_price_detail_followups():
    from kopi_keys.components.query_router import EXTRACTED_FIELDS, route_query
    from kopi_keys.state import GraphState
    history = []
    for message, expected in [
        ("3-room prices in Tampines in 2025", ("TAMPINES", "3 ROOM", "2025-01", "2025-12")),
        ("How about 2024?", ("TAMPINES", "3 ROOM", "2024-01", "2024-12")),
        ("And in Bedok?", ("BEDOK", "3 ROOM", "2024-01", "2024-12")),
        ("give me more details about prices", ("BEDOK", "3 ROOM", "2024-01", "2024-12")),
    ]:
        state = GraphState(**initial_state(ChatRequest(message=message, history=history)))
        known = {field: getattr(state, field) for field in (*EXTRACTED_FIELDS, "start_month", "end_month")}
        out = route_query(message, known, context_question=state.followup_question)
        assert (out.town, out.flat_type, out.start_month, out.end_month) == expected
        history += [HistoryTurn(role="user", content=message), HistoryTurn(role="assistant", content="Price summary.")]


@pytest.mark.parametrize("message", ["Show all-floor 4-room prices in Yishun.", "Show all floors for 4 room prices in Yishun"])
def test_all_floor_request_is_not_misread_as_floor_four(message):
    from kopi_keys.components.query_router import route_query
    out = route_query(message, {"storey_band": "high"})
    assert out.route == "price" and out.missing_fields == []
    assert (out.town, out.flat_type, out.storey_band) == ("YISHUN", "4 ROOM", None)


@pytest.mark.parametrize("reply", ["all", "All floors", "give me all"])
def test_floor_clarification_can_be_cleared_instead_of_choosing_a_band(graph, reply):
    from kopi_keys.components.query_router import FLOOR_SCOPE_PREFIX
    request = floor_history(reply)
    request.history[-1] = HistoryTurn(role="assistant", content=FLOOR_SCOPE_PREFIX + " (1–6), mid floors (7–12), or high floors (13+).")
    state = initial_state(request)
    from kopi_keys.components.query_router import route_query
    out = route_query(reply, state, context_question=state.get("followup_question"))
    assert out.route == "price" and out.storey_band is None


def test_transaction_period_request_uses_known_property_instead_of_topic_menu(graph):
    request = ChatRequest(message="give me 2027 transactions", history=[
        HistoryTurn(role="user", content="3-room prices in Tampines"),
        HistoryTurn(role="assistant", content="Price summary."),
        HistoryTurn(role="user", content="What is the EHG?"),
        HistoryTurn(role="assistant", content="Policy overview."),
    ])
    state = run_graph(graph, request)
    assert state.route == "price" and state.abstain_reason == "price_out_of_range"
    assert "Jan 2027" in state.response.message and state.model_calls == 0


def test_personal_confirmation_reply_has_a_specific_safe_response_without_model(graph):
    request = ChatRequest(message="Does that mean I definitely qualify for both?", history=[
        HistoryTurn(role="user", content="Can EHG and PHG be combined?"),
        HistoryTurn(role="assistant", content="Other conditions apply."),
    ])
    state = run_graph(graph, request)
    assert state.abstain_reason == "eligibility_confirmation" and state.model_calls == 0
    assert "cannot confirm that you qualify" in state.response.message
    assert "policy and resale price questions only" not in state.response.message
