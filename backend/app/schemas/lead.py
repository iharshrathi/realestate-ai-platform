from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import LeadSource, LeadStatus, ScoreBand
from app.schemas.common import ORMModel, PhoneNumber
from app.schemas.prediction import PredictionOut
from app.schemas.requirement import RequirementIn, RequirementOut
from app.schemas.user import UserBrief


class LeadCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: PhoneNumber | None = None
    source: LeadSource
    campaign_id: int | None = None
    assigned_to_id: int | None = None
    requirement: RequirementIn | None = None
    message: str | None = Field(
        default=None,
        max_length=5000,
        description="Original enquiry text (stored as an interaction)",
    )

    @model_validator(mode="after")
    def _needs_contact(self) -> LeadCreate:
        if not self.email and not self.phone:
            raise ValueError("Provide at least an email or a phone number")
        return self


class LeadUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: PhoneNumber | None = None
    source: LeadSource | None = None
    status: LeadStatus | None = None
    campaign_id: int | None = None
    assigned_to_id: int | None = None


class LeadOut(ORMModel):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    source: LeadSource
    status: LeadStatus
    campaign_id: int | None
    assigned_to: UserBrief | None
    latest_probability: float | None
    latest_band: ScoreBand | None
    is_synthetic: bool
    created_at: datetime
    converted_at: datetime | None


class LeadDetail(LeadOut):
    requirement: RequirementOut | None = None
    latest_prediction: PredictionOut | None = None
    interaction_count: int = 0


class LeadQuery(BaseModel):
    """Query-string filters for the lead list (validated by FastAPI)."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=100, description="name / email / phone search")
    status: LeadStatus | None = None
    source: LeadSource | None = None
    band: ScoreBand | None = None
    assigned_to_id: int | None = None
    created_from: date | None = None
    created_to: date | None = None
    sort_by: Literal["created_at", "full_name", "latest_probability", "status"] = "created_at"
    order: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
