"""GPU is opt-in; GPU benchmark reports must reject silent CPU fallback."""

import json
import os
import subprocess
import sys

import httpx
import pytest

from kopi_keys.llm import ModelEngineError, OllamaEngine, OllamaSettings


@pytest.mark.parametrize("generation_url,embedding_url,expected", [
    (None, None, "http://127.0.0.1:11434"),
    ("http://127.0.0.1:11435", None, "http://127.0.0.1:11435"),
    ("http://127.0.0.1:11435", "http://127.0.0.1:11434", "http://127.0.0.1:11434"),
])
def test_embedding_endpoint_can_stay_local_when_generation_moves_to_gpu(
    generation_url, embedding_url, expected,
):
    # Configuration is read at import. A fresh process avoids reloading shared
    # exception classes used by the retrieval tests.
    env = os.environ.copy()
    for key, value in (("KOPI_OLLAMA_BASE_URL", generation_url),
                       ("KOPI_EMBED_BASE_URL", embedding_url)):
        env.pop(key, None)
        if value is not None:
            env[key] = value
    result = subprocess.run(
        [sys.executable, "-c", "from kopi_keys.components.policy_index import OLLAMA_URL; print(OLLAMA_URL)"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == expected


def test_gpu_mode_omits_cpu_override_for_load_and_chat():
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": "A fixture response."}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        engine = OllamaEngine(OllamaSettings(device="gpu"), client)
        engine.warm_up()
        generation = engine.complete([{"role": "user", "content": "Fixture"}])
    assert all("num_gpu" not in p["options"] for p in payloads)
    assert generation.usage["device_requested"] == "gpu"
    assert generation.usage["num_gpu_requested"] is None


def test_cpu_remains_explicit_for_load_and_chat():
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": "A fixture response."}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        engine = OllamaEngine(OllamaSettings(), client)
        engine.warm_up()
        generation = engine.complete([{"role": "user", "content": "Fixture"}])
    assert all(p["options"]["num_gpu"] == 0 for p in payloads)
    assert generation.usage["device_requested"] == "cpu"


def test_env_and_policy_clone_preserve_gpu_mode(monkeypatch):
    monkeypatch.setenv("KOPI_OLLAMA_DEVICE", "GPU")
    settings = OllamaSettings.from_env()
    policy = OllamaEngine(settings).for_policy({"type": "object"}, model_override="qwen2.5:32b")
    assert settings.device == policy.settings.device == "gpu"
    assert policy.settings.model == "qwen2.5:32b"
    with pytest.raises(ValueError, match="cpu or gpu"):
        OllamaSettings(device="typo")


@pytest.mark.parametrize("models", [[], [{"name": "qwen2.5:3b", "size_vram": 0}],
                                   [{"name": "another-model", "size_vram": 1000}]])
def test_gpu_check_rejects_cpu_fallback_or_a_different_loaded_model(models):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"models": models}))) as client:
        with pytest.raises(ModelEngineError, match="no reported GPU offload"):
            OllamaEngine(OllamaSettings(device="gpu"), client).verify_gpu_loaded()


def test_gpu_check_preserves_memory_record_without_claiming_full_offload():
    model = {"name": "qwen2.5:3b", "size": 3000, "size_vram": 1500}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"models": [model]}))) as client:
        assert OllamaEngine(OllamaSettings(device="gpu"), client).verify_gpu_loaded() == model
