from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.core.errors import ConflictError, NotFoundError
from app.models import MarketingCampaign
from app.schemas.campaign import CampaignCreate, CampaignOut, CampaignUpdate

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignOut])
def list_campaigns(db: DbSession, _: CurrentUser) -> list[CampaignOut]:
    rows = db.scalars(select(MarketingCampaign).order_by(MarketingCampaign.start_date.desc()))
    return [CampaignOut.model_validate(c) for c in rows]


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(data: CampaignCreate, db: DbSession, _: ManagerUser) -> CampaignOut:
    if db.scalar(select(MarketingCampaign.id).where(MarketingCampaign.name == data.name)):
        raise ConflictError("A campaign with this name already exists")
    campaign = MarketingCampaign(**data.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: int, data: CampaignUpdate, db: DbSession, _: ManagerUser
) -> CampaignOut:
    campaign = db.get(MarketingCampaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(campaign, field, value)
    db.commit()
    db.refresh(campaign)
    return CampaignOut.model_validate(campaign)
