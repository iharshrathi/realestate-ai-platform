"""AI endpoints: model info, NLP analysis, the public chatbot and agent workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.agents.insights_graph import run_sales_intelligence
from app.agents.lead_graph import run_lead_pipeline
from app.agents.runtime import AgentContext
from app.api.deps import AccessibleLead, CurrentUser, DbSession, ManagerUser
from app.core.rate_limit import chat_rate_limit
from app.models import AgentLog, Property
from app.schemas.agent import AgentLogOut, AgentRunRequest, LeadAgentResult
from app.schemas.analytics import Forecast, InsightsResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import Page
from app.schemas.nlp import AnalyzeRequest, ExtractedRequirements
from app.schemas.prediction import ModelInfo
from app.services import chatbot_service, nlp_service, scoring_service

router = APIRouter(tags=["ai"])


@router.get("/model", response_model=ModelInfo)
def model_info(_: CurrentUser) -> ModelInfo:
    """Metadata, evaluation metrics and feature importance of the lead-scoring model."""
    return scoring_service.model_info()


@router.post("/nlp/analyze", response_model=ExtractedRequirements)
def analyze_text(data: AnalyzeRequest, db: DbSession, _: CurrentUser) -> ExtractedRequirements:
    """Extract budget, location, property type, urgency and intent from a message (no writes)."""
    locations = list(db.scalars(select(Property.location).distinct()))
    return nlp_service.extract_requirements(data.text, locations)


@router.post(
    "/chatbot/message", response_model=ChatResponse, dependencies=[Depends(chat_rate_limit)]
)
def chatbot_message(data: ChatRequest, db: DbSession) -> ChatResponse:
    """Public, rate-limited website chatbot (RAG over verified listings).

    Stateless: the client sends the conversation and the profile collected so far.
    """
    return chatbot_service.handle_message(db, data)


@router.post("/agents/leads/{lead_id}/run", response_model=LeadAgentResult)
def run_lead_agents(
    data: AgentRunRequest, lead: AccessibleLead, db: DbSession, user: CurrentUser
) -> LeadAgentResult:
    """Run qualification -> scoring -> recommendation -> follow-up drafting for one lead."""
    return run_lead_pipeline(AgentContext(db=db, user=user), lead, data.message)


class _InsightsRun(InsightsResponse):
    forecast: Forecast | None = None


@router.post("/agents/sales-intelligence/run", response_model=_InsightsRun)
def run_sales_intelligence_agent(db: DbSession, user: ManagerUser) -> _InsightsRun:
    """Run the Sales Intelligence Agent (read-only analytics + insights)."""
    response, forecast = run_sales_intelligence(AgentContext(db=db, user=user))
    return _InsightsRun(**response.model_dump(), forecast=forecast)


@router.get("/agents/logs", response_model=Page[AgentLogOut])
def agent_logs(
    db: DbSession,
    _: ManagerUser,
    run_id: Annotated[str | None, Query(max_length=36)] = None,
    lead_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AgentLogOut]:
    """Audit trail of agent decisions and actions."""
    stmt = select(AgentLog)
    if run_id:
        stmt = stmt.where(AgentLog.run_id == run_id)
    if lead_id:
        stmt = stmt.where(AgentLog.lead_id == lead_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AgentLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[AgentLogOut](
        items=[AgentLogOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
