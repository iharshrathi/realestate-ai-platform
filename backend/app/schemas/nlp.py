from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import PropertyType


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ExtractedRequirements(BaseModel):
    """Structured customer requirement profile extracted from an unstructured message."""

    budget_min: int | None = None
    budget_max: int | None = None
    preferred_location: str | None = None
    property_type: PropertyType | None = None
    bedrooms: int | None = None
    purchase_timeline_days: int | None = None
    urgency: str | None = Field(default=None, pattern="^(low|medium|high)$")
    loan_preapproved: bool | None = None
    intent: str = "general_enquiry"
    intents: dict[str, int] = Field(default_factory=dict)  # intent -> keyword hits
    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    summary: str = ""
    method: str = "rules"  # "rules" or "rules+llm"

    def has_requirement_data(self) -> bool:
        return any(
            value is not None
            for value in (
                self.budget_min,
                self.budget_max,
                self.preferred_location,
                self.property_type,
                self.bedrooms,
                self.purchase_timeline_days,
            )
        )
