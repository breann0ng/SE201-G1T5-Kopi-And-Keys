"""answers_aspect: does each policy quote answer an asked part of the question (no Ollama)."""

import json
from datetime import date

import pytest

from kopi_keys.components.answer_aspects import asked_aspects, check_claim
from kopi_keys.components.policy_guardrails import score_relevance
from kopi_keys.components.policy_synthesis import PolicySummariser, answer_schema
from kopi_keys.components.verifier import policy_relevance_scores, verify
from kopi_keys.llm import Generation
from kopi_keys.schemas import Claim, Draft, PolicyPassage
from kopi_keys.state import GraphState

HFE = ("You must have a valid HFE letter before you obtain an Option to Purchase. "
       "The HFE letter is valid for 9 months.")
Q_VALID = "How long is an HFE letter valid for?"
OFF_TARGET = "You must have a valid HFE letter before you obtain an Option to Purchase."
ON_TARGET = "The HFE letter is valid for 9 months."


def passage(cid="hfe", text=HFE, title="HFE letter"):
    return PolicyPassage(id=cid, text=text, title=title, source_url="demo://aspects/" + cid,
                         snapshot_id="fictional-aspects", verified_on=date(2026, 11, 8))


def claim(quote, aspect, cid="hfe"):
    return Claim(text=quote, citation_ids=[cid], supporting_quote=quote, answers_aspect=aspect)


def state(*claims, question=Q_VALID, intent="policy"):
    return GraphState(message=question, route="policy", intent=intent, passages=[passage()],
                      draft=Draft(kind="answer", claims=list(claims)))


# --- What the question asks ---------------------------------------------------

@pytest.mark.parametrize("question, asked", [
    ("How long is an HFE letter valid for?", ["timing"]),
    ("What is the EHG income ceiling?", ["income"]),
    ("Does the age of the flat change how much CPF we can use?", ["amount", "lease", "cpf"]),
    ("For PHG, how near must the resale flat be to my parents?", ["distance"]),
    # Grant names are topics, not asks.
    ("Can EHG and PHG be combined?", []),
    ("How much can the Enhanced CPF Housing Grant give a first-time couple at most?", ["amount"]),
    ("Can we get the Step-Up grant?", []),
    ("Explain Proximity Housing Grant (PHG) conditions.", []),
    # Instructions on what not to do are not asks (SYN-02, a false reject in the benchmark).
    ("Can we combine EHG and PHG? Explain the prerequisite without adding maximum amounts together.", []),
])
def test_asked_aspects_come_from_what_the_question_asks(question, asked):
    assert asked_aspects(question) == asked


# --- The known false pass -------------------------------------------------------

def test_a_quote_sharing_the_words_but_not_the_answer_now_fails():
    # Word overlap passes it: hfe, letter, valid all match.
    assert score_relevance(Q_VALID, OFF_TARGET, "HFE letter").score >= 0.2
    result = check_claim(Q_VALID, claim(OFF_TARGET, "timing"))
    assert result["aspect_ok"] is False and "does not address" in result["aspect_reason"]
    assert check_claim(Q_VALID, claim(ON_TARGET, "timing"))["aspect_ok"] is True


@pytest.mark.parametrize("aspect, reason", [
    ("other", "none of the asked aspects"),
    ("income", "was not asked"),  # only reachable without the schema's enum (fixtures, other engines)
])
def test_other_or_unasked_labels_fail(aspect, reason):
    assert reason in check_claim(Q_VALID, claim(ON_TARGET, aspect))["aspect_reason"]


def test_without_a_model_label_code_finds_the_aspect_the_quote_shows():
    on, off = check_claim(Q_VALID, claim(ON_TARGET, None)), check_claim(Q_VALID, claim(OFF_TARGET, None))
    assert (on["aspect"], on["aspect_source"], on["aspect_ok"]) == ("timing", "code", True)
    assert (off["aspect"], off["aspect_ok"]) == ("other", False)


def test_nothing_is_checked_without_a_quote_or_an_asked_aspect():
    assert check_claim(Q_VALID, Claim(text="x", citation_ids=["hfe"])) is None  # legacy fixtures
    assert check_claim("Can EHG and PHG be combined?", claim(ON_TARGET, None))["aspect_ok"] is True


def test_table_criterion_counts_as_evidence():
    row = Claim(text="x", citation_ids=["t"], supporting_quote="Must not exceed $9,000",
                source_criterion="Monthly household income ceiling", answers_aspect="income")
    assert check_claim("What is the EHG income ceiling?", row)["aspect_ok"] is True


# --- Modes in the verifier --------------------------------------------------------

@pytest.mark.parametrize("label", ["timing", None])
def test_shadow_records_but_never_blocks(monkeypatch, label):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", "shadow")
    s = state(claim(OFF_TARGET, label))
    assert not verify(s)
    assert policy_relevance_scores(s)[0]["aspect_ok"] is False


@pytest.mark.parametrize("label", ["timing", None])
def test_enforce_blocks_the_failing_claim(monkeypatch, label):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", "enforce")
    errors = verify(state(claim(OFF_TARGET, label)))
    assert any("does not answer the question" in e and "asked: timing" in e for e in errors)
    assert not verify(state(claim(ON_TARGET, label)))


def test_discovery_questions_are_not_checked(monkeypatch):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", "enforce")
    assert not verify(state(claim(OFF_TARGET, "other"), intent="discovery"))
    assert "aspect_ok" not in policy_relevance_scores(state(claim(OFF_TARGET, "other"), intent="discovery"))[0]


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", "maybe")
    with pytest.raises(ValueError):
        verify(state(claim(ON_TARGET, "timing")))


# --- Asking the model for the label ------------------------------------------------

def test_schema_offers_only_the_asked_aspects_and_other():
    claim_schema = answer_schema(["hfe"], 3, Q_VALID, label_aspects=True)["$defs"]["PolicyClaim"]
    assert claim_schema["properties"]["answers_aspect"]["enum"] == ["timing", "other"]
    assert "answers_aspect" in claim_schema["required"]
    off = answer_schema(["hfe"], 3, Q_VALID, label_aspects=False)["$defs"]["PolicyClaim"]
    assert "answers_aspect" not in off["properties"]


class Engine:
    def __init__(self, text):
        self.text, self.calls = text, []

    def complete(self, messages):
        self.calls.append(messages)
        return Generation(text=self.text, model="fictional-test")


@pytest.mark.parametrize("mode, label, sent, kept", [
    ("shadow", "model", True, "timing"),
    ("shadow", "code", False, None),   # the default: generation is unchanged
    ("off", "model", False, None),
])
def test_summariser_asks_for_the_label_only_in_model_mode(monkeypatch, mode, label, sent, kept):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", mode)
    monkeypatch.setenv("KOPI_ASPECT_LABEL", label)
    engine = Engine(json.dumps({"claims": [{"citation_id": "hfe", "supporting_quote": ON_TARGET,
                                            "answers_aspect": "timing"}]}))
    claims, _, errors = PolicySummariser(engine).generate(state())
    context = json.loads(engine.calls[0][-1]["content"])
    assert ("asked_aspects" in context["answer_requirements"]) is sent
    assert ("answers_aspect" in engine.calls[0][0]["content"]) is sent
    assert claims[0].answers_aspect == kept and not errors


def test_a_missing_model_label_counts_as_other(monkeypatch):
    monkeypatch.setenv("KOPI_ASPECT_CHECK", "shadow")
    monkeypatch.setenv("KOPI_ASPECT_LABEL", "model")
    engine = Engine(json.dumps({"claims": [{"citation_id": "hfe", "supporting_quote": ON_TARGET}]}))
    claims, _, _ = PolicySummariser(engine).generate(state())
    assert claims[0].answers_aspect == "other"
