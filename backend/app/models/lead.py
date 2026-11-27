from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import LeadSource, LeadStatus, ScoreBand, enum_column

if TYPE_CHECKING:
    from app.models.follow_up import FollowUp
    from app.models.interaction import LeadInteraction
    from app.models.prediction import Prediction
    from app.models.requirement import CustomerRequirement
    from app.models.user import User


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="contact_required"),
        CheckConstraint(
            "latest_probability IS NULL OR (latest_probability >= 0 AND latest_probability <= 1)",
            name="probability_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    source: Mapped[LeadSource] = mapped_column(enum_column(LeadSource), index=True)
    status: Mapped[LeadStatus] = mapped_column(
        enum_column(LeadStatus), default=LeadStatus.NEW, index=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("marketing_campaigns.id", ondelete="SET NULL"), index=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Denormalised copy of the most recent prediction: keeps list filtering/sorting cheap.
    latest_probability: Mapped[float | None] = mapped_column(Float, index=True)
    latest_band: Mapped[ScoreBand | None] = mapped_column(enum_column(ScoreBand), index=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    assigned_to: Mapped[User | None] = relationship(lazy="joined")
    requirements: Mapped[list[CustomerRequirement]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="CustomerRequirement.id"
    )
    interactions: Mapped[list[LeadInteraction]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="LeadInteraction.occurred_at"
    )
    follow_ups: Mapped[list[FollowUp]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="FollowUp.id"
    )
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Prediction.id"
    )
