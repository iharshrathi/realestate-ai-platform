from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AdminUser, DbSession, ManagerUser
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _: ManagerUser) -> list[UserOut]:
    """List staff (managers need this to assign leads)."""
    return [UserOut.model_validate(u) for u in user_service.list_users(db)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: DbSession, _: AdminUser) -> UserOut:
    return UserOut.model_validate(user_service.create_user(db, data))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: DbSession, _: AdminUser) -> UserOut:
    return UserOut.model_validate(user_service.update_user(db, user_id, data))
