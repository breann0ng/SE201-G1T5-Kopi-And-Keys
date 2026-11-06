"""A stopped chat must cancel prefill/body reads and never cache a partial answer."""

import asyncio
import json
import threading

import httpx
import pytest

from kopi_keys.cancellation import request_cancelled
from kopi_keys.llm import GenerationCancelled, ModelEngineError, OllamaEngine, OllamaSettings
from kopi_keys.main import create_app
from kopi_keys.schemas import ChatRequest, ChatResponse


def transport_client(monkeypatch, handler):
    factory = httpx.AsyncClient
    monkeypatch.setattr("kopi_keys.llm.httpx.AsyncClient", lambda **kwargs:
                        factory(transport=httpx.MockTransport(handler), **kwargs))


def test_stop_interrupts_prefill_before_response_headers(monkeypatch):
    closed = []

    async def handler(request):
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    transport_client(monkeypatch, handler)

    async def exercise():
        stopped = threading.Event()
        asyncio.get_running_loop().call_later(0.05, stopped.set)
        with pytest.raises(GenerationCancelled):
            await OllamaEngine()._cancelable_chat({}, stopped)
        assert closed

    asyncio.run(asyncio.wait_for(exercise(), timeout=2))


def test_stop_closes_a_partial_stream_without_exposing_unverified_tokens(monkeypatch):
    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message":{"content":"UNVERIFIED_PARTIAL"},"done":false}\n'
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    transport_client(monkeypatch, lambda request: httpx.Response(200, stream=Body()))

    async def exercise():
        stopped = threading.Event()
        asyncio.get_running_loop().call_later(0.05, stopped.set)
        with pytest.raises(GenerationCancelled):
            await OllamaEngine()._cancelable_chat({}, stopped)
        assert closed

    asyncio.run(asyncio.wait_for(exercise(), timeout=2))


def test_complete_stream_assembles_the_draft_and_preserves_cpu_options(monkeypatch):
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        body = '\n'.join(json.dumps(row) for row in [
            {"message": {"content": "complete "}, "done": False},
            {"message": {"content": "draft"}, "done": False},
            {"message": {"content": ""}, "done": True, "model": "fixture", "eval_count": 2},
        ])
        return httpx.Response(200, text=body)

    transport_client(monkeypatch, handler)
    token = request_cancelled.set(threading.Event())
    try:
        result = OllamaEngine().complete([{"role": "user", "content": "fixture"}])
    finally:
        request_cancelled.reset(token)
    assert result.text == "complete draft"
    assert result.usage["output_tokens"] == 2
    assert payloads[0]["stream"] is True and payloads[0]["options"]["num_gpu"] == 0


def test_stream_timeout_is_bounded_even_when_no_tokens_arrive(monkeypatch):
    async def handler(request):
        await asyncio.Event().wait()

    transport_client(monkeypatch, handler)

    async def exercise():
        with pytest.raises(ModelEngineError, match="timed out"):
            await OllamaEngine(OllamaSettings(timeout_seconds=0.05))._cancelable_chat({}, threading.Event())

    asyncio.run(asyncio.wait_for(exercise(), timeout=2))


def test_disconnect_marks_only_its_own_request_and_does_not_cache_partial_work(monkeypatch):
    monkeypatch.setenv("KOPI_WARM_UP", "0")

    class Graph:
        calls = 0
        events = []

        def stream(self, *args, **kwargs):
            self.calls += 1
            stopped = request_cancelled.get()
            self.events.append(stopped)
            yield {"query_router": {"trace": ["query_router:policy"]}}
            if self.calls == 1:
                assert stopped.wait(2), "The disconnected request was not cancelled"
            yield {"output": {"response": ChatResponse(status="answered", mode="demo", message="Complete fixture answer.")}}

    graph = Graph()
    app = create_app(graph)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/chat/stream")

    async def exercise():
        request = ChatRequest(message="fixture")
        response = await endpoint(request)
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
        assert graph.events[0].is_set()
        await asyncio.sleep(0.1)
        second = await endpoint(request)
        lines = [line async for line in second.body_iterator]
        assert any("Complete fixture answer" in line for line in lines)
        assert graph.calls == 2  # The aborted result was not cached.
        third = await endpoint(request)
        assert [line async for line in third.body_iterator]
        assert graph.calls == 2  # The fully completed result can be cached.
        assert graph.events[0] is not graph.events[1]

    asyncio.run(asyncio.wait_for(exercise(), timeout=3))
