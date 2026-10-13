from fastapi import FastAPI

from .advisor import DemoAdvisor
from .schemas import ChatRequest, ChatResponse
from .tools.policy import DemoPolicyRetriever
from .tools.price import UnconfiguredPriceTool
from .workflow import build_workflow, run_request


def create_app(graph=None) -> FastAPI:
    application = FastAPI(
        title="Kopi & Keys",
        version="0.1.0",
        description="Backend foundation. Demo fixtures only; official data and LLM inference are not connected.",
    )
    workflow = graph if graph is not None else build_workflow(
        DemoAdvisor(), DemoPolicyRetriever(), UnconfiguredPriceTool(),
    )

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": "demo"}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return run_request(workflow, request)

    return application


app = create_app()
