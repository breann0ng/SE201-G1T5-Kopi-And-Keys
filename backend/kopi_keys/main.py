import os
from pathlib import Path

from fastapi import FastAPI

from .advisor import DemoAdvisor
from .schemas import ChatRequest, ChatResponse
from .tools.policy import DemoPolicyRetriever
from .tools.price import SqlitePriceTool
from .workflow import build_workflow, run_request

REPO_ROOT = Path(__file__).resolve().parents[2]


def resale_db_path() -> Path:
    # RESALE_DB_PATH may be absolute or relative to the repository root.
    path = Path(os.environ.get("RESALE_DB_PATH", "data/processed/resale.db"))
    return path if path.is_absolute() else REPO_ROOT / path


def create_app(graph=None) -> FastAPI:
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Demo Advisor and policy fixtures; price benchmarks use the local resale database if built.",
    )
    workflow = graph if graph is not None else build_workflow(
        DemoAdvisor(), DemoPolicyRetriever(), SqlitePriceTool(resale_db_path()),
    )

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": "demo"}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return run_request(workflow, request)

    return application


app = create_app()
