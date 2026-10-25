"""Finals regressions: irrelevant-but-real quotes and incomplete grant logic."""

import json
from datetime import date

import httpx
import pytest

from kopi_keys.components.policy_guardrails import requested_grants, score_relevance
from kopi_keys.components.policy_synthesis import PolicySummariser
from kopi_keys.components.synthesiser import Synthesiser
from kopi_keys.components.verifier import verify
from kopi_keys.graph import build_graph, run_graph
from kopi_keys.llm import Generation, OllamaEngine, OllamaSettings
from kopi_keys.schemas import ChatRequest, Claim, Draft, PolicyPassage
from kopi_keys.state import GraphState


EHG = "Applicants for EHG must meet the household income and employment conditions."
PHG = "The PHG supports families buying a resale flat near their parents."
LINK = "EHG may be combined with PHG if each grant's conditions are met."
DEPENDENCY = "You must first qualify for the CPF Housing Grant for Resale Flats before you may be eligible for the EHG."
QUESTION = "Can EHG and PHG be combined for a resale flat?"


def passage(cid, text, title="Grant rules"):
    return PolicyPassage(id=cid, text=text, title=title, source_url="demo://finals/" + cid,
                         snapshot_id="fictional-finals", verified_on=date(2026, 10, 26))


SOURCES = [passage("ehg", EHG, "EHG"), passage("phg", PHG, "PHG"),
           passage("link", LINK + " " + DEPENDENCY, "Grant combination")]


def claim(cid, text):
    return Claim(text=text, citation_ids=[cid], supporting_quote=text)


def state(*claims, question=QUESTION, sources=None):
    return GraphState(message=question, route="policy", passages=SOURCES if sources is None else sources,
                      draft=Draft(kind="answer", claims=list(claims)))


def output(*items, missing=()):
    return json.dumps({"claims": [{"citation_id": cid, "supporting_quote": quote} for cid, quote in items],
                       "missing_evidence": list(missing)})


class Engine:
    def __init__(self, *outputs):
        self.outputs, self.calls = iter(outputs), []

    def complete(self, messages):
        self.calls.append(messages)
        return Generation(text=next(self.outputs), model="fictional-test")


class Retriever:
    def search(self, query, limit=5):
        return SOURCES[:limit]


def test_combination_must_cover_every_grant_and_preserve_prerequisite():
    assert not verify(state(claim("link", LINK + " " + DEPENDENCY)))
    errors = verify(state(claim("ehg", EHG)))
    assert any("Missing requested grant" in e for e in errors)
    assert any("combination rule" in e for e in errors)
    assert any("prerequisite" in e for e in errors)


def test_two_independent_descriptions_do_not_prove_stacking():
    errors = verify(state(claim("ehg", EHG), claim("phg", PHG)))
    assert any("combination rule" in e for e in errors)
    assert not any("Missing requested grant" in e for e in errors)


def test_compare_question_does_not_require_stacking_rule():
    assert not verify(state(claim("ehg", EHG), claim("phg", PHG), question="Compare EHG and PHG."))


def test_new_flat_exclusion_does_not_require_resale_stacking_or_its_prerequisite():
    only = passage("new", "For a new flat, the only housing grant is EHG.", "EHG")
    resale = passage("resale", "PHG helps eligible buyers of resale flats.", "PHG")
    assert not verify(state(claim(only.id, only.text), claim(resale.id, resale.text),
                            question="Can I combine EHG and PHG for a new flat?", sources=[only, resale]))


def test_household_specific_answer_rejects_an_opposite_scoped_source():
    p = passage("single", "The income ceiling for singles is a source-specific amount.", "EHG for Singles")
    errors = verify(state(claim(p.id, p.text), question="What is the EHG income ceiling for first-timer families?", sources=[p]))
    assert any("opposite household scope" in e for e in errors)


def test_household_context_survives_a_generic_chunk_heading():
    p = passage("singles", "Monthly household income ceiling: $4,500. Read more about EHG for first-timer singles.", "EHG eligibility")
    quote = "Monthly household income ceiling: $4,500."
    errors = verify(state(claim(p.id, quote), question="What is the EHG income ceiling for families?", sources=[p]))
    assert any("opposite household scope" in e for e in errors)


def test_relevance_rejects_real_but_unrelated_quote():
    p = passage("loan", "Apply for an HFE letter before applying for an HDB housing loan.", "HDB loans")
    errors = verify(state(claim(p.id, p.text), question="What are the EHG income conditions?", sources=[p]))
    assert any("Low policy relevance" in e for e in errors)


def test_same_grant_wrong_aspect_does_not_pass_on_its_heading():
    score = score_relevance("What is the EHG income ceiling?", "Applicants must be Singapore Citizens.", "EHG")
    assert score.score == 0
    assert score_relevance("What is the EHG income ceiling?", "Monthly household income must meet the ceiling.", "EHG").score > 0.2
    assert score_relevance("Combine EHG and PHG without adding maximum amounts together.", LINK, "EHG and PHG").score > 0.2


def test_presentational_emphasis_can_be_omitted_but_qualifications_cannot():
    p = passage("emphasis", "For **first-timer families**, EHG depends on <u>household income</u>.", "EHG")
    plain = "For first-timer families, EHG depends on household income."
    assert not verify(state(claim(p.id, plain), question="Explain EHG income conditions for families.", sources=[p]))
    changed = "For all families, EHG depends on household income."
    assert any("not present" in e for e in verify(state(claim(p.id, changed), question="Explain EHG income conditions.", sources=[p])))


def test_partial_multi_grant_answer_cannot_be_salvaged_as_a_complete_answer():
    incomplete = output(("ehg", EHG), ("phg", "An invented condition for PHG."))
    engine = Engine(incomplete, incomplete)
    final = run_graph(build_graph(retriever=Retriever(), synthesiser=Synthesiser(engine), cards=[]),
                      ChatRequest(message=QUESTION))
    assert final.response.status == "abstained" and final.model_calls == 2
    assert any("combination rule" in e for e in final.verification_errors)


def test_retry_receives_actual_json_validation_error_and_allowed_ids():
    engine = Engine(output(("invented-id", LINK)), output(("link", LINK + " " + DEPENDENCY)))
    final = run_graph(build_graph(retriever=Retriever(), synthesiser=Synthesiser(engine), cards=[]),
                      ChatRequest(message=QUESTION))
    assert final.response.status == "answered" and final.model_calls == 2
    context = json.loads(engine.calls[-1][-1]["content"])
    assert any("citation was not supplied" in e for e in context["previous_verification_errors"])
    assert set(context["allowed_citation_ids"]) == {p.id for p in SOURCES}
    assert context["answer_requirements"]["combination_rule_required"]


def test_low_score_triggers_one_repair_then_abstention():
    p = passage("loan", "HDB loans are repaid in monthly instalments.", "HDB loan")
    class Loans:
        def search(self, query, limit=5): return [p]
    engine = Engine(output((p.id, p.text)), output((p.id, p.text)))
    final = run_graph(build_graph(retriever=Loans(), synthesiser=Synthesiser(engine), cards=[]),
                      ChatRequest(message="Tell me about the EHG income ceiling."))
    assert final.response.status == "abstained" and final.model_calls == 2
    assert final.relevance_scores[0]["score"] == 0
    assert "instalments" not in final.response.message


def test_explicit_missing_evidence_cannot_be_dropped_by_claim_salvage():
    engine = Engine(output(("ehg", EHG), missing=["PHG combination rule"]),
                    output(("ehg", EHG), missing=["PHG combination rule"]))
    final = run_graph(build_graph(retriever=Retriever(), synthesiser=Synthesiser(engine), cards=[]),
                      ChatRequest(message=QUESTION))
    assert final.response.status == "abstained"
    assert any("Missing policy evidence" in e for e in final.verification_errors)


def test_ollama_schema_enumerates_only_this_requests_sources_and_pins_benchmark_model(monkeypatch):
    monkeypatch.setenv("KOPI_POLICY_MODEL", "another-model:7b")
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": output(("ehg", EHG))}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        engine = OllamaEngine(OllamaSettings(model="qwen2.5:3b"), client)
        summary = PolicySummariser(engine, model_override="qwen2.5:3b")
        summary.generate(state(question="Explain EHG.", sources=[SOURCES[0]]))
        summary.generate(state(question="Explain PHG.", sources=[SOURCES[1]]))
    assert requests[0]["format"]["$defs"]["PolicyClaim"]["properties"]["citation_id"]["enum"] == ["ehg"]
    assert requests[1]["format"]["$defs"]["PolicyClaim"]["properties"]["citation_id"]["enum"] == ["phg"]
    assert requests[0]["model"] == "qwen2.5:3b"
    assert requests[0]["options"]["num_gpu"] == 0


def test_benchmark_unload_releases_only_the_requested_model():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "done_reason": "unload"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        OllamaEngine(OllamaSettings(model="qwen3:4b"), client).unload()
    assert requests == [{"model": "qwen3:4b", "keep_alive": 0}]


@pytest.mark.parametrize("question", ["Stack EHG with PHG", "Combine Enhanced CPF Housing Grant and Proximity Housing Grant"])
def test_full_names_and_acronyms_have_the_same_grant_requirements(question):
    assert requested_grants(question) == {"ehg", "phg"}


def test_standalone_cpf_grant_is_distinct_from_the_full_ehg_name():
    assert requested_grants("Enhanced CPF Housing Grant") == {"ehg"}
    assert requested_grants("Combine EHG, CPF Housing Grant and PHG") == {"ehg", "phg", "family_grant"}


def test_complex_question_retains_distinct_chunks_under_the_same_heading():
    first = SOURCES[0].model_copy(update={"source_url": "demo://shared", "title": "Grant conditions"})
    second = SOURCES[1].model_copy(update={"source_url": "demo://shared", "title": "Grant conditions"})
    engine = Engine(output((first.id, first.text), (second.id, second.text)))
    claims, _, errors = PolicySummariser(engine).generate(state(
        question="Compare EHG and PHG.", sources=[first, second]))
    context = json.loads(engine.calls[0][-1]["content"])
    assert {p["id"] for p in context["evidence"]} == {first.id, second.id}
    assert len(claims) == 2 and not errors
