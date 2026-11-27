from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.deps import AccessibleLead, CurrentUser, DbSession, ManagerUser
from app.models import Lead, Prediction
from app.models.enums import RequirementSource
from app.schemas.common import Page
from app.schemas.follow_up import FollowUpCreate, FollowUpOut, SuggestedFollowUp
from app.schemas.interaction import InteractionCreate, InteractionOut
from app.schemas.lead import LeadCreate, LeadDetail, LeadOut, LeadQuery, LeadUpdate
from app.schemas.prediction import PredictionOut
from app.schemas.property import PropertyOut, Recommendation
from app.schemas.requirement import RequirementIn, RequirementOut
from app.services import followup_service, lead_service, scoring_service
from app.services.recommendation_service import criteria_from_requirement, recommend

router = APIRouter(prefix="/leads", tags=["leads"])


def _detail(db: DbSession, lead: Lead) -> LeadDetail:
    requirement = lead_service.current_requirement(db, lead.id)
    prediction = scoring_service.latest_prediction(db, lead.id)
    return LeadDetail.model_validate(lead).model_copy(
        update={
            "requirement": RequirementOut.model_validate(requirement) if requirement else None,
            "latest_prediction": PredictionOut.model_validate(prediction) if prediction else None,
            "interaction_count": len(lead.interactions),
        }
    )


# -------------------------------------------------------------------------------- leads
@router.get("", response_model=Page[LeadOut])
def list_leads(
    query: Annotated[LeadQuery, Query()], db: DbSession, user: CurrentUser
) -> Page[LeadOut]:
    """Search, filter, sort and paginate leads (agents only see their own + unassigned)."""
    items, total = lead_service.list_leads(db, user, query)
    return Page[LeadOut](
        items=[LeadOut.model_validate(i) for i in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


@router.post("", response_model=LeadDetail, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, db: DbSession, user: CurrentUser) -> LeadDetail:
    return _detail(db, lead_service.create_lead(db, data, user))


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead: AccessibleLead, db: DbSession) -> LeadDetail:
    return _detail(db, lead)


@router.patch("/{lead_id}", response_model=LeadDetail)
def update_lead(
    data: LeadUpdate, lead: AccessibleLead, db: DbSession, user: CurrentUser
) -> LeadDetail:
    return _detail(db, lead_service.update_lead(db, lead, data, user))


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead: AccessibleLead, db: DbSession, _: ManagerUser) -> Response:
    lead_service.delete_lead(db, lead)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- interactions
@router.get("/{lead_id}/interactions", response_model=list[InteractionOut])
def list_interactions(lead: AccessibleLead) -> list[InteractionOut]:
    """Lead activity history, newest first."""
    ordered = sorted(lead.interactions, key=lambda i: (i.occurred_at, i.id), reverse=True)
    return [InteractionOut.model_validate(i) for i in ordered]


@router.post(
    "/{lead_id}/interactions", response_model=InteractionOut, status_code=status.HTTP_201_CREATED
)
def add_interaction(
    data: InteractionCreate, lead: AccessibleLead, db: DbSession, user: CurrentUser
) -> InteractionOut:
    return InteractionOut.model_validate(lead_service.add_interaction(db, lead, data, user))


# ---------------------------------------------------------------------------- requirements
@router.get("/{lead_id}/requirements", response_model=list[RequirementOut])
def requirement_history(lead: AccessibleLead) -> list[RequirementOut]:
    return [RequirementOut.model_validate(r) for r in reversed(lead.requirements)]


@router.post(
    "/{lead_id}/requirements", response_model=RequirementOut, status_code=status.HTTP_201_CREATED
)
def add_requirement(data: RequirementIn, lead: AccessibleLead, db: DbSession) -> RequirementOut:
    """Record a new requirement profile (previous ones are kept as history)."""
    return RequirementOut.model_validate(
        lead_service.add_requirement(db, lead, data, RequirementSource.MANUAL)
    )


# ---------------------------------------------------------------------------- AI scoring
@router.post("/{lead_id}/score", response_model=PredictionOut)
def score_lead(lead: AccessibleLead, db: DbSession) -> PredictionOut:
    """Run the ML model for this lead and store the prediction (503 if no model is trained)."""
    return PredictionOut.model_validate(scoring_service.score_lead(db, lead))


@router.get("/{lead_id}/predictions", response_model=list[PredictionOut])
def prediction_history(lead: AccessibleLead, db: DbSession) -> list[PredictionOut]:
    rows = db.scalars(
        select(Prediction).where(Prediction.lead_id == lead.id).order_by(Prediction.id.desc())
    )
    return [PredictionOut.model_validate(r) for r in rows]


# -------------------------------------------------------------------------- recommendations
@router.get("/{lead_id}/recommendations", response_model=list[Recommendation])
def recommend_for_lead(
    lead: AccessibleLead, db: DbSession, limit: Annotated[int, Query(ge=1, le=10)] = 5
) -> list[Recommendation]:
    requirement = lead_service.current_requirement(db, lead.id)
    return recommend(db, criteria_from_requirement(requirement), limit=limit)


# ----------------------------------------------------------------------------- follow-ups
@router.get("/{lead_id}/follow-ups", response_model=list[FollowUpOut])
def lead_follow_ups(lead: AccessibleLead) -> list[FollowUpOut]:
    return [FollowUpOut.model_validate(f) for f in reversed(lead.follow_ups)]


@router.post(
    "/{lead_id}/follow-ups", response_model=FollowUpOut, status_code=status.HTTP_201_CREATED
)
def create_follow_up(
    data: FollowUpCreate, lead: AccessibleLead, db: DbSession, user: CurrentUser
) -> FollowUpOut:
    """Schedule a follow-up written by a human."""
    return FollowUpOut.model_validate(followup_service.create_manual(db, lead, data, user))


@router.post("/{lead_id}/follow-ups/suggest", response_model=SuggestedFollowUp)
def suggest_follow_up(lead: AccessibleLead, db: DbSession, user: CurrentUser) -> SuggestedFollowUp:
    """Ask the follow-up assistant for a personalised DRAFT. It is not sent until approved."""
    suggestion = followup_service.suggest_follow_up(db, lead, user)
    return SuggestedFollowUp(
        follow_up=FollowUpOut.model_validate(suggestion.follow_up),
        template_key=suggestion.template_key,
        priority_reasons=suggestion.priority_reasons,
        recommended_properties=[
            PropertyOut.model_validate(r.property) for r in suggestion.recommendations
        ],
        generated_by=suggestion.generated_by,
    )
