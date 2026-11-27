from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import login_rate_limit
from app.core.security import create_access_token
from app.schemas.user import Token, UserOut
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token, dependencies=[Depends(login_rate_limit)])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    """Exchange email + password for a bearer token (OAuth2 password flow; `username` = email)."""
    user = user_service.authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
