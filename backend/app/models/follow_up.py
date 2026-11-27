from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import (
    FollowUpAuthor,
    FollowUpChannel,
    FollowUpStatus,
    Priority,
    enum_column,
)
from app.models.lead import Lead


class FollowUp(Base):
    """A planned or drafted outreach. Nothing leaves the system automatically: an AI-written
    draft stays in ``draft`` until a human approves it, and ``sent`` is only ever set by a human
    confirming they sent it."""

    __tablename__ = "follow_ups"
    __table_args__ = (Index("ix_follow_ups_status_due", "status", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    channel: Mapped[FollowUpChannel] = mapped_column(enum_column(FollowUpChannel))
    message: Mapped[str] = mapped_column(Text, default="")
    template_key: Mapped[str | None] = mapped_column(String(40))
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), default=Priority.MEDIUM)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FollowUpStatus] = mapped_column(
        enum_column(FollowUpStatus), default=FollowUpStatus.DRAFT
    )
    generated_by: Mapped[FollowUpAuthor] = mapped_column(
        enum_column(FollowUpAuthor), default=FollowUpAuthor.HUMAN
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    lead: Mapped[Lead] = relationship(back_populates="follow_ups")

    @property
    def lead_name(self) -> str:
        return self.lead.full_name
