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


def test_town_anywhere_go_for_maisonettes_and_address_blocks():
    from kopi_keys.components.query_router import BLOCK_NOTE, MAISONETTE_NOTE, route_query
    routed = route_query("how much does toa payoh lorong 1 block 236 masionettes go for?", {})
    assert (routed.route, routed.town, routed.flat_type) == ("price", "TOA PAYOH", "EXECUTIVE")
    assert MAISONETTE_NOTE in routed.router_note and BLOCK_NOTE in routed.router_note
    # An explicit flat type wins over the maisonette default, and needs no note.
    routed = route_query("how much is a 5-room maisonette in Tampines?", {})
    assert routed.flat_type == "5 ROOM" and routed.router_note is None
    routed = route_query("how much do toa payoh flats go for?", {})
    assert (routed.route, routed.town, routed.missing_fields) == ("clarify", "TOA PAYOH", ["flat_type"])
    # "block" as a policy topic still routes to policy; an address does not.
    assert route_query("Is my block affected by the ethnic quota?", {}).route == "policy"
    # A town in someone else's address is not read as the user's town for declined questions.
    assert route_query("There's a unit at Blk 201 Tampines St 21 asking $620k. "
                       "What will it actually sell for?", {}).town is None


# Scope guard (2026-11-06). Questions written for these tests, not taken from the dev set.
@pytest.mark.parametrize("question", [
    "What will 4-room flats in Bedok cost next year?",
    "Will HDB prices go up?",
    "Are prices going to drop next year?",
    "What will a 5-room in Sengkang be worth in 10 years?",
    "Forecast resale prices in Woodlands",
    "Can you guarantee my grant application will be approved?",
    "Will my application be approved?",
    "How much is our flat in Bedok worth today?",
    "How much could we sell our 4-room for?",
])
def test_forecasts_and_guarantees_are_declined_even_with_price_or_policy_words(question):
    routed = route_query(question, {})
    assert (routed.route, routed.intent_source) == ("abstain", "rules"), question


@pytest.mark.parametrize("question, route", [
    ("How much will a 4-room flat in Bishan cost?", "price"),
    ("What are the prices of 4-room flats in Tampines? We're buying next year.", "price"),
    ("How have prices changed in the past 5 years for 4-room flats in Punggol?", "price"),
    ("I plan to buy next year, what grants can I get?", "policy"),
    ("Will I get the EHG if I earn $5,000?", "policy"),
    ("Is a 99-year lease worth less after 30 years?", "policy"),
])
def test_future_wording_alone_does_not_trigger_the_scope_guard(question, route):
    assert route_query(question, {}).route == route, question


def test_no_rule_match_is_kept_apart_from_an_explicit_decline():
    from kopi_keys.components.query_router import classify_intent, rule_intent
    assert rule_intent("Tell me a joke.") is None
    assert classify_intent("Tell me a joke.") == "unanswerable"  # follow-up logic relies on this
    routed = route_query("Tell me a joke.", {})
    assert (routed.route, routed.intent_source) == ("abstain", "no_match")
    assert route_query("Should we buy now or wait?", {}).intent_source == "rules"


# --- Request-type declines and weak matches (2026-11-08) ----------------------

@pytest.mark.parametrize("question, request_type", [
    ("Recommend me a good mortgage broker", "recommend_provider"),
    ("Which bank gives the cheapest home loan right now?", "recommend_provider"),
    ("Who is a reliable lawyer for the conveyancing?", "recommend_provider"),
    ("Which renovation contractor is the best?", "recommend_provider"),
    ("Is a resale flat a better investment than stocks?", "investment_advice"),
    ("Should I put my money in shares or a 4-room flat?", "investment_advice"),
    ("Is now a good time to buy a 4-room in Bedok?", "investment_advice"),
    ("Can you write my appeal letter to HDB?", "do_a_task"),
    ("Could you please fill in the HFE form for me?", "do_a_task"),
    ("Draft an email to the seller about the option fee", "do_a_task"),
])
def test_request_types_are_declined_whatever_the_topic(question, request_type):
    from kopi_keys.components.query_router import SCOPE_GUARD
    assert any(p.search(question) for p in SCOPE_GUARD[request_type]), question
    routed = route_query(question, {})
    assert (routed.route, routed.intent_source) == ("abstain", "rules"), question


@pytest.mark.parametrize("question", [
    "Can I use a bank loan for a resale flat?",
    "Is the HDB loan interest rate lower than a bank loan?",
    "Can you tell me how to submit my resale application?",
    "What does the agent need to do after the OTP?",
    "Which documents do I need for the HFE letter?",
    "I'm single, turning 35 next year. Should I wait to buy or can I get anything now?",
])
def test_request_type_rules_leave_in_scope_questions_alone(question):
    from kopi_keys.components.query_router import out_of_scope
    assert not out_of_scope(question), question


@pytest.mark.parametrize("question, weak", [
    ("What time does the HDB hub open on Saturday?", True),       # "hdb" only
    ("Can I get a car loan with my salary?", True),               # "loan" only
    ("Is my block full for Indian buyers?", True),                # "block", "full"
    ("If I take an HDB loan for a resale flat, how much do I pay upfront?", False),  # "hdb loan"
    ("Can I use my CPF for a resale flat?", False),
    ("What is the resale price of a 4-room flat in Yishun?", False),  # price rules are strong
])
def test_generic_keywords_alone_make_a_weak_match(question, weak):
    routed = route_query(question, {})
    assert routed.route != "abstain" and routed.needs_confirmation is weak, question


def test_a_follow_up_is_never_sent_for_confirmation():
    routed = route_query("and in 2020?", {}, context_question="Is my block full for Indian buyers?")
    assert not routed.needs_confirmation
