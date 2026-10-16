"""FastAPI entry point. All behaviour lives in graph.py."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from .graph import build_graph, run_chat
from .schemas import ChatRequest, ChatResponse


def create_app(graph=None) -> FastAPI:
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Demo policy fixtures only; the resale database is not connected.",
    )
    graph = graph if graph is not None else build_graph()

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": "demo"}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return run_chat(graph, request)

    return application


app = create_app()
