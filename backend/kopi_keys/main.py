"""FastAPI entry point. All behaviour lives in graph.py."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from .components.policy_retrieval import SnapshotPolicyRetriever
from .components.price_query import SqlitePriceTool
from .graph import build_graph, run_chat
from .schemas import ChatRequest, ChatResponse


def create_app(graph=None) -> FastAPI:
    mode = "snapshot" if graph is None else "demo"
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Policy passages from the ACTIVE snapshot (keyword search); resale prices from data/processed/hdb_prices.db when built.",
    )
    # Without a built database the SQLite tool reports "unavailable", like the old placeholder.
    graph = graph if graph is not None else build_graph(
        retriever=SnapshotPolicyRetriever(), price_tool=SqlitePriceTool(), data_mode="snapshot")

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": mode}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return run_chat(graph, request)

    return application


app = create_app()
