from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from .advisor import DemoAdvisor
from .orchestration.graph import build_stage1_graph
from .schemas import ChatRequest, ChatResponse, GraphState
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
    gateway = build_stage1_graph()

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": "demo"}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        gateway_input = {
            "message": request.message,
            "user_age": request.profile.age,
            "income": request.profile.household_income,
            "citizenship": request.profile.citizenship,
            "town": request.price_filters.town if request.price_filters else None,
            "flat_type": request.price_filters.flat_type if request.price_filters else None,
        }
        gateway_state = GraphState.model_validate(
            gateway.invoke(gateway_input)
        )
        if gateway_state.status == "clarify":
            return ChatResponse(
                status="clarifying",
                message=gateway_state.response or "More information is required.",
                trace=["gateway:clarify"],
            )
        if gateway_state.status == "abstain" and "demo" not in request.message.casefold():
            return ChatResponse(
                status="abstained",
                message=gateway_state.response or "I cannot answer that request.",
                trace=["gateway:abstain"],
            )

        profile = request.profile.model_copy(update={
            "age": gateway_state.user_age or request.profile.age,
            "household_income": float(gateway_state.income)
            if gateway_state.income is not None
            else request.profile.household_income,
            "citizenship": gateway_state.citizenship or request.profile.citizenship,
        })
        request = request.model_copy(update={"profile": profile})
        return run_request(workflow, request)

    return application


app = create_app()
