"""Schema creation.

``create_all`` is used for simplicity. Before the schema starts changing in production, adopt
Alembic migrations (``docs/schema.sql`` shows the exact DDL for PostgreSQL).
"""

from __future__ import annotations

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base
from app.db.session import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
