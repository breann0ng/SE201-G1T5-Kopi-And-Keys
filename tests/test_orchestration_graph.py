from kopi_keys.orchestration.graph import run_stage1


def test_policy_request_continues_to_policy_route():
    state = run_stage1("Am I eligible for a grant? I am 32 and Singaporean.")

    assert state.status == "continue"
    assert state.route == "policy"
    assert state.missing_fields == []


def test_price_question_short_circuits_when_query_fields_are_missing():
    state = run_stage1("What is the resale price?")

    assert state.intent == "price"
    assert state.status == "clarify"
    assert state.route == "clarify"
    assert state.missing_fields == ["town", "flat_type"]
    assert "town" in state.response
    assert "flat_type" in state.response


def test_mixed_question_requires_both_price_parameters():
    state = run_stage1(
        "Can I buy a 4-room flat in Tampines and what is the median price? "
        "I am 32 Singaporean."
    )

    assert state.intent == "mixed"
    assert state.status == "continue"
    assert state.route == "mixed"
    assert state.missing_fields == []


def test_unanswerable_question_abstains_without_tool_route():
    state = run_stage1("Tell me a joke.")

    assert state.intent == "unanswerable"
    assert state.status == "abstain"
    assert state.route == "abstain"
    assert state.response is not None
