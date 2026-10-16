from fastapi.testclient import TestClient

from fakes import FictionalRetriever
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.graph import build_graph
from kopi_keys.main import create_app


def client():
    return TestClient(create_app(build_graph(retriever=FictionalRetriever(), synthesiser=Synthesiser(engine=None), cards=[])))


def test_health_and_policy_answer():
    with client() as c:
        assert c.get("/health").json() == {"status": "ok", "mode": "demo"}
        response = c.post("/chat", json={"message": "What is the demo grant policy?"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        assert body["route"] == "policy"
        assert body["retrieval_rounds"] == 1
        assert body["citations"][0]["id"] == "demo-programme"


def test_invalid_payloads_are_rejected():
    with client() as c:
        assert c.post("/chat", json={"message": "   "}).status_code == 422
        assert c.post("/chat", json={"message": "prices", "price_filters": {
            "town": "TAMPINES", "flat_type": "4 ROOM",
            "start_month": "2025-12", "end_month": "2025-01",
        }}).status_code == 422


def test_unsupported_request_abstains():
    with client() as c:
        body = c.post("/chat", json={"message": "Tell me a joke."}).json()
    assert body["status"] == "abstained"
    assert body["trace"] == ["query_router:abstain", "abstention:unsupported"]


def test_structured_price_filters_reach_price_tool():
    with client() as c:
        body = c.post("/chat", json={"message": "prices", "price_filters": {
            "town": "TAMPINES", "flat_type": "4 ROOM",
            "start_month": "2025-01", "end_month": "2025-12",
        }}).json()
    assert body["status"] == "abstained"
    assert "price_query:unavailable" in body["trace"]
