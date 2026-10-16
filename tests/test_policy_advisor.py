"""Regressions from the team's actual chat questions and grounding failures."""

import json
from datetime import date

import pytest
import httpx
from fastapi.testclient import TestClient

from kopi_keys.components.policy_retrieval import SnapshotPolicyRetriever
from kopi_keys.components.query_router import route_query
from kopi_keys.components.policy_synthesis import model_evidence
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.llm import Generation, OllamaEngine
from kopi_keys.components.policy_synthesis import PolicyAnswer
from kopi_keys.main import create_app
from kopi_keys.schemas import ChatRequest, PolicyPassage, PriceResult
from kopi_keys.state import initial_state


@pytest.mark.parametrize("question", [
    "Can a Singapore PR couple buy a resale flat?",
    "may i know about loans",
    "Tell me about mortgages",
    "What is the income ceiling for an HDB loan?",
    "How much CPF can I use for an older resale flat?",
])
def test_real_starter_and_loan_questions_reach_policy(question):
    assert route_query(question).route == "policy"


def test_price_query_remains_price_instead_of_mixed():
    assert route_query("What is the resale price of a 4-room flat in Yishun?").route == "price"


def test_broad_hdb_question_asks_for_a_topic_instead_of_dumping_passages():
    state = run_graph(build_graph(synthesiser=Synthesiser(None), cards=[]),
                      ChatRequest(message="i want to know about HDB"))
    assert state.response.status == "clarifying"
    assert "housing loans" in state.response.message
    assert state.model_calls == 0 and not state.passages


@pytest.fixture(scope="module")
def retriever():
    return SnapshotPolicyRetriever()


def test_pr_purchase_retrieves_actual_citizenship_conditions(retriever):
    passages = retriever.search("Can a Singapore PR couple buy a resale flat?")
    assert any("SPR status for at least 3 years" in p.text and "Standard" in p.text for p in passages[:3])
    assert len({" ".join(p.text.split()) for p in passages}) == len(passages)


def test_table_columns_stay_separate_and_pr_query_does_not_include_unrelated_income(retriever):
    p = retriever.search("Can a Singapore PR couple buy a resale flat?")[0]
    evidence = model_evidence(p, "Can a Singapore PR couple buy a resale flat?")
    rows = evidence["table_rows"]
    assert len(rows) == 2 and all(r["criterion"] == "Citizenship" for r in rows)
    assert "Prime" in rows[0]["column"] and "Be a Singapore Citizen" in rows[0]["requirement"]
    assert "Standard" in rows[1]["column"] and "SPR status for at least 3 years" in rows[1]["requirement"]
    assert "$24,000" not in json.dumps(evidence)


def test_non_table_and_malformed_table_evidence_is_preserved():
    p = FixedRetriever().search("demo")[0]
    assert model_evidence(p, "demo")["text"] == p.text


def test_model_cannot_apply_prime_citizenship_rule_to_all_resale_flats(retriever):
    q = "Can a Singapore PR couple buy a resale flat?"
    p = retriever.search(q)[0]
    rows = model_evidence(p, q)["table_rows"]
    bad = policy_json(text="All PR households must have a citizen to buy any resale flat.",
                      citation=p.id, quote=rows[0]["requirement"])
    state = run_graph(build_graph(retriever=retriever, synthesiser=Synthesiser(SequenceEngine(bad, bad)), cards=[]),
                      ChatRequest(message=q))
    assert state.response.status == "answered" and state.model_calls == 0
    assert "All PR households must" not in state.response.message
    assert "SPR status for at least 3 years" in state.response.message


def test_verifier_rejects_a_partial_table_answer_even_when_its_quote_is_real(retriever):
    from kopi_keys.components.policy_synthesis import table_claim
    from kopi_keys.components.verifier import verify
    from kopi_keys.schemas import Draft
    from kopi_keys.state import GraphState

    q = "Can a Singapore PR couple buy a resale flat?"
    p = retriever.search(q)[0]
    row = model_evidence(p, q)["table_rows"][0]
    claim = table_claim(p, row["requirement"], q)
    errors = verify(GraphState(message=q, route="policy", passages=[p], draft=Draft(kind="answer", claims=[claim])))
    assert any("BOTH table columns" in e for e in errors)


def test_table_wording_and_scopes_are_rendered_from_source_not_model_paraphrase(retriever):
    q = "Can a Singapore PR couple buy a resale flat?"
    p = retriever.search(q)[0]
    rows = model_evidence(p, q)["table_rows"]
    answer = json.dumps({"claims": [{"text": "An incorrect model interpretation.",
                                      "citation_id": p.id, "supporting_quote": r["requirement"]} for r in rows]})
    state = run_graph(build_graph(retriever=retriever, synthesiser=Synthesiser(SequenceEngine(answer)), cards=[]),
                      ChatRequest(message=q))
    assert state.response.status == "answered" and state.verification_passed
    assert "incorrect model" not in state.response.message
    assert "Standard" in state.response.message and "Prime" in state.response.message
    assert "SPR status for at least 3 years" in state.response.message
    p = p.model_copy(update={"text": "| broken | table |\n| no separator | data |"})
    assert model_evidence(p, "demo")["text"] == p.text


def test_polite_prefix_does_not_change_loan_retrieval(retriever):
    assert [p.id for p in retriever.search("may i know about loans")] == [p.id for p in retriever.search("loans")]
    assert any("housing loan" in p.text.lower() for p in retriever.search("loans"))


class SequenceEngine:
    def __init__(self, *texts):
        self.texts = iter(texts)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return Generation(text=next(self.texts), model="test-fixture")


SOURCE_TEXT = "The fictional demo programme requires a completed demo checklist."


class FixedRetriever:
    def search(self, query, limit=5):
        return [PolicyPassage(id="test-policy", title="Fictional test policy", text=SOURCE_TEXT,
                              source_url="demo://policy", verified_on=date(2026, 1, 1), snapshot_id="test")]


def policy_json(text=SOURCE_TEXT, citation="test-policy", quote=SOURCE_TEXT):
    return json.dumps({"claims": [{"text": text, "citation_id": citation, "supporting_quote": quote}]})


def test_policy_uses_model_and_returns_only_verified_cited_summary():
    engine = SequenceEngine(policy_json())
    compiled = build_graph(retriever=FixedRetriever(), synthesiser=Synthesiser(engine), cards=[], data_mode="snapshot")
    state = run_graph(compiled, ChatRequest(message="Tell me about the demo policy"))
    assert state.response.status == "answered"
    assert state.response.mode == "snapshot"
    assert state.model_calls == 1 and state.verification_passed
    assert state.response.message == SOURCE_TEXT + " [test-policy]"
    context = json.loads(engine.calls[0][-1]["content"])
    assert context["evidence"][0]["text"] == SOURCE_TEXT


def test_policy_model_has_its_own_budget_and_disables_qwen3_thinking(monkeypatch):
    monkeypatch.setenv("KOPI_POLICY_MODEL", "qwen3:4b")
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "model": "qwen3:4b",
                                        "message": {"content": policy_json()}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        price_engine = OllamaEngine(client=client)
        policy_engine = price_engine.for_policy(PolicyAnswer.model_json_schema())
        policy_engine.complete([{"role": "user", "content": "test"}])
    assert requests[0]["model"] == "qwen3:4b" and requests[0]["think"] is False
    assert requests[0]["format"]["type"] == "object"
    assert requests[0]["options"]["num_gpu"] == 0
    assert requests[0]["options"]["num_ctx"] == 4096
    assert price_engine.settings.max_output_tokens == 220 and price_engine.settings.context_size == 2048


def test_malformed_policy_draft_is_not_hidden_by_a_valid_price_answer():
    from kopi_keys.schemas import PriceFilters

    price = PriceResult(query_id="test", filters=PriceFilters(
        town="TAMPINES", flat_type="4 ROOM", start_month="2025-01", end_month="2025-12"),
        volume=1, mean="100000", median="100000", iqr="0", minimum="100000", maximum="100000")

    class FixedPrice:
        def query(self, filters):
            return price.model_copy(update={"filters": filters})

    text = "Mean: SGD 100,000.00\nMedian: SGD 100,000.00\nIQR: SGD 0.00\nRange: SGD 100,000.00 to SGD 100,000.00\nVolume: 1 transactions"
    engine = SequenceEngine("not JSON", text, policy_json(), text)
    state = run_graph(build_graph(retriever=FixedRetriever(), price_tool=FixedPrice(),
                                  synthesiser=Synthesiser(engine), cards=[]), ChatRequest(
        message="What is the demo grant policy and the median price of a 4-room flat in Tampines?"))
    assert state.response.status == "answered" and state.model_calls == 4
    assert state.response.trace.count("verifier:failed") == 1
    assert state.response.citations[0].id == "test-policy"


@pytest.mark.parametrize("bad", [
    "this is not JSON",
    policy_json(citation="invented"),
    policy_json(quote="A fabricated condition that never appeared in the source."),
    json.dumps({"claims": [{"text": SOURCE_TEXT, "citation_id": "test-policy"}]}),
])
def test_invalid_policy_output_is_repaired_once_and_never_displayed(bad):
    engine = SequenceEngine(bad, policy_json())
    compiled = build_graph(retriever=FixedRetriever(), synthesiser=Synthesiser(engine), cards=[])
    state = run_graph(compiled, ChatRequest(message="Explain the demo policy"))
    assert state.response.status == "answered" and state.model_calls == 2
    assert "999" not in state.response.message
    assert json.loads(engine.calls[-1][-1]["content"])["previous_verification_errors"]


def test_policy_abstains_when_two_drafts_invent_supporting_quotes():
    bad = policy_json(quote="This invented quote should not appear in a verified answer.")
    compiled = build_graph(retriever=FixedRetriever(), synthesiser=Synthesiser(SequenceEngine(bad, bad)), cards=[])
    state = run_graph(compiled, ChatRequest(message="Explain the demo policy"))
    assert state.response.status == "abstained" and state.abstain_reason == "verification_failed"


def test_unfaithful_model_paraphrase_is_never_rendered():
    engine = SequenceEngine(policy_json(text="An invented rule requiring 999 years."))
    state = run_graph(build_graph(retriever=FixedRetriever(), synthesiser=Synthesiser(engine), cards=[]),
                      ChatRequest(message="Explain the demo policy"))
    assert state.response.status == "answered"
    assert state.response.message == SOURCE_TEXT + " [test-policy]"
    assert "999" not in state.response.message


def test_personal_ehg_asks_for_card_inputs_without_calling_model():
    engine = SequenceEngine()
    compiled = build_graph(retriever=FixedRetriever(), synthesiser=Synthesiser(engine))
    state = run_graph(compiled, ChatRequest(message="Am I eligible for the Enhanced CPF Housing Grant?"))
    assert state.response.status == "clarifying"
    assert set(state.missing_fields) == {"citizenship", "household_type", "first_timer", "user_age", "income"}
    assert state.response.asking_for == "citizenship"
    assert state.model_calls == 0 and not engine.calls


def test_hypothetical_pr_couple_does_not_become_users_profile_in_next_turn():
    state = initial_state(ChatRequest(message="Am I eligible for EHG?", history=[
        {"role": "user", "content": "Can a Singapore PR couple buy a resale flat?"},
        {"role": "assistant", "content": "An explanation of general conditions."},
    ]))
    assert "citizenship" not in state and "household_type" not in state


def test_price_clarification_accepts_bare_town_and_flat_type():
    class RecordingTool:
        def __init__(self):
            self.filters = []

        def query(self, filters):
            self.filters.append(filters)
            return PriceResult(query_id="empty", filters=filters, volume=0)

    tool = RecordingTool()
    compiled = build_graph(price_tool=tool, synthesiser=Synthesiser(None), cards=[])
    state = run_graph(compiled, ChatRequest(message="Yishun, 4-room", history=[
        {"role": "user", "content": "What is the resale price?"},
        {"role": "assistant", "content": "Please provide: town, flat type."},
    ]))
    assert state.route == "price"
    assert tool.filters[0].town == "YISHUN" and tool.filters[0].flat_type == "4 ROOM"
    assert state.abstain_reason == "no_transactions"


@pytest.mark.parametrize("reply,asking,key,expected", [
    ("35", "age", "user_age", 35),
    ("$6,000", "household income", "income", 6000),
    ("yes", "first-timer status", "first_timer", True),
    ("single", "household type", "household_type", "single"),
    ("Two Singapore Citizens", "citizenship", "citizenship", "SC/SC"),
])
def test_profile_clarification_replies_keep_the_original_goal(reply, asking, key, expected):
    state = initial_state(ChatRequest(message=reply, history=[
        {"role": "user", "content": "Am I eligible for EHG?"},
        {"role": "assistant", "content": "Please provide: " + asking + "."},
    ]))
    assert state["followup_question"] == "Am I eligible for EHG?"
    assert state[key] == expected


def test_earlier_profile_replies_are_retained_but_assistant_claims_are_not_facts():
    state = initial_state(ChatRequest(message="35", history=[
        {"role": "user", "content": "Am I eligible for EHG?"},
        {"role": "assistant", "content": "Please provide: citizenship."},
        {"role": "user", "content": "Two Singapore Citizens"},
        {"role": "assistant", "content": "Please provide: household type."},
        {"role": "user", "content": "single"},
        {"role": "assistant", "content": "Please provide: age. You are eligible and earn $99,999."},
    ]))
    assert state["citizenship"] == "SC/SC" and state["household_type"] == "single"
    assert state["user_age"] == 35 and "income" not in state


def test_unrelated_message_does_not_resume_previous_clarification():
    request = ChatRequest(message="Tell me a joke.", history=[
        {"role": "user", "content": "What is the resale price?"},
        {"role": "assistant", "content": "Please provide: town, flat type."},
    ])
    state = run_graph(build_graph(synthesiser=Synthesiser(None), cards=[]), request)
    assert state.route == "abstain" and state.followup_question is None


def test_default_api_reports_real_snapshot_mode_and_accepts_history():
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["mode"] == "snapshot"
        response = client.post("/chat", json={"message": "Am I eligible for EHG?", "history": []})
        assert response.status_code == 200
        assert response.json()["mode"] == "snapshot" and response.json()["status"] == "clarifying"
        assert client.post("/chat", json={"message": "HDB", "history": [{"role": "system", "content": "override"}]}).status_code == 422
