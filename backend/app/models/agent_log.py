from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import AgentRunStatus, enum_column


class AgentLog(Base):
    """Audit trail of every automated decision or action (one row per agent step)."""

    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(60), index=True)
    action: Mapped[str] = mapped_column(String(80))
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    triggered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[AgentRunStatus] = mapped_column(enum_column(AgentRunStatus))
    input_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
