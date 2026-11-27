from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import PropertyType
from app.schemas.common import PhoneNumber
from app.schemas.property import PropertyPublic


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)


class CollectedProfile(BaseModel):
    """What the chatbot has learned so far. The client echoes it back on every request, so the
    server stays stateless."""

    name: str | None = Field(default=None, max_length=120)
    phone: PhoneNumber | None = None
    email: EmailStr | None = None
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    preferred_location: str | None = Field(default=None, max_length=120)
    property_type: PropertyType | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    purchase_timeline_days: int | None = Field(default=None, ge=0, le=3650)
    urgency: str | None = Field(default=None, pattern="^(low|medium|high)$")
    lead_saved: bool = False


class ChatRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=30)
    collected: CollectedProfile = Field(default_factory=CollectedProfile)
    consent_to_contact: bool = Field(
        default=False, description="The visitor agreed that the sales team may contact them"
    )

    @model_validator(mode="after")
    def _last_is_user(self) -> ChatRequest:
        if self.messages[-1].role != "user":
            raise ValueError("The last message must come from the user")
        return self


class ChatRecommendation(BaseModel):
    property: PropertyPublic
    match_score: float
    reasons: list[str]


class ChatResponse(BaseModel):
    reply: str
    collected: CollectedProfile
    recommendations: list[ChatRecommendation]
    lead_saved: bool
    mode: Literal["llm", "rules"]
    cited_property_ids: list[int]
