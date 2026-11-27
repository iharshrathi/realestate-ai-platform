from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.analytics import (
    ChannelStats,
    Forecast,
    InsightsResponse,
    MonthlyPoint,
    Overview,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=Overview)
def overview(db: DbSession, user: CurrentUser) -> Overview:
    """Dashboard KPIs, scoped to the leads the current user may see."""
    return analytics_service.overview(db, user)


@router.get("/monthly", response_model=list[MonthlyPoint])
def monthly(
    db: DbSession, user: ManagerUser, months: Annotated[int, Query(ge=1, le=36)] = 12
) -> list[MonthlyPoint]:
    """Monthly lead and conversion counts, split by acquisition channel."""
    return analytics_service.monthly(db, user, months)


@router.get("/channels", response_model=list[ChannelStats])
def channels(db: DbSession, user: ManagerUser) -> list[ChannelStats]:
    """Marketing-channel comparison: volume, conversion rate, lead quality and cost."""
    return analytics_service.channels(db, user)


@router.get("/forecast", response_model=Forecast)
def forecast(db: DbSession, user: ManagerUser) -> Forecast:
    """Expected conversions from open leads plus a simple next-month trend."""
    return analytics_service.forecast(db, user)


@router.get("/insights", response_model=InsightsResponse)
def insights(db: DbSession, user: ManagerUser) -> InsightsResponse:
    """Rule-generated, number-backed business insights (optionally summarised by an LLM)."""
    return analytics_service.insights_with_narrative(db, user)
