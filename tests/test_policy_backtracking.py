"""Missing-policy searches reuse the one repair; they cannot create unbounded loops."""
import pytest

from fakes import FictionalRetriever
from kopi_keys.components.synthesiser import SynthesisResult
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest, Claim, Draft


class RecordingRetriever(FictionalRetriever):
    def __init__(self):
        self.queries = []

    def search(self, query, limit=5):
        self.queries.append(query)
        return super().search(query, limit)


class NeedsPolicy:
    def __init__(self, *, always_missing=False, invalid_quote=False):
        self.seen = []
        self.always_missing, self.invalid_quote = always_missing, invalid_quote

    def synthesise(self, state):
        self.seen.append(state)
        if self.invalid_quote:
            return SynthesisResult(Draft(kind="answer", claims=[Claim(
                text="Invented wording.", supporting_quote="Invented wording.", citation_ids=[state.passages[0].id])]))
        if len(self.seen) == 1 or self.always_missing:
            return SynthesisResult(Draft(kind="answer"), validation_errors=["Missing policy evidence: related condition"],
                                   model_calls=1)
        p = state.passages[0]
        return SynthesisResult(Draft(kind="answer", claims=[Claim(
            text=p.text, supporting_quote=p.text, citation_ids=[p.id])]), model_calls=1)


def execute(synthesiser, *, max_repairs=1):
    retriever = RecordingRetriever()
    graph = build_graph(retriever=retriever, synthesiser=synthesiser, cards=[], max_repairs=max_repairs)
    return run_graph(graph, ChatRequest(message="Explain the demo grant policy.")), retriever


def test_missing_policy_rewrites_search_and_verifies_new_evidence():
    synth = NeedsPolicy()
    state, retriever = execute(synth)
    assert len(retriever.queries) == 2 and "related condition" in retriever.queries[1]
    assert synth.seen[1].passages[0].id == "demo-condition"
    assert state.response.status == "answered" and state.model_calls == 2
    assert state.repair_count == 1 and state.response.retrieval_rounds == 2


@pytest.mark.parametrize("repairs,searches", [(0, 1), (1, 2)])
def test_missing_policy_still_abstains_at_existing_repair_limit(repairs, searches):
    state, retriever = execute(NeedsPolicy(always_missing=True), max_repairs=repairs)
    assert state.response.status == "abstained"
    assert len(retriever.queries) == searches
    assert state.repair_count == repairs


def test_altered_quote_uses_normal_repair_not_an_extra_search():
    state, retriever = execute(NeedsPolicy(invalid_quote=True))
    assert state.response.status == "abstained"
    assert len(retriever.queries) == 1


def test_mixed_backtracking_reuses_the_executed_price_result():
    from decimal import Decimal
    from types import SimpleNamespace
    from kopi_keys.schemas import PriceResult
    class Tool:
        calls = 0
        def info(self):
            return SimpleNamespace(max_month="2026-10")
        def query(self, filters):
            self.calls += 1
            return PriceResult(query_id="fixture", filters=filters, volume=5, mean=Decimal(5),
                               median=Decimal(5), iqr=Decimal(0), minimum=Decimal(5), maximum=Decimal(5))
    class Mixed(NeedsPolicy):
        def synthesise(self, state):
            result = super().synthesise(state)
            result.draft = result.draft.model_copy(update={"price_text":
                "Mean: 5\nMedian: 5\nIQR: 0\nRange: 5 to 5\nVolume: 5 transactions"})
            return result
    tool = Tool()
    graph = build_graph(retriever=RecordingRetriever(), price_tool=tool, synthesiser=Mixed(), cards=[])
    state = run_graph(graph, ChatRequest(message="Explain the demo grant policy and median 4-room prices in Bishan."))
    assert state.response.status == "answered" and state.response.route == "mixed"
    assert len(state.retrieval_queries) == 2 and tool.calls == 1
