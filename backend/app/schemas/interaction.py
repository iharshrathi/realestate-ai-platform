from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import InteractionDirection, InteractionType
from app.schemas.common import ORMModel


class InteractionCreate(BaseModel):
    type: InteractionType
    direction: InteractionDirection | None = None  # inferred from type when omitted
    content: str = Field(default="", max_length=5000)
    occurred_at: datetime | None = None


class InteractionOut(ORMModel):
    id: int
    lead_id: int
    type: InteractionType
    direction: InteractionDirection
    content: str
    occurred_at: datetime
    created_by_id: int | None
