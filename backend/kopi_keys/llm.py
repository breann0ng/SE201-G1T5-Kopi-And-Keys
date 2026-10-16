"""Local LLM engine (Ollama over HTTP), shared by every LLM component. CPU only."""

import os
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Protocol

import httpx
from langsmith import traceable


class ModelEngineError(RuntimeError):
    """Expected local runtime, HTTP or model-output failure."""


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: float = 180
    num_threads: int = 4
    context_size: int = 2048
    max_output_tokens: int = 220
    response_format: dict | None = None

    def __post_init__(self):
        url = httpx.URL(self.base_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("Ollama base URL must be an HTTP(S) URL.")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Ollama base URL must not contain credentials, a query or a fragment.")
        if not self.model.strip():
            raise ValueError("A model name is required.")
        if self.timeout_seconds <= 0 or min(self.num_threads, self.context_size, self.max_output_tokens) < 1:
            raise ValueError("Timeout and inference limits must be positive.")

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.getenv("KOPI_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            model=os.getenv("KOPI_OLLAMA_MODEL", "qwen2.5:3b"),
            timeout_seconds=float(os.getenv("KOPI_OLLAMA_TIMEOUT", "180")),
            num_threads=int(os.getenv("KOPI_OLLAMA_NUM_THREADS", "4")),
        )


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    usage: dict = field(default_factory=dict)


class TextEngine(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> Generation: ...


class OllamaEngine:
    def __init__(self, settings: OllamaSettings | None = None, client: httpx.Client | None = None):
        self.settings = settings or OllamaSettings.from_env()
        self._client = client

    def for_policy(self, schema: dict):
        """Separate policy budgets; the strict price formatter keeps its limits."""
        settings = replace(
            self.settings, context_size=4096, max_output_tokens=850,
            response_format=schema,
            model=os.getenv("KOPI_POLICY_MODEL", self.settings.model),
        )
        return OllamaEngine(settings=settings, client=self._client)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        def send(client):
            response = client.request(
                method, f"{self.settings.base_url.rstrip('/')}{path}",
                json=payload, timeout=self.settings.timeout_seconds,
            )
            if response.status_code == 404:
                raise ModelEngineError(f"Ollama model or endpoint not found. Pull {self.settings.model} first.")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("error"):
                raise ModelEngineError("Ollama returned an invalid or failed response.")
            return data

        try:
            if self._client is not None:
                return send(self._client)
            # Ignore machine proxy variables for the default local server.
            with httpx.Client(trust_env=False) as client:
                return send(client)
        except httpx.TimeoutException as error:
            raise ModelEngineError("Ollama timed out before completing the response.") from error
        except httpx.HTTPError as error:
            raise ModelEngineError("Ollama request failed. Check the local server and model installation.") from error
        except ValueError as error:
            raise ModelEngineError("Ollama did not return valid JSON.") from error

    @traceable(run_type="llm", name="ollama_chat")
    def complete(self, messages: list[dict[str, str]]) -> Generation:
        started = perf_counter()
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "num_gpu": 0,
                "num_thread": self.settings.num_threads,
                "num_ctx": self.settings.context_size,
                "num_predict": self.settings.max_output_tokens,
                "temperature": 0,
                "seed": 42,
            },
        }
        if self.settings.response_format is not None:
            payload["format"] = self.settings.response_format
        if self.settings.model.startswith("qwen3"):
            payload["think"] = False
        data = self._request("POST", "/api/chat", payload)
        message = data.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if data.get("done") is not True or not isinstance(text, str) or not text.strip():
            raise ModelEngineError("Ollama returned no completed text response.")
        if data.get("done_reason") == "length":
            raise ModelEngineError("Ollama response was truncated at the output-token limit.")
        return Generation(
            text=text.strip(), model=str(data.get("model", self.settings.model)),
            usage={
                "elapsed_seconds": round(perf_counter() - started, 3),
                "prompt_tokens": data.get("prompt_eval_count"),
                "output_tokens": data.get("eval_count"),
                "num_gpu_requested": 0,
            },
        )

    def inspect(self) -> dict:
        version = self._request("GET", "/api/version")
        tags = self._request("GET", "/api/tags")
        return {
            "version": version.get("version"),
            "configured_model": self.settings.model,
            "installed_models": [model.get("name") for model in tags.get("models", [])],
            "loaded_models": self._request("GET", "/api/ps").get("models", []),
        }
