"""Shared fixtures.

Environment variables are set *before* the app is imported so that settings, the in-memory
SQLite engine and the model path all point at test resources.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="reai-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "sqlite://"
        ),  # set to run the suite on PostgreSQL
        "SECRET_KEY": "test-secret-key-test-secret-key-0123456789",
        "MODEL_PATH": str(_TMP_DIR / "lead_model.joblib"),
        "LLM_PROVIDER": "none",
        "RATE_LIMIT_GLOBAL_PER_MINUTE": "100000",
        "RATE_LIMIT_LOGIN_PER_MINUTE": "100000",
        "RATE_LIMIT_CHAT_PER_MINUTE": "100000",
        "SEED_PASSWORD": "TestPassw0rd!",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead, Property, User  # noqa: E402
from app.models.enums import LeadSource, LeadStatus, PropertyType, UserRole  # noqa: E402
from app.services.rag_service import property_index  # noqa: E402
from tests import factories  # noqa: E402

PASSWORD = "TestPassw0rd!"


@pytest.fixture(scope="session")
def trained_model() -> Path:
    """Train a small model once per test session (a few seconds)."""
    from ml.train import train_and_save

    path = Path(os.environ["MODEL_PATH"])
    train_and_save(output_path=path, n_samples=1500, quick=True, seed=3)
    return path


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limiter.reset()
    property_index.reset()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(subject=str(user.id), role=user.role.value)}"
    }


@pytest.fixture
def admin(db: Session) -> User:
    return factories.make_user(db, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
def manager(db: Session) -> User:
    return factories.make_user(db, "manager@example.com", UserRole.MANAGER)


@pytest.fixture
def agent(db: Session) -> User:
    return factories.make_user(db, "agent@example.com", UserRole.AGENT)


@pytest.fixture
def other_agent(db: Session) -> User:
    return factories.make_user(db, "agent2@example.com", UserRole.AGENT)


@pytest.fixture
def admin_h(admin: User) -> dict[str, str]:
    return _headers(admin)


@pytest.fixture
def manager_h(manager: User) -> dict[str, str]:
    return _headers(manager)


@pytest.fixture
def agent_h(agent: User) -> dict[str, str]:
    return _headers(agent)


@pytest.fixture
def other_agent_h(other_agent: User) -> dict[str, str]:
    return _headers(other_agent)


@pytest.fixture
def properties(db: Session) -> list[Property]:
    return [
        factories.make_property(db, "Orchid Park 2 BHK", "Baner", PropertyType.APARTMENT, 8_500_000, 2,
                                "Ready to move apartment near the metro with gym and clubhouse"),
        factories.make_property(db, "Skyline 3 BHK", "Baner", PropertyType.APARTMENT, 12_500_000, 3,
                                "Spacious apartment with swimming pool"),
        factories.make_property(db, "Riverstone Villa", "Kharadi", PropertyType.VILLA, 28_000_000, 4,
                                "Independent villa with private garden"),
        factories.make_property(db, "Green Plot", "Wagholi", PropertyType.PLOT, 4_500_000, None,
                                "Corner plot in a gated layout"),
    ]  # fmt: skip


@pytest.fixture
def lead(db: Session, agent: User) -> Lead:
    return factories.make_lead(db, assigned_to=agent)


__all__ = ["LeadSource", "LeadStatus"]
