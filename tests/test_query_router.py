import pytest
from pydantic import ValidationError

from kopi_keys.components.query_router import route_query
from kopi_keys.state import GraphState


def test_extracts_profile_values_and_classifies_policy():
    routed = route_query("Am I eligible for a grant? I am 32 and Singaporean.")

    assert routed.intent == "policy"
    assert routed.route == "policy"
    assert routed.status == "continue"
    assert routed.user_age == 32
    assert routed.citizenship == "Singaporean"
    assert routed.missing_fields == []


def test_extracts_price_parameters_with_punctuation():
    routed = route_query("What is the resale price for a 4-room flat in Tampines?")

    assert routed.intent == "price"
    assert routed.town == "TAMPINES"
    assert routed.flat_type == "4 ROOM"


def test_extracts_income_and_abstains_on_unsupported_question():
    routed = route_query("My income is SGD 6,000 and I live in Tampines.")

    assert routed.income == 6000
    assert routed.town == "TAMPINES"
    assert routed.intent == "unanswerable"
    assert routed.route == "abstain"


def test_price_question_without_filters_asks_for_them():
    routed = route_query("What is the resale price?")

    assert routed.intent == "price"
    assert routed.status == "clarify"
    assert routed.route == "clarify"
    assert routed.missing_fields == ["town", "flat_type"]


def test_known_values_fill_gaps_but_message_values_win():
    routed = route_query(
        "What is the resale price for a 4-room flat?",
        known={"town": "BEDOK", "flat_type": "5 ROOM"},
    )

    assert routed.status == "continue"
    assert routed.town == "BEDOK"
    assert routed.flat_type == "4 ROOM"


def test_mixed_question_requires_both_price_parameters():
    routed = route_query(
        "Can I buy a 4-room flat in Tampines and what is the median price? I am 32 Singaporean."
    )

    assert routed.intent == "mixed"
    assert routed.route == "mixed"
    assert routed.missing_fields == []


def test_state_rejects_invalid_profile_values():
    with pytest.raises(ValidationError):
        GraphState(message="question", user_age=121)
    with pytest.raises(ValidationError):
        GraphState(message="question", income=-1)
    with pytest.raises(ValidationError):
        GraphState(message="question", town="   ")


def test_all_dataset_towns_and_aliases_are_extracted():
    from kopi_keys.components.query_router import KNOWN_TOWNS, extract_fields
    assert len(KNOWN_TOWNS) == 26
    for town in KNOWN_TOWNS:
        assert extract_fields(f"4-room flat prices in {town.title()}?")["town"] == town
    assert extract_fields("How much is a 4-room flat in Pasir Ris going for?")["town"] == "PASIR RIS"
    assert extract_fields("4 room in Kallang Whampoa")["town"] == "KALLANG/WHAMPOA"
    assert extract_fields("flat in AMK")["town"] == "ANG MO KIO"
    assert extract_fields("My parents live in Bedok, we want a 4-room in Tampines")["town"] == "TAMPINES"



def test_how_much_for_a_flat_or_town_asks_for_flat_type_instead_of_declining():
    from kopi_keys.components.query_router import route_query
    for question, town in [
        ("how much is a flat in toa payoh", "TOA PAYOH"),
        ("how much are flats in tampines", "TAMPINES"),
        ("how much did units in bishan sell for", "BISHAN"),
    ]:
        routed = route_query(question, {})
        assert routed.route == "clarify", question
        assert routed.town == town and routed.missing_fields == ["flat_type"]
    # Policy questions that mention a flat stay policy questions.
    assert route_query("how much CPF can I use for a resale flat?", {}).route == "policy"
    assert route_query("how much is the option fee?", {}).route == "policy"
    assert route_query("Tell me a joke.", {}).route == "abstain"
