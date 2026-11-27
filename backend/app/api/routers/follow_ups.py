from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.follow_up import FollowUpOut, FollowUpQuery, FollowUpUpdate
from app.services import followup_service

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


@router.get("", response_model=Page[FollowUpOut])
def list_follow_ups(
    query: Annotated[FollowUpQuery, Query()], db: DbSession, user: CurrentUser
) -> Page[FollowUpOut]:
    """Pending (draft/approved) or completed follow-ups, most urgent first."""
    items, total = followup_service.list_follow_ups(db, user, query)
    return Page[FollowUpOut](
        items=[FollowUpOut.model_validate(i) for i in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


@router.patch("/{follow_up_id}", response_model=FollowUpOut)
def edit_follow_up(
    follow_up_id: int, data: FollowUpUpdate, db: DbSession, user: CurrentUser
) -> FollowUpOut:
    follow_up = followup_service.get_follow_up_for_user(db, follow_up_id, user)
    return FollowUpOut.model_validate(followup_service.update_follow_up(db, follow_up, data))


@router.post("/{follow_up_id}/approve", response_model=FollowUpOut)
def approve_follow_up(follow_up_id: int, db: DbSession, user: CurrentUser) -> FollowUpOut:
    """Human approval gate: drafts (AI-written or not) become sendable only after this call."""
    follow_up = followup_service.get_follow_up_for_user(db, follow_up_id, user)
    return FollowUpOut.model_validate(followup_service.approve(db, follow_up, user))


@router.post("/{follow_up_id}/reject", response_model=FollowUpOut)
def reject_follow_up(follow_up_id: int, db: DbSession, user: CurrentUser) -> FollowUpOut:
    follow_up = followup_service.get_follow_up_for_user(db, follow_up_id, user)
    return FollowUpOut.model_validate(followup_service.reject(db, follow_up))


@router.post("/{follow_up_id}/complete", response_model=FollowUpOut)
def complete_follow_up(follow_up_id: int, db: DbSession, user: CurrentUser) -> FollowUpOut:
    """Record that a human sent the (approved) message or made the call."""
    follow_up = followup_service.get_follow_up_for_user(db, follow_up_id, user)
    return FollowUpOut.model_validate(followup_service.complete(db, follow_up, user))
