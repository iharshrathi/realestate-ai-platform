from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.models.enums import LeadSource
from app.schemas.common import ORMModel


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    channel: LeadSource
    start_date: date
    end_date: date | None = None
    spend_inr: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates_ordered(self) -> CampaignCreate:
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    end_date: date | None = None
    spend_inr: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class CampaignOut(ORMModel):
    id: int
    name: str
    channel: LeadSource
    start_date: date
    end_date: date | None
    spend_inr: int
    notes: str | None
    is_synthetic: bool
