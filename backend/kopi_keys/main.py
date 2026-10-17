"""FastAPI entry point. All behaviour lives in graph.py."""

from dotenv import load_dotenv

load_dotenv()

import hashlib
import json
import os
import threading
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from .components.policy_retrieval import HybridPolicyRetriever
from .components.price_query import SqlitePriceTool
from .graph import build_graph, run_chat
from .llm import OllamaEngine
from .state import initial_state
from .schemas import ChatRequest, ChatResponse


_ACTIVE = Path(__file__).resolve().parents[2] / "data" / "policy_snapshots" / "ACTIVE"


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
        try:
            snapshot = _ACTIVE.read_text(encoding="utf-8").strip()
        except OSError:
            snapshot = ""
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

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": getattr(graph, "evidence_mode", "demo")}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        key = cache.key(request)
        response = cache.get(key)
        if response is None:
            response = run_chat(graph, request)
            cache.put(key, response)
        return response

    @application.post("/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        """Added 2026-10-17: the same answer as /chat, as newline-delimited JSON.
        One {"step": "<graph node>", "trace": [...]} line as each step finishes, then {"response": {...}}.
        Lets the UI show real progress during the 40-60 s model step."""
        key = cache.key(request)

        def lines():
            cached = cache.get(key)
            if cached is not None:
                yield json.dumps({"step": "cache"}) + "\n"
                yield json.dumps({"response": cached.model_dump(mode="json")}) + "\n"
                return
            final = None
            for update in graph.stream(initial_state(request), config={"recursion_limit": 50},
                                       stream_mode="updates"):
                for node, values in update.items():
                    trace = values.get("trace", []) if isinstance(values, dict) else []
                    yield json.dumps({"step": node, "trace": trace}) + "\n"
                    if isinstance(values, dict) and values.get("response") is not None:
                        final = values["response"]
            response = final if isinstance(final, ChatResponse) else ChatResponse.model_validate(final)
            cache.put(key, response)
            yield json.dumps({"response": response.model_dump(mode="json")}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    return application


app = create_app()
