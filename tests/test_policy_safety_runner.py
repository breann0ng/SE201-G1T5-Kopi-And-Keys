"""Verify the safety oracle with adversarial fixtures, not claimed live results."""

import json

import pytest
import httpx

from kopi_keys.evaluation.policy_safety import check_result, load_cases, main, run_case
from kopi_keys.llm import Generation, ModelEngineError, OllamaEngine, OllamaSettings


DATA, SOURCES = load_cases()


class Engine:
    def __init__(self, output):
        self.output = output

    def complete(self, messages):
        if isinstance(self.output, Exception):
            raise self.output
        return Generation(text=self.output, model="synthetic-test-fixture")


@pytest.mark.parametrize("row", DATA["cases"], ids=lambda row: row["id"])
def test_synthetic_safety_labels_are_exercised_by_the_real_graph(row):
    ids = row["source_ids"]
    # Deliberately quote the first passage, including poisoned and wrong-scope
    # passages. The production verifier must contain the bad fixture outputs.
    items = [{"citation_id": ids[0], "supporting_quote": SOURCES[ids[0]].text}] if ids else []
    record = run_case(row, SOURCES, Engine(json.dumps({"claims": items})))
    assert record["passed"], record["reasons"]
    assert record["model_calls"] <= 2


def test_model_outage_does_not_count_as_successful_attack_containment():
    row = DATA["cases"][1]
    record = run_case(row, SOURCES, Engine(ModelEngineError("Fixture outage")))
    assert record["availability_error"] and not record["passed"]


def test_refusing_everything_cannot_pass_the_clean_positive_control():
    record = run_case(DATA["cases"][0], SOURCES, Engine('{"claims": []}'))
    assert record["status"] == "abstained" and not record["passed"]


def test_default_command_validates_without_creating_an_engine(monkeypatch):
    monkeypatch.setattr("kopi_keys.evaluation.policy_safety.OllamaEngine",
                        lambda *args: pytest.fail("Validation must not load or call a model"))
    assert main([]) == 0


def test_benchmark_model_wins_over_the_normal_application_policy_override(monkeypatch):
    monkeypatch.setenv("KOPI_POLICY_MODEL", "another-model-from-application-env")
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
            "claims": [{"citation_id": "SAFE_EHG", "supporting_quote": SOURCES["SAFE_EHG"].text}],
        })}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        record = run_case(DATA["cases"][0], SOURCES,
                          OllamaEngine(OllamaSettings(model="selected-benchmark-model"), client))
    assert record["passed"]
    assert requests[0]["model"] == "selected-benchmark-model"
