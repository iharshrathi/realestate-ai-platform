from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import PropertyType, RequirementSource
from app.schemas.common import ORMModel

URGENCY_PATTERN = "^(low|medium|high)$"


class RequirementIn(BaseModel):
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    preferred_location: str | None = Field(default=None, max_length=120)
    property_type: PropertyType | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    purchase_timeline_days: int | None = Field(default=None, ge=0, le=3650)
    urgency: str | None = Field(default=None, pattern=URGENCY_PATTERN)
    intent: str | None = Field(default=None, max_length=40)
    loan_preapproved: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _budget_ordered(self) -> RequirementIn:
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class RequirementOut(ORMModel):
    id: int
    lead_id: int
    budget_min: int | None
    budget_max: int | None
    preferred_location: str | None
    property_type: PropertyType | None
    bedrooms: int | None
    purchase_timeline_days: int | None
    urgency: str | None
    intent: str | None
    loan_preapproved: bool | None
    notes: str | None
    source: RequirementSource
    created_at: datetime
