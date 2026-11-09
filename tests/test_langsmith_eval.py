"""The LangSmith experiment target returns the same output shape as a live trace.

One LangSmith UI evaluator serves both the live tracing project and the dev-set dataset, and its
variable mapping (output.response.message) is stored on the evaluator, not per rule.
"""
from types import SimpleNamespace

import langsmith

from kopi_keys import graph as graph_module
from kopi_keys import main as main_module
from kopi_keys.components import policy_retrieval, price_query
from kopi_keys.evaluation import langsmith_eval
from kopi_keys.schemas import ChatResponse


def run_experiment(monkeypatch, response: ChatResponse):
    captured = {}
    monkeypatch.setattr(langsmith, "evaluate", lambda target, **kw: captured.update(target=target, **kw))
    monkeypatch.setattr(graph_module, "build_graph", lambda **kw: object())
    monkeypatch.setattr(graph_module, "run_graph", lambda g, request: SimpleNamespace(response=response))
    monkeypatch.setattr(main_module, "router_fallback", lambda: None)
    monkeypatch.setattr(policy_retrieval, "HybridPolicyRetriever", lambda: object())
    monkeypatch.setattr(price_query, "SqlitePriceTool", lambda: object())
    langsmith_eval.run(client=None, prefix="test", judge_model=None, limit=None, concurrency=1)
    return captured


def test_experiment_output_matches_a_live_trace(monkeypatch):
    response = ChatResponse(status="abstained", route="abstain", message="I can help with HDB resale policy "
                            "and resale price questions only.", trace=["query_router:abstain", "abstention:unsupported"])
    captured = run_experiment(monkeypatch, response)
    outputs = captured["target"]({"message": "Will this flat be worth more in five years if we buy now?", "profile": {}})
    assert outputs["response"]["message"] == response.message
    assert outputs["response"]["status"] == "abstained"

    # The code metrics still read the response from the new shape.
    code_metrics = captured["evaluators"][0]
    example = SimpleNamespace(metadata={"id": "OOS-01"})
    scores = {r["key"]: r["score"] for r in code_metrics(outputs, example)["results"]}
    assert scores["route_correct"] == 1 and scores["unsafe_answering"] == 0
