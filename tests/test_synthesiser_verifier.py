import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from kopi_keys.cli import PriceCase, run_case
from kopi_keys.components.verifier import verify_generated_numbers
from kopi_keys.llm import Generation, ModelEngineError, OllamaEngine, OllamaSettings
from kopi_keys.schemas import PriceResult


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "price_sql_result.json"
VALID_TEXT = """Mean: SGD 650,000.13
Median: SGD 640,000.00
IQR: SGD 80,000.00
Range: SGD 500,000.00 to SGD 780,000.00
Volume: 42 transactions"""


@pytest.fixture
def state():
    return PriceCase.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


class FixtureEngine:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return Generation(text=response, model="test-fixture")


def test_regex_matches_field_values_and_documented_cent_rounding(state):
    assert verify_generated_numbers(VALID_TEXT, state.sql_result).passed
    assert state.sql_result.mean.as_tuple().exponent == -3  # Preserve raw SQL precision.
    assert verify_generated_numbers(VALID_TEXT.replace(",", "").replace("SGD ", "$"), state.sql_result).passed


@pytest.mark.parametrize("bad_text", [
    VALID_TEXT.replace("Mean: SGD 650,000.13", "Mean: SGD 640,000.00").replace(
        "Median: SGD 640,000.00", "Median: SGD 650,000.13",
    ),  # Same numeric set, wrong statistic labels.
    VALID_TEXT.replace("650,000.13", "650,000.12"),
    VALID_TEXT.replace("640,000.00", "640k"),
    VALID_TEXT.replace("640,000.00", "640,00.00"),
    VALID_TEXT.replace("640,000.00", "-640,000.00"),
    VALID_TEXT.replace("640,000.00", "6.4e5"),
    VALID_TEXT.replace("640,000.00", "640,000.001"),
    VALID_TEXT.replace("80,000.00", "80,000.00%"),
    VALID_TEXT.replace("42 transactions", "43 transactions"),
    VALID_TEXT.replace("42 transactions", "42.0 transactions"),
    VALID_TEXT.replace("500,000.00 to SGD 780,000.00", "780,000.00 to SGD 500,000.00"),
    VALID_TEXT.replace("Volume: 42 transactions", ""),
    VALID_TEXT + "\nMedian: SGD 640,000.00",
    VALID_TEXT + "\nA grant of SGD 100,000 also applies.",
    VALID_TEXT.replace("Median: SGD 640,000.00", "Median: SGD 640,000.00 plus SGD 20,000"),
    "These prices will rise next year.",
])
def test_regex_rejects_changed_ambiguous_or_extra_output(state, bad_text):
    assert not verify_generated_numbers(bad_text, state.sql_result).passed


def test_graph_repairs_bad_generation_and_exposes_only_verified_final_text(state):
    engine = FixtureEngine(VALID_TEXT.replace("640,000.00", "999,000.00"), VALID_TEXT)
    output = run_case(state, engine)
    assert output.response.status == "answered"
    assert output.verification_passed is True
    assert output.model_calls == 2
    assert "999,000" not in output.response.message
    assert "SYNTHETIC TEST DATA" in output.response.message
    repair_context = json.loads(engine.calls[-1][-1]["content"])
    assert any("median" in error for error in repair_context["previous_verification_errors"])
    assert "4 ROOM flats in TAMPINES" in output.response.message


def test_graph_abstains_after_one_unsuccessful_repair(state):
    engine = FixtureEngine("Median: SGD 999,000.00", "Median: SGD 999,000.00")
    output = run_case(state, engine)
    assert output.response.status == "abstained"
    assert output.verification_passed is False
    assert output.model_calls == 2
    assert "999,000" not in output.response.message


def test_empty_result_skips_model_entirely(state):
    state.sql_result = PriceResult(
        query_id="empty-result", filters=state.sql_result.filters, volume=0,
    )
    engine = FixtureEngine()
    output = run_case(state, engine)
    assert output.abstain_reason == "no_transactions"
    assert output.model_calls == 0
    assert engine.calls == []


def test_engine_unavailable_abstains_without_repeated_inference(state):
    engine = FixtureEngine(ModelEngineError("Local server unavailable"))
    output = run_case(state, engine)
    assert output.abstain_reason == "engine_unavailable"
    assert output.model_calls == 1
    assert output.verification_errors == ["Local server unavailable"]


@pytest.mark.parametrize("updates", [
    {"volume": 0},
    {"volume": True},
    {"mean": None},
    {"mean": "NaN"},
    {"median": "Infinity"},
    {"mean": "999999"},
    {"iqr": "999999"},
    {"minimum": "-1"},
])
def test_invalid_sql_context_is_rejected_before_model_call(state, updates):
    data = state.sql_result.model_dump()
    data.update(updates)
    with pytest.raises(ValidationError):
        PriceResult.model_validate(data)


def test_ollama_http_request_forces_cpu_and_records_usage():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "done": True, "done_reason": "stop", "model": "qwen2.5:3b",
            "message": {"content": VALID_TEXT}, "prompt_eval_count": 100, "eval_count": 70,
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generation = OllamaEngine(client=client).complete([{"role": "user", "content": "format"}])
    assert requests[0]["options"]["num_gpu"] == 0
    assert requests[0]["options"]["temperature"] == 0
    assert requests[0]["stream"] is False
    assert generation.usage["output_tokens"] == 70


@pytest.mark.parametrize("data", [
    {"done": False, "message": {"content": VALID_TEXT}},
    {"done": True, "done_reason": "length", "message": {"content": VALID_TEXT}},
    {"done": True, "message": {"content": ""}},
    {"error": "model failed"},
])
def test_incomplete_model_responses_do_not_become_answers(data):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
        with pytest.raises(ModelEngineError):
            OllamaEngine(client=client).complete([])


def test_timeout_and_missing_model_have_actionable_errors():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ModelEngineError, match="timed out"):
            OllamaEngine(client=client).complete([])
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        with pytest.raises(ModelEngineError, match="Pull qwen2.5:3b"):
            OllamaEngine(client=client).complete([])


def test_settings_can_switch_model_without_changing_node_code(monkeypatch):
    monkeypatch.setenv("KOPI_OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("KOPI_OLLAMA_NUM_THREADS", "2")
    settings = OllamaSettings.from_env()
    assert settings.model == "llama3.2:3b"
    assert settings.num_threads == 2
