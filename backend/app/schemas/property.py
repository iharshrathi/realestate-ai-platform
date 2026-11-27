from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import PropertyStatus, PropertyType
from app.schemas.common import ORMModel


class PropertyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    location: str = Field(min_length=2, max_length=120)
    property_type: PropertyType
    price_inr: int = Field(gt=0)
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    area_sqft: int | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=4000)
    amenities: list[str] = Field(default_factory=list, max_length=30)
    status: PropertyStatus = PropertyStatus.AVAILABLE


class PropertyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    location: str | None = Field(default=None, min_length=2, max_length=120)
    property_type: PropertyType | None = None
    price_inr: int | None = Field(default=None, gt=0)
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    area_sqft: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=4000)
    amenities: list[str] | None = Field(default=None, max_length=30)
    status: PropertyStatus | None = None


class PropertyOut(ORMModel):
    id: int
    title: str
    location: str
    property_type: PropertyType
    price_inr: int
    bedrooms: int | None
    area_sqft: int | None
    description: str
    amenities: list[str]
    status: PropertyStatus
    is_synthetic: bool
    created_at: datetime


class PropertyPublic(ORMModel):
    """The subset of a listing that is safe to show to anonymous website visitors."""

    id: int
    title: str
    location: str
    property_type: PropertyType
    price_inr: int
    bedrooms: int | None
    area_sqft: int | None
    amenities: list[str]


class Recommendation(BaseModel):
    property: PropertyOut
    match_score: float = Field(ge=0, le=1)
    reasons: list[str]
