"""LangSmith experiment target and evaluators (no Ollama, LangSmith or judge model needed).

The target returns the same output shape as a live trace ({"response": ...}): one LangSmith UI
evaluator serves both the live tracing project and the dev-set dataset, and its variable mapping
(output.response.message) is stored on the evaluator, not per rule.

The evaluators must survive every output the SDK can hand them. When the target crashes, the SDK
passes outputs={} (run.outputs or {}): that is recorded as an error, never judged.
"""
import sys
from types import ModuleType, SimpleNamespace

import langsmith
import pytest

from kopi_keys import graph as graph_module
from kopi_keys import main as main_module
from kopi_keys.components import policy_retrieval, price_query
from kopi_keys.evaluation import langsmith_eval
from kopi_keys.schemas import ChatResponse

ABSTAINED = ChatResponse(status="abstained", route="abstain", message="I can help with HDB resale policy "
                         "and resale price questions only.", trace=["query_router:abstain", "abstention:unsupported"])
ANSWERED = {"status": "answered", "route": "policy", "message": "You must pay flat sellers an Option Fee "
            "when they grant you an OTP [CHUNK_X]", "citations": [{"id": "CHUNK_X", "text": "..."}]}
CLARIFYING = {"status": "clarifying", "route": "clarify", "message": "Please provide: flat type."}


class FakeJudge:
    """Stands in for openevals.create_llm_as_judge and records what it was asked to judge."""

    def __init__(self, fail: Exception | None = None):
        self.calls, self.fail = [], fail

    def __call__(self, *, inputs, outputs):
        if self.fail:
            raise self.fail
        self.calls.append((inputs, outputs))
        return {"key": "answer_relevance", "score": True, "comment": "fake"}


def run_experiment(monkeypatch, response: ChatResponse = ABSTAINED, judge: FakeJudge | None = None):
    captured = {}
    monkeypatch.setattr(langsmith, "evaluate", lambda target, **kw: captured.update(target=target, **kw))
    monkeypatch.setattr(graph_module, "build_graph", lambda **kw: object())
    monkeypatch.setattr(graph_module, "run_graph", lambda g, request: SimpleNamespace(response=response))
    monkeypatch.setattr(main_module, "router_fallback", lambda: None)
    monkeypatch.setattr(policy_retrieval, "HybridPolicyRetriever", lambda: object())
    monkeypatch.setattr(price_query, "SqlitePriceTool", lambda: object())
    if judge is not None:  # judging enabled, without installing openevals or calling a model
        llm = ModuleType("openevals.llm")
        llm.create_llm_as_judge = lambda **kw: judge
        monkeypatch.setitem(sys.modules, "openevals", ModuleType("openevals"))
        monkeypatch.setitem(sys.modules, "openevals.llm", llm)
    langsmith_eval.run(client=None, prefix="test", judge_model="fake:judge" if judge else None,
                       limit=None, concurrency=1)
    evaluators = {e.__name__: e for e in captured["evaluators"]}
    return captured["target"], evaluators


def example(question_id):
    return SimpleNamespace(metadata={"id": question_id})


def run_with(error=None):
    return SimpleNamespace(error=error)


def scores(result):
    return {r["key"]: r["score"] for r in result["results"]}


def test_experiment_output_matches_a_live_trace(monkeypatch):
    target, evaluators = run_experiment(monkeypatch)
    outputs = target({"message": "Will this flat be worth more in five years if we buy now?", "profile": {}})
    assert outputs["response"]["message"] == ABSTAINED.message
    assert outputs["response"]["status"] == "abstained"
    # The code metrics read the response from the new shape.
    result = scores(evaluators["code_metrics"](run_with(), example("OOS-01"), outputs))
    assert result["route_correct"] == 1 and result["unsafe_answering"] == 0


@pytest.mark.parametrize("outputs", [{}, None, {"response": None}, {"response": "not a dict"}])
def test_a_crashed_target_is_an_error_and_never_judged(monkeypatch, outputs):
    judge = FakeJudge()
    _, evaluators = run_experiment(monkeypatch, judge=judge)
    run = run_with("TimeoutError: Ollama did not answer")
    result = evaluators["code_metrics"](run, example("POL-06"), outputs)
    assert result["key"] == "error" and result["score"] == 1
    assert "no response" in result["comment"] and "TimeoutError" in result["comment"]
    assert evaluators["answer_relevance"]({"message": "q"}, outputs) == {"results": []}
    assert judge.calls == []


def test_only_answered_responses_are_judged(monkeypatch):
    judge = FakeJudge()
    _, evaluators = run_experiment(monkeypatch, judge=judge)
    relevance = evaluators["answer_relevance"]
    question = {"message": "What do I have to pay the seller when they give me an Option to Purchase?"}
    for skipped in (ABSTAINED.model_dump(mode="json"), CLARIFYING):
        assert relevance(question, {"response": skipped}) == {"results": []}
    assert judge.calls == []
    assert relevance(question, {"response": ANSWERED})["key"] == "answer_relevance"
    assert judge.calls == [(question["message"], ANSWERED["message"])]


def test_an_answer_without_text_is_judged_as_empty(monkeypatch):
    judge = FakeJudge()
    _, evaluators = run_experiment(monkeypatch, judge=judge)
    evaluators["answer_relevance"]({"message": "q"}, {"response": {"status": "answered"}})
    assert judge.calls == [("q", "")]


def test_a_failed_judge_call_is_not_scored_as_irrelevant(monkeypatch):
    judge = FakeJudge(fail=RuntimeError("429 RESOURCE_EXHAUSTED"))
    _, evaluators = run_experiment(monkeypatch, judge=judge)
    result = evaluators["answer_relevance"]({"message": "q"}, {"response": ANSWERED})
    assert result["key"] == "judge_error" and result["score"] == 1
    assert "429" in result["comment"]


def test_malformed_response_and_unknown_question_are_errors(monkeypatch):
    _, evaluators = run_experiment(monkeypatch, judge=FakeJudge())
    code_metrics = evaluators["code_metrics"]
    malformed = code_metrics(run_with(), example("POL-06"), {"response": {"message": "no status"}})
    assert malformed["key"] == "error" and "status" in malformed["comment"]
    unknown = code_metrics(run_with(), example("NOT-A-QUESTION"), {"response": ANSWERED})
    assert unknown["key"] == "error" and "upload" in unknown["comment"]
    no_metadata = code_metrics(run_with(), SimpleNamespace(metadata=None), {"response": ANSWERED})
    assert no_metadata["key"] == "error"
