"""FastAPI entry point. All behaviour lives in graph.py."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from .components.policy_retrieval import HybridPolicyRetriever
from .components.price_query import SqlitePriceTool
from .graph import build_graph, run_chat
from .schemas import ChatRequest, ChatResponse


def create_app(graph=None) -> FastAPI:
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Policy passages from the ACTIVE snapshot (hybrid keyword + vector search); resale prices from data/processed/hdb_prices.db when built.",
    )
    # Without a built database the SQLite tool reports "unavailable", like the old placeholder.
    graph = graph if graph is not None else build_graph(
        retriever=HybridPolicyRetriever(), price_tool=SqlitePriceTool())

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": getattr(graph, "evidence_mode", "demo")}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return run_chat(graph, request)

    return application


app = create_app()
