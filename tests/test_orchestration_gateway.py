import pytest
from pydantic import ValidationError

from kopi_keys.orchestration.gateway import parse_gateway
from kopi_keys.schemas import GraphState


def test_gateway_extracts_profile_values_and_classifies_policy():
    state = parse_gateway("Am I eligible for a grant? I am 32 and Singaporean.")

    assert state.intent == "policy"
    assert state.user_age == 32
    assert state.citizenship == "Singaporean"


def test_gateway_extracts_price_parameters_with_punctuation():
    state = parse_gateway("What is the resale price for a 4-room flat in Tampines?")

    assert state.intent == "price"
    assert state.town == "TAMPINES"
    assert state.flat_type == "4 ROOM"


def test_graph_state_rejects_invalid_profile_values():
    with pytest.raises(ValidationError):
        GraphState(message="question", user_age=121)

    with pytest.raises(ValidationError):
        GraphState(message="question", income=-1)


def test_parse_gateway_extracts_income_without_running_the_graph():
    state = parse_gateway("My income is SGD 6,000 and I live in Tampines.")

    assert state.income == 6000
    assert state.town == "TAMPINES"
    assert state.intent == "unanswerable"
