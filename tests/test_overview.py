"""Overview answers for broad questions, and related passages (graph + verifier)."""
import pytest

from kopi_keys.components.policy_retrieval import KeywordPolicyRetriever
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.components.verifier import verify
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.schemas import ChatRequest, Claim, Draft, OverviewItem
from kopi_keys.state import GraphState
from kopi_keys.topic_cards import OVERVIEW_TOPICS, load_cards, overview_topic


@pytest.mark.parametrize("question, topic", [
    ("What grants are there?", "grants"),
    ("Which schemes can singles apply for?", "grants"),
    ("Tell me about HDB loans", "loans"),
    ("What are the steps to buy a resale flat?", "buying"),
    ("How much EHG can we get?", None),            # names one scheme: normal answer
    ("What is the PHG?", None),
    ("What do 4-room flats in Tampines cost?", None),
])
def test_broad_questions_are_detected(question, topic):
    assert overview_topic(question) == topic


def test_every_overview_card_has_a_verbatim_quote():
    cards = {c.card_id: c for c in load_cards()}
    for card_ids in OVERVIEW_TOPICS.values():
        for card_id in card_ids:
            assert cards[card_id].overview is not None, card_id


@pytest.fixture(scope="module")
def grants_state():
    graph = build_graph(retriever=KeywordPolicyRetriever(), synthesiser=Synthesiser(None), cards=load_cards())
    return run_graph(graph, ChatRequest(message="What grants are there?"))


def test_broad_grant_question_builds_a_cited_overview(grants_state):
    ids = {p.id for p in grants_state.passages}
    assert [i.card_id for i in grants_state.overview] == list(OVERVIEW_TOPICS["grants"])
    assert all(i.citation_id in ids for i in grants_state.overview)
    assert any("overview:grants" in step for step in grants_state.trace)


def test_verifier_rejects_an_overview_quote_that_is_not_in_its_source(grants_state):
    good = grants_state.overview[0]
    passages = [p for p in grants_state.passages if p.id == good.citation_id]
    tampered = OverviewItem(card_id=good.card_id, title=good.title, quote="Up to $999,999 for everyone.",
                            citation_id=good.citation_id)
    draft = Draft(kind="answer", claims=[Claim(text=passages[0].text[:80], citation_ids=[passages[0].id])])
    state = GraphState(message="What grants are there?", route="policy", passages=passages, draft=draft,
                       overview=[tampered])
    assert any("not verbatim" in e for e in verify(state))
    assert not any("Overview" in e for e in verify(state.model_copy(update={"overview": [good]})))


def test_related_passages_exclude_cited_ones(grants_state):
    response = grants_state.response
    if response is None or response.status != "answered":
        pytest.skip("answer not produced without a model engine")
    cited = {c.id for c in response.citations}
    assert not cited & {p.id for p in response.related}
