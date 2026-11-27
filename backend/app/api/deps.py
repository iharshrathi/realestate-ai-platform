"""FastAPI dependencies: database session, authentication and role-based access control."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Lead, User
from app.models.enums import UserRole
from app.services import lead_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{get_settings().api_prefix}/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    unauthorised = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorised from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorised
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """Dependency factory: allow only the given roles."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do that")
        return user

    return checker


AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
ManagerUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


def get_accessible_lead(lead_id: int, db: DbSession, user: CurrentUser) -> Lead:
    """Resolve ``{lead_id}`` in the path, enforcing per-role lead visibility."""
    return lead_service.get_lead_for_user(db, lead_id, user)


AccessibleLead = Annotated[Lead, Depends(get_accessible_lead)]
