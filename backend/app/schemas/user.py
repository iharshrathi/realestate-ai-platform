from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.models.enums import UserRole
from app.schemas.common import ORMModel


def _check_password(value: str) -> str:
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10)
    role: UserRole = UserRole.AGENT

    _password_limit = field_validator("password")(_check_password)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)

    _password_limit = field_validator("password")(
        lambda v: _check_password(v) if v is not None else v
    )


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserBrief(ORMModel):
    id: int
    full_name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
