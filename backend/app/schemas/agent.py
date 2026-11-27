from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AgentRunStatus
from app.schemas.common import ORMModel
from app.schemas.follow_up import FollowUpOut
from app.schemas.nlp import ExtractedRequirements
from app.schemas.prediction import PredictionOut
from app.schemas.property import Recommendation


class AgentRunRequest(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional new customer message to analyse. Defaults to the latest inbound text.",
    )


class AgentStep(BaseModel):
    agent: str
    action: str
    status: AgentRunStatus
    duration_ms: int
    error: str | None = None


class LeadAgentResult(BaseModel):
    run_id: str
    lead_id: int
    requirement: ExtractedRequirements | None
    prediction: PredictionOut | None
    recommendations: list[Recommendation]
    follow_up: FollowUpOut | None
    steps: list[AgentStep]
    errors: list[str]
    note: str = (
        "The follow-up is a DRAFT. Nothing is sent until a human approves it. "
        "Lead status, assignment and contact details are never changed by agents."
    )


class AgentLogOut(ORMModel):
    id: int
    run_id: str
    agent_name: str
    action: str
    lead_id: int | None
    triggered_by_id: int | None
    status: AgentRunStatus
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]
    error: str | None
    duration_ms: int
    created_at: datetime
