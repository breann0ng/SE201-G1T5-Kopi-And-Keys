from fastapi.testclient import TestClient

from kopi_keys.advisor import DemoAdvisor
from kopi_keys.main import create_app
from kopi_keys.schemas import AdvisorDecision, ChatRequest, Claim, PriceFilters, PriceResult
from kopi_keys.tools.policy import DemoPolicyRetriever
from kopi_keys.tools.price import UnconfiguredPriceTool
from kopi_keys.workflow import WorkflowLimits, build_workflow, run_request


class ScriptedAdvisor:
    def __init__(self, *decisions):
        self.decisions = iter(decisions)
        self.seen = []

    def decide(self, state):
        self.seen.append(state)
        return next(self.decisions)


def workflow(advisor=None, retriever=None, price_tool=None, limits=WorkflowLimits()):
    return build_workflow(
        advisor or DemoAdvisor(),
        retriever or DemoPolicyRetriever(),
        price_tool or UnconfiguredPriceTool(),
        limits,
    )


def test_advisor_retrieves_related_rule_and_keeps_both_sources():
    advisor = ScriptedAdvisor(
        AdvisorDecision(action="retrieve", query="demo programme"),
        AdvisorDecision(action="retrieve", query="demo related condition"),
        AdvisorDecision(action="answer", claims=[
            Claim(text="A completed demo checklist is required.", citation_ids=["demo-condition"]),
        ]),
    )
    result = run_request(workflow(advisor), ChatRequest(message="Explain the related rule."))
    assert result.status == "answered"
    assert result.retrieval_rounds == 2
    assert {p.id for p in advisor.seen[-1]["passages"]} == {"demo-programme", "demo-condition"}
    assert [p.id for p in result.citations] == ["demo-condition"]
    assert result.trace[-1] == "verifier:passed"


def test_missing_citation_is_reported_to_advisor_and_can_be_repaired():
    advisor = ScriptedAdvisor(
        AdvisorDecision(action="retrieve", query="demo programme"),
        AdvisorDecision(action="answer", claims=[Claim(text="Draft without a citation.")]),
        AdvisorDecision(action="answer", claims=[
            Claim(text="The fictional programme has a related condition.", citation_ids=["demo-programme"]),
        ]),
    )
    result = run_request(workflow(advisor), ChatRequest(message="demo"))
    assert result.status == "answered"
    assert advisor.seen[-1]["verification_errors"]
    assert "Draft without a citation" not in result.message


def test_persistent_unknown_citation_is_never_shown_as_an_answer():
    draft = AdvisorDecision(action="answer", claims=[
        Claim(text="Unsupported claim.", citation_ids=["invented-source"]),
    ])
    result = run_request(
        workflow(ScriptedAdvisor(draft, draft)), ChatRequest(message="Question"),
    )
    assert result.status == "abstained"
    assert result.citations == []
    assert "Unsupported claim" not in result.message
    assert result.trace.count("verifier:failed") == 2


def test_superseded_source_is_rejected():
    class OldRetriever:
        def search(self, query, limit=5):
            passage = DemoPolicyRetriever().search("demo programme")[0]
            return [passage.model_copy(update={"superseded": True})]

    draft = AdvisorDecision(action="answer", claims=[
        Claim(text="An old rule.", citation_ids=["demo-programme"]),
    ])
    advisor = ScriptedAdvisor(AdvisorDecision(action="retrieve", query="old rule"), draft, draft)
    result = run_request(workflow(advisor, retriever=OldRetriever()), ChatRequest(message="Question"))
    assert result.status == "abstained"
    assert any("Superseded" in error for error in advisor.seen[-1]["verification_errors"])


def test_repeat_queries_stop_without_consuming_extra_retrieval_calls():
    query = AdvisorDecision(action="retrieve", query="demo programme")
    result = run_request(workflow(ScriptedAdvisor(query, query)), ChatRequest(message="Question"))
    assert result.status == "abstained"
    assert result.retrieval_rounds == 1


def test_different_queries_still_obey_retrieval_budget():
    advisor = ScriptedAdvisor(*[
        AdvisorDecision(action="retrieve", query=f"query {i}") for i in range(4)
    ])
    result = run_request(workflow(advisor), ChatRequest(message="Question"))
    assert result.status == "abstained"
    assert result.retrieval_rounds == 3


def test_missing_price_filters_clarifies_and_missing_database_abstains():
    graph = workflow()
    result = run_request(graph, ChatRequest(message="What are resale prices?"))
    assert result.status == "clarifying"
    filters = PriceFilters(town="TAMPINES", flat_type="4 ROOM", start_month="2025-01", end_month="2025-12")
    result = run_request(graph, ChatRequest(message="What are resale prices?", price_filters=filters))
    assert result.status == "abstained"
    assert result.price_result is None


def test_price_answer_uses_executed_result_and_preserves_query_provenance():
    class FixturePriceTool:
        def query(self, filters):
            return PriceResult(
                query_id="synthetic-query-1", filters=filters, count=3,
                median=200, minimum=100, maximum=300,
            )

    filters = PriceFilters(town="DEMO TOWN", flat_type="4 ROOM", start_month="2025-01", end_month="2025-12")
    result = run_request(workflow(price_tool=FixturePriceTool()), ChatRequest(
        message="What are prices?", price_filters=filters,
    ))
    assert result.status == "answered"
    assert result.price_result.query_id == "synthetic-query-1"
    assert "median SGD 200.00" in result.message


def test_requests_do_not_share_evidence():
    graph = workflow()
    assert run_request(graph, ChatRequest(message="Explain demo")).status == "answered"
    result = run_request(graph, ChatRequest(message="What grants can we get?"))
    assert result.status == "abstained"
    assert result.citations == []


def test_api_demo_and_invalid_payloads():
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok", "mode": "demo"}
        response = client.post("/chat", json={"message": "Explain the demo programme."})
        assert response.status_code == 200
        assert response.json()["retrieval_rounds"] == 2
        assert response.json()["mode"] == "demo"
        assert client.post("/chat", json={"message": "   "}).status_code == 422
        assert client.post("/chat", json={"message": "prices", "price_filters": {
            "town": "TAMPINES", "flat_type": "4 ROOM",
            "start_month": "2025-12", "end_month": "2025-01",
        }}).status_code == 422


def test_api_gateway_short_circuits_unsupported_requests():
    with TestClient(create_app()) as client:
        response = client.post("/chat", json={"message": "Tell me a joke."})

    assert response.status_code == 200
    assert response.json()["status"] == "abstained"
    assert response.json()["trace"] == ["gateway:abstain"]


def test_api_gateway_accepts_structured_price_filters():
    with TestClient(create_app()) as client:
        response = client.post("/chat", json={"message": "prices", "price_filters": {
            "town": "TAMPINES", "flat_type": "4 ROOM",
            "start_month": "2025-01", "end_month": "2025-12",
        }})

    assert response.status_code == 200
    assert response.json()["status"] == "abstained"
    assert response.json()["trace"][-1] == "price:unavailable"
