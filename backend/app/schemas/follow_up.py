from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FollowUpAuthor, FollowUpChannel, FollowUpStatus, Priority
from app.schemas.common import ORMModel
from app.schemas.property import PropertyOut


class FollowUpCreate(BaseModel):
    channel: FollowUpChannel
    message: str = Field(default="", max_length=4000)
    priority: Priority = Priority.MEDIUM
    due_at: datetime | None = None


class FollowUpUpdate(BaseModel):
    channel: FollowUpChannel | None = None
    message: str | None = Field(default=None, max_length=4000)
    priority: Priority | None = None
    due_at: datetime | None = None


class FollowUpOut(ORMModel):
    id: int
    lead_id: int
    lead_name: str
    channel: FollowUpChannel
    message: str
    template_key: str | None
    priority: Priority
    rationale: str | None
    status: FollowUpStatus
    generated_by: FollowUpAuthor
    due_at: datetime | None
    approved_by_id: int | None
    approved_at: datetime | None
    sent_at: datetime | None
    created_at: datetime


class FollowUpQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: Literal["pending", "completed", "rejected", "all"] = "pending"
    priority: Priority | None = None
    lead_id: int | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SuggestedFollowUp(BaseModel):
    """Result of the follow-up assistant: a saved *draft* plus the context it used."""

    follow_up: FollowUpOut
    template_key: str
    priority_reasons: list[str]
    recommended_properties: list[PropertyOut]
    generated_by: FollowUpAuthor
