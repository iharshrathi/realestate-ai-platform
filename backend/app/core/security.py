"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.time import utcnow

# bcrypt only uses the first 72 bytes of a password; schemas enforce this limit.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:  # malformed hash or over-long password
        return False


# Used to spend the same time on unknown e-mails as on wrong passwords (timing side channel).
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(*, subject: str, role: str) -> str:
    settings = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a token. Raises ``jwt.InvalidTokenError`` on any problem."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
