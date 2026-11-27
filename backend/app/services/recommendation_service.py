"""Property recommendations: structured matching (budget, location, type, bedrooms) plus an
optional free-text relevance bonus from the retrieval index.

Technique: deterministic scoring, no ML and no LLM, so every recommendation is explainable.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CustomerRequirement, Property
from app.models.enums import PropertyStatus, PropertyType
from app.schemas.property import PropertyOut, Recommendation
from app.services.rag_service import property_index

# Importance of each criterion. Criteria the customer did not specify are skipped and the
# remaining weights are re-normalised, so a customer who only gave a budget is not penalised.
WEIGHTS = {"budget": 0.40, "location": 0.30, "type": 0.20, "bedrooms": 0.10}
TEXT_BONUS = 0.10
OVER_BUDGET_TOLERANCE = 0.15  # listings up to 15% above budget still get partial credit


@dataclass(frozen=True)
class Criteria:
    budget_min: int | None = None
    budget_max: int | None = None
    location: str | None = None
    property_type: PropertyType | None = None
    bedrooms: int | None = None
    free_text: str | None = None

    def is_empty(self) -> bool:
        return not any(
            (self.budget_min, self.budget_max, self.location, self.property_type, self.bedrooms)
        )


def criteria_from_requirement(
    requirement: CustomerRequirement | None, free_text: str | None = None
) -> Criteria:
    if requirement is None:
        return Criteria(free_text=free_text)
    return Criteria(
        budget_min=requirement.budget_min,
        budget_max=requirement.budget_max,
        location=requirement.preferred_location,
        property_type=requirement.property_type,
        bedrooms=requirement.bedrooms,
        free_text=free_text,
    )


def _budget_score(prop: Property, criteria: Criteria) -> tuple[float, str]:
    price, low, high = prop.price_inr, criteria.budget_min, criteria.budget_max
    if high is not None and price > high:
        overshoot = (price - high) / high
        if overshoot <= OVER_BUDGET_TOLERANCE:
            return 0.5 * (1 - overshoot / OVER_BUDGET_TOLERANCE), f"{overshoot:.0%} above budget"
        return 0.0, "above budget"
    if low is not None and price < low:
        return 0.6, "below your minimum budget"
    return 1.0, "within budget"


def score_property(
    prop: Property, criteria: Criteria, text_score: float | None = None
) -> Recommendation:
    """Score one listing. ``text_score`` (0-1) is only passed when a free-text query exists."""
    earned = total = 0.0
    reasons: list[str] = []

    if criteria.budget_min is not None or criteria.budget_max is not None:
        score, reason = _budget_score(prop, criteria)
        earned, total = earned + WEIGHTS["budget"] * score, total + WEIGHTS["budget"]
        reasons.append(reason)
    if criteria.location:
        match = prop.location.lower() == criteria.location.lower()
        earned, total = earned + (WEIGHTS["location"] if match else 0), total + WEIGHTS["location"]
        reasons.append(f"in {prop.location}" if match else f"different area ({prop.location})")
    if criteria.property_type:
        match = prop.property_type == criteria.property_type
        earned, total = earned + (WEIGHTS["type"] if match else 0), total + WEIGHTS["type"]
        reasons.append(
            f"{prop.property_type.value}" if match else f"is a {prop.property_type.value}"
        )
    if criteria.bedrooms is not None and prop.bedrooms is not None:
        gap = abs(prop.bedrooms - criteria.bedrooms)
        credit = 1.0 if gap == 0 else 0.5 if gap == 1 else 0.0
        earned, total = earned + WEIGHTS["bedrooms"] * credit, total + WEIGHTS["bedrooms"]
        reasons.append(
            f"{prop.bedrooms} BHK" + ("" if gap == 0 else f" (wanted {criteria.bedrooms})")
        )

    structured = earned / total if total else 0.0
    if text_score is None:
        score = structured
    elif total:
        score = structured + TEXT_BONUS * min(text_score, 1.0)  # text can only add
    else:  # nothing structured to match on: rank purely by text relevance
        score = min(text_score, 1.0)
    score = min(score, 1.0)
    return Recommendation(
        property=PropertyOut.model_validate(prop), match_score=round(score, 3), reasons=reasons
    )


def passes_hard_filters(prop: Property, criteria: Criteria) -> bool:
    """Listings that must never be shown, whatever their score.

    * The customer's budget ceiling (plus a small tolerance) is respected.
    * When a location and/or property type was requested, the listing must match at least one;
      matching on budget alone would surface irrelevant listings (a plot for someone who asked
      for a villa in another area).
    """
    if criteria.budget_max and prop.price_inr > criteria.budget_max * (1 + OVER_BUDGET_TOLERANCE):
        return False
    checks = []
    if criteria.location:
        checks.append(prop.location.lower() == criteria.location.lower())
    if criteria.property_type:
        checks.append(prop.property_type == criteria.property_type)
    return not checks or any(checks)


def recommend(
    db: Session, criteria: Criteria, *, limit: int = 5, min_score: float = 0.3
) -> list[Recommendation]:
    """Rank available listings for the given criteria."""
    listings = list(db.scalars(select(Property).where(Property.status == PropertyStatus.AVAILABLE)))
    text_scores: dict[int, float] = {}
    if criteria.free_text:
        text_scores = {
            h.property.id: h.score for h in property_index.search(db, criteria.free_text, k=20)
        }

    scored = [
        score_property(p, criteria, text_scores.get(p.id, 0.0) if criteria.free_text else None)
        for p in listings
        if passes_hard_filters(p, criteria)
    ]
    scored = [r for r in scored if r.match_score >= min_score]
    scored.sort(key=lambda r: (-r.match_score, r.property.price_inr))
    return scored[:limit]
