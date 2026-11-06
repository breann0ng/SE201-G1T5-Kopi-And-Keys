"""Ollama over HTTP, with CPU by default and opt-in allocated GPU inference."""

import os
import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Literal, Protocol

import httpx
from langsmith import traceable

from .cancellation import request_cancelled


class ModelEngineError(RuntimeError):
    """Expected local runtime, HTTP or model-output failure."""


class GenerationCancelled(ModelEngineError):
    """The client stopped its request; partial model text must not be shown."""


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: float = 180
    num_threads: int = 4
    context_size: int = 2048
    max_output_tokens: int = 220
    response_format: dict | None = None
    # Added 2026-10-17: how long Ollama keeps the model in memory after a request.
    # Reloading it costs 10-20 s on a laptop CPU; "-1" keeps it until Ollama stops.
    keep_alive: str = "30m"
    device: Literal["cpu", "gpu"] = "cpu"

    def __post_init__(self):
        url = httpx.URL(self.base_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("Ollama base URL must be an HTTP(S) URL.")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Ollama base URL must not contain credentials, a query or a fragment.")
        if not self.model.strip():
            raise ValueError("A model name is required.")
        if self.device not in {"cpu", "gpu"}:
            raise ValueError("Ollama device must be cpu or gpu.")
        if self.timeout_seconds <= 0 or min(self.num_threads, self.context_size, self.max_output_tokens) < 1:
            raise ValueError("Timeout and inference limits must be positive.")

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.getenv("KOPI_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            model=os.getenv("KOPI_OLLAMA_MODEL", "qwen2.5:3b"),
            timeout_seconds=float(os.getenv("KOPI_OLLAMA_TIMEOUT", "180")),
            num_threads=int(os.getenv("KOPI_OLLAMA_NUM_THREADS", "4")),
            keep_alive=os.getenv("KOPI_OLLAMA_KEEP_ALIVE", "30m"),
            device=os.getenv("KOPI_OLLAMA_DEVICE", "cpu").strip().lower(),
        )


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    usage: dict = field(default_factory=dict)


def _trace_inputs(inputs: dict) -> dict:
    # Do not send prompts, profiles, retrieved text or the engine/client repr to
    # LangSmith. Request contents still reach the explicitly configured Ollama.
    return {"message_count": len(inputs.get("messages", [])), "content_redacted": True}


def _trace_outputs(output) -> dict:
    usage = getattr(output, "usage", {})
    allowed = ("elapsed_seconds", "prompt_tokens", "output_tokens", "num_gpu_requested",
               "load_seconds", "prompt_eval_seconds", "generation_seconds")
    clean = {key: usage[key] for key in allowed
             if isinstance(usage.get(key), (int, float)) and not isinstance(usage[key], bool)}
    if usage.get("device_requested") in {"cpu", "gpu"}:
        clean["device_requested"] = usage["device_requested"]
    return {"usage": clean, "content_redacted": True}


class TextEngine(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> Generation: ...


class OllamaEngine:
    def __init__(self, settings: OllamaSettings | None = None, client: httpx.Client | None = None):
        self.settings = settings or OllamaSettings.from_env()
        self._client = client

    def for_policy(self, schema: dict, model_override: str | None = None):
        """Separate policy budgets; the strict price formatter keeps its limits."""
        settings = replace(
            self.settings, context_size=4096, max_output_tokens=850,
            response_format=schema,
            model=model_override or os.getenv("KOPI_POLICY_MODEL", self.settings.model),
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

    async def _cancelable_chat(self, payload: dict, cancelled) -> dict:
        """Consume tokens privately; close HTTP even when stopped during prefill.

        Token streaming is internal only. The graph still verifies the complete
        draft before sending any answer text to the UI.
        """
        async def consume():
            async with httpx.AsyncClient(trust_env=False, timeout=self.settings.timeout_seconds) as client:
                async with client.stream("POST", f"{self.settings.base_url.rstrip('/')}/api/chat",
                                         json={**payload, "stream": True}) as response:
                    response.raise_for_status()
                    parts = []
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        if not isinstance(data, dict) or data.get("error"):
                            raise ModelEngineError("Ollama returned a failed streamed response.")
                        message = data.get("message") or {}
                        if not isinstance(message, dict):
                            raise ModelEngineError("Ollama returned an invalid streamed message.")
                        if isinstance(message.get("content"), str):
                            parts.append(message["content"])
                        if data.get("done") is True:
                            return {**data, "message": {"content": "".join(parts)}}
            raise ModelEngineError("Ollama returned no completed streamed response.")

        async def wait_for_stop():
            while not cancelled.is_set():
                await asyncio.sleep(0.05)

        if cancelled.is_set():
            raise GenerationCancelled("Generation stopped by the client.")
        generation = asyncio.create_task(consume())
        stopping = asyncio.create_task(wait_for_stop())
        try:
            done, _ = await asyncio.wait({generation, stopping}, timeout=self.settings.timeout_seconds,
                                         return_when=asyncio.FIRST_COMPLETED)
            if stopping in done or cancelled.is_set():
                raise GenerationCancelled("Generation stopped by the client.")
            if generation not in done:
                raise ModelEngineError("Ollama timed out before completing the response.")
            return await generation
        except httpx.TimeoutException as error:
            raise ModelEngineError("Ollama timed out before completing the response.") from error
        except httpx.HTTPError as error:
            raise ModelEngineError("Ollama request failed. Check the local server and model installation.") from error
        except ValueError as error:
            raise ModelEngineError("Ollama did not return valid streamed JSON.") from error
        finally:
            for task in (generation, stopping):
                task.cancel()
                with suppress(asyncio.CancelledError, ModelEngineError, httpx.HTTPError, ValueError):
                    await task

    def warm_up(self) -> None:
        """Load the model into memory without generating anything (Ollama: a request with no
        prompt). Called once at startup so the first question doesn't pay the load time."""
        self._request("POST", "/api/generate", {
            "model": self.settings.model, "keep_alive": self.settings.keep_alive,
            "options": self._hardware_options(),
        })

    def _hardware_options(self) -> dict:
        options = {"num_thread": self.settings.num_threads, "num_ctx": self.settings.context_size}
        if self.settings.device == "cpu":
            options["num_gpu"] = 0
        # Omitting num_gpu lets Ollama offload onto scheduler-visible GPUs.
        # Do not change CUDA_VISIBLE_DEVICES or expose unallocated devices.
        return options

    def verify_gpu_loaded(self) -> dict:
        """Reject CPU fallback before calling a timed GPU benchmark a GPU result.

        Positive VRAM proves some offload, not that the whole model fits. Keep
        the full loading record so partial offload can be reviewed separately.
        """
        models = self._request("GET", "/api/ps").get("models", [])
        model = next((m for m in models if m.get("name") == self.settings.model
                      or m.get("model") == self.settings.model), None)
        if model is None or not isinstance(model.get("size_vram"), (int, float)) or model["size_vram"] <= 0:
            raise ModelEngineError("GPU mode was requested, but the selected model has no reported GPU offload. Check the allocation, drivers and ollama ps.")
        return model

    def unload(self) -> None:
        """Release this model between benchmark batches without stopping Ollama."""
        self._request("POST", "/api/generate", {"model": self.settings.model, "keep_alive": 0})

    @traceable(run_type="llm", name="ollama_chat", process_inputs=_trace_inputs, process_outputs=_trace_outputs)
    def complete(self, messages: list[dict[str, str]]) -> Generation:
        started = perf_counter()
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                **self._hardware_options(),
                "num_predict": self.settings.max_output_tokens,
                "temperature": 0,
                "seed": 42,
            },
        }
        if self.settings.response_format is not None:
            payload["format"] = self.settings.response_format
        if self.settings.model.startswith("qwen3"):
            payload["think"] = False
        cancelled = request_cancelled.get()
        data = (asyncio.run(self._cancelable_chat(payload, cancelled)) if cancelled is not None
                else self._request("POST", "/api/chat", payload))
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
                "num_gpu_requested": 0 if self.settings.device == "cpu" else None,
                "device_requested": self.settings.device,
                "load_seconds": round(data.get("load_duration", 0) / 1e9, 3),
                "prompt_eval_seconds": round(data.get("prompt_eval_duration", 0) / 1e9, 3),
                "generation_seconds": round(data.get("eval_duration", 0) / 1e9, 3),
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
