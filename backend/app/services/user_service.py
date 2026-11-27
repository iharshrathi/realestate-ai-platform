from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate, UserUpdate


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalars(select(User).where(func.lower(User.email) == email.lower())).first()
    # Always run one bcrypt comparison so response time does not reveal which emails exist.
    password_ok = verify_password(password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        return None
    return user


def create_user(db: Session, data: UserCreate) -> User:
    if db.scalar(select(User.id).where(func.lower(User.email) == data.email.lower())):
        raise ConflictError("A user with this email already exists")
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, data: UserUpdate) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    changes = data.model_dump(exclude_unset=True)
    if password := changes.pop("password", None):
        user.hashed_password = hash_password(password)
    for field, value in changes.items():
        if value is not None:
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.full_name)))
