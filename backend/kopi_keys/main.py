"""FastAPI entry point. All behaviour lives in graph.py."""

from dotenv import load_dotenv

load_dotenv()

import hashlib
import asyncio
import json
import os
import sqlite3
import threading
import uuid
from contextlib import suppress
from collections import OrderedDict
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .components.policy_retrieval import HybridPolicyRetriever
from .components.price_query import SqlitePriceTool
from .graph import build_graph, run_chat
from .llm import OllamaEngine
from .state import initial_state
from .schemas import ChatRequest, ChatResponse
from .cancellation import request_cancelled
from .feedback import (
    AnswerContext, ContextStore, FeedbackRequest, FeedbackStore, send_to_langsmith, tracing_enabled,
)


_ACTIVE = Path(__file__).resolve().parents[2] / "data" / "policy_snapshots" / "ACTIVE"


def _active_snapshot() -> str:
    try:
        return _ACTIVE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class ResponseCache:
    """Added 2026-10-17: repeated questions answered instantly.

    Keyed on the whole request (message, profile, history, filters) plus the ACTIVE snapshot,
    so a different profile or a new snapshot never reuses an answer. In memory only: cleared on
    restart, never written to disk. Model failures are not cached. KOPI_RESPONSE_CACHE=0 turns it off.
    """

    def __init__(self, size: int):
        self.size, self._items, self._lock = size, OrderedDict(), threading.Lock()

    @staticmethod
    def key(request: ChatRequest) -> str:
        snapshot = _active_snapshot()
        return hashlib.sha256(f"{snapshot}\n{request.model_dump_json()}".encode()).hexdigest()

    def get(self, key: str) -> ChatResponse | None:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        return None

    def put(self, key: str, response: ChatResponse) -> None:
        if self.size <= 0 or any("engine" in step for step in response.trace):
            return
        with self._lock:
            self._items[key] = response
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)


def _warm_up() -> None:
    try:
        OllamaEngine().for_policy({}).warm_up()
    except Exception:  # Ollama not running yet: the first question loads the model instead
        pass


def create_app(graph=None) -> FastAPI:
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Policy passages from the ACTIVE snapshot (hybrid keyword + vector search); resale prices from data/processed/hdb_prices.db when built.",
    )
    # Without a built database the SQLite tool reports "unavailable", like the old placeholder.
    if graph is None:
        graph = build_graph(retriever=HybridPolicyRetriever(), price_tool=SqlitePriceTool())
        if os.getenv("KOPI_WARM_UP", "1") != "0":
            threading.Thread(target=_warm_up, daemon=True).start()
    cache = ResponseCache(int(os.getenv("KOPI_RESPONSE_CACHE", "200")))
    # Feedback (added 2026-11-07) is recorded for human review only; it never reaches the graph.
    contexts, feedback_store = ContextStore(), FeedbackStore()

    def new_run_id() -> str:
        return str(uuid.uuid4())

    def stamp_new(response: ChatResponse, run_id: str) -> ChatResponse:
        """A freshly generated answer: its message_id is the root trace run id."""
        return response.model_copy(update={
            "message_id": run_id, "langsmith_run_id": run_id if tracing_enabled() else None,
        })

    def deliver(request: ChatRequest, response: ChatResponse, cached: bool) -> ChatResponse:
        """Cache hits get a new message_id but keep the original answer's trace id."""
        if cached:
            response = response.model_copy(update={"message_id": new_run_id()})
        contexts.remember(response.message_id, AnswerContext(
            question=request.message, answer=response.message, route=response.route,
            snapshot=_active_snapshot() or None, langsmith_run_id=response.langsmith_run_id,
        ))
        return response

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": getattr(graph, "evidence_mode", "demo")}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        key = cache.key(request)
        response = cache.get(key)
        if response is not None:
            return deliver(request, response, cached=True)
        run_id = new_run_id()
        response = stamp_new(run_chat(graph, request, run_id=run_id), run_id)
        cache.put(key, response)
        return deliver(request, response, cached=False)

    @application.post("/feedback")
    def feedback(item: FeedbackRequest, background: BackgroundTasks) -> dict:
        """Write-only: records a rating for human review. There is no endpoint that reads it back."""
        context = contexts.get(item.message_id)
        try:
            first = feedback_store.save(item, context)
        except (OSError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Feedback could not be recorded.") from None
        # The trace id only ever comes from this server's record of the answer. Unknown message
        # (for example after a restart): saved locally, and LangSmith is not called at all.
        if context is not None:
            background.add_task(send_to_langsmith, context.langsmith_run_id, item.message_id, item.rating,
                                item.reason, item.comment, first)
        return {"status": "recorded"}

    @application.post("/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        """Added 2026-10-17: the same answer as /chat, as newline-delimited JSON.
        One {"step": "<graph node>", "trace": [...]} line as each step finishes, then {"response": {...}}.
        Lets the UI show real progress during the 40-60 s model step."""
        key = cache.key(request)

        async def lines():
            cancelled = threading.Event()
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def send(item):
                if not cancelled.is_set():
                    loop.call_soon_threadsafe(queue.put_nowait, item)

            def produce():
                token = request_cancelled.set(cancelled)
                try:
                    for line in graph_lines(cancelled):
                        if cancelled.is_set():
                            break
                        send(line)
                except Exception as error:
                    send(error)
                finally:
                    request_cancelled.reset(token)
                    send(None)

            worker = asyncio.create_task(asyncio.to_thread(produce))
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield item
            finally:
                cancelled.set()
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

        def graph_lines(cancelled):
            cached = cache.get(key)
            if cached is not None:
                yield json.dumps({"step": "cache"}) + "\n"
                cached = deliver(request, cached, cached=True)
                yield json.dumps({"response": cached.model_dump(mode="json")}) + "\n"
                return
            final = None
            run_id = new_run_id()
            for update in graph.stream(initial_state(request), config={"recursion_limit": 50, "run_id": run_id},
                                       stream_mode="updates"):
                if cancelled.is_set():
                    return
                for node, values in update.items():
                    trace = values.get("trace", []) if isinstance(values, dict) else []
                    yield json.dumps({"step": node, "trace": trace}) + "\n"
                    if isinstance(values, dict) and values.get("response") is not None:
                        final = values["response"]
            response = final if isinstance(final, ChatResponse) else ChatResponse.model_validate(final)
            if cancelled.is_set():
                return
            response = stamp_new(response, run_id)
            cache.put(key, response)
            response = deliver(request, response, cached=False)
            yield json.dumps({"response": response.model_dump(mode="json")}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    return application


app = create_app()
