from fakes import FictionalRetriever
from kopi_keys.components.synthesiser import SynthesisResult, Synthesiser
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest, Claim, Draft, PriceFilters, PriceResult, Suggestion


POLICY_QUESTION = "What is the demo grant policy?"


class ScriptedSynthesiser:
    """Returns pre-written drafts in order and records the state it saw."""

    def __init__(self, *drafts):
        self.drafts = iter(drafts)
        self.seen = []

    def synthesise(self, state):
        self.seen.append(state)
        return SynthesisResult(next(self.drafts))


def graph(synthesiser=None, retriever=None, price_tool=None):
    return build_graph(
        retriever=retriever or FictionalRetriever(),
        price_tool=price_tool,
        synthesiser=synthesiser or Synthesiser(engine=None),
        cards=[],
    )


def answer(*claims, suggestions=()):
    return Draft(kind="answer", claims=list(claims), suggestions=list(suggestions))


def test_policy_question_retrieves_and_answers_with_citation():
    state = run_graph(graph(), ChatRequest(message=POLICY_QUESTION))
    response = state.response
    assert response.status == "answered"
    assert response.route == "policy"
    assert [p.id for p in response.citations] == ["demo-programme"]
    assert "[demo-programme]" in response.message
    assert response.trace == [
        "query_router:policy", "policy_retrieval:1 passages", "topic_cards:0 matched",
        "synthesiser:answer", "verifier:passed", "output",
    ]


def test_policy_question_without_evidence_abstains_before_synthesis():
    synthesiser = ScriptedSynthesiser()
    state = run_graph(graph(synthesiser), ChatRequest(message="What grants can we get?"))
    assert state.response.status == "abstained"
    assert state.abstain_reason == "no_evidence"
    assert synthesiser.seen == []


def test_missing_citation_is_sent_back_once_and_can_be_repaired():
    synthesiser = ScriptedSynthesiser(
        answer(Claim(text="Draft without a citation.")),
        answer(Claim(text="The demo programme has a condition.", citation_ids=["demo-programme"])),
    )
    state = run_graph(graph(synthesiser), ChatRequest(message=POLICY_QUESTION))
    assert state.response.status == "answered"
    assert synthesiser.seen[-1].verification_errors
    assert "Draft without a citation" not in state.response.message


def test_persistent_unknown_citation_is_never_shown():
    draft = answer(Claim(text="Unsupported claim.", citation_ids=["invented-source"]))
    state = run_graph(graph(ScriptedSynthesiser(draft, draft)), ChatRequest(message=POLICY_QUESTION))
    assert state.response.status == "abstained"
    assert state.abstain_reason == "verification_failed"
    assert "Unsupported claim" not in state.response.message
    assert state.response.trace.count("verifier:failed") == 2


def test_superseded_source_is_rejected():
    class OldAndNewRetriever:
        def search(self, query, limit=5):
            current = FictionalRetriever().search("demo programme")[0]
            old = current.model_copy(update={"id": "demo-old", "superseded": True})
            return [current, old]

    draft = answer(Claim(text="An old rule.", citation_ids=["demo-old"]))
    synthesiser = ScriptedSynthesiser(draft, draft)
    state = run_graph(graph(synthesiser, retriever=OldAndNewRetriever()), ChatRequest(message=POLICY_QUESTION))
    assert state.response.status == "abstained"
    assert any("Superseded" in error for error in synthesiser.seen[-1].verification_errors)


def test_suggestion_with_unmatched_topic_card_is_rejected():
    draft = answer(
        Claim(text="Cited.", citation_ids=["demo-programme"]),
        suggestions=[Suggestion(card_id="invented-card", text="Look at this.", citation_ids=["demo-programme"])],
    )
    synthesiser = ScriptedSynthesiser(draft, draft)
    state = run_graph(graph(synthesiser), ChatRequest(message=POLICY_QUESTION))
    assert state.response.status == "abstained"
    assert any("Unknown topic card" in e for e in synthesiser.seen[-1].verification_errors)


def test_price_question_missing_filters_gets_clarifying_question():
    state = run_graph(graph(), ChatRequest(message="What is the resale price?"))
    assert state.response.status == "clarifying"
    assert state.response.message == "Please provide: town, flat type."
    assert state.response.trace[0] == "query_router:clarify"


def test_unsupported_question_abstains_without_tools():
    state = run_graph(graph(), ChatRequest(message="Tell me a joke."))
    assert state.response.status == "abstained"
    assert state.response.trace == ["query_router:abstain", "abstention:unsupported"]


def test_missing_database_abstains_with_reason():
    state = run_graph(graph(), ChatRequest(message="What is the resale price for a 4-room flat in Tampines?"))
    assert state.response.status == "abstained"
    assert "not connected" in state.response.message
    assert state.price_result is None


def test_price_filters_default_to_recent_window_when_dates_are_missing():
    seen = []

    class RecordingPriceTool:
        def query(self, filters):
            seen.append(filters)
            return PriceResult(query_id="q", filters=filters, volume=0)

    run_graph(graph(price_tool=RecordingPriceTool()),
              ChatRequest(message="What is the resale price for a 4-room flat in Tampines?"))
    assert seen[0].town == "TAMPINES"
    assert seen[0].start_month < seen[0].end_month


def test_mixed_question_answers_policy_part_when_price_is_unavailable():
    state = run_graph(graph(), ChatRequest(
        message="What is the demo grant policy and what is the median price of a 4-room flat in Tampines?",
    ))
    assert state.route == "mixed"
    assert state.response.status == "answered"
    assert "Price benchmark unavailable" in state.response.message
    assert [p.id for p in state.response.citations] == ["demo-programme"]


def test_requests_do_not_share_evidence():
    compiled = graph()
    assert run_graph(compiled, ChatRequest(message=POLICY_QUESTION)).response.status == "answered"
    state = run_graph(compiled, ChatRequest(message="What grants can we get?"))
    assert state.response.status == "abstained"
    assert state.passages == []


def test_structured_filters_from_request_reach_the_price_tool():
    seen = []

    class RecordingPriceTool:
        def query(self, filters):
            seen.append(filters)
            return PriceResult(query_id="q", filters=filters, volume=0)

    filters = PriceFilters(town="TAMPINES", flat_type="4 ROOM", start_month="2025-01", end_month="2025-12")
    run_graph(graph(price_tool=RecordingPriceTool()), ChatRequest(message="prices", price_filters=filters))
    assert seen == [filters]
