from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import ScoreBand, enum_column
from app.models.lead import Lead


class Prediction(Base):
    """One scoring event. Append-only, so score history is auditable."""

    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability_range"),
        Index("ix_predictions_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    probability: Mapped[float] = mapped_column(Float)
    band: Mapped[ScoreBand] = mapped_column(enum_column(ScoreBand))
    model_version: Mapped[str] = mapped_column(String(80))
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    factors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="predictions")
