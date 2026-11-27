from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import InteractionDirection, InteractionType, enum_column
from app.models.lead import Lead


class LeadInteraction(Base):
    __tablename__ = "lead_interactions"
    __table_args__ = (Index("ix_lead_interactions_lead_occurred", "lead_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    type: Mapped[InteractionType] = mapped_column(enum_column(InteractionType))
    direction: Mapped[InteractionDirection] = mapped_column(enum_column(InteractionDirection))
    content: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="interactions")
