from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import PropertyType, RequirementSource, enum_column
from app.models.lead import Lead


class CustomerRequirement(Base):
    """What a lead is looking for. Append-only: the newest row is the current profile,
    older rows are kept as history (so automated extraction never overwrites a human entry)."""

    __tablename__ = "customer_requirements"
    __table_args__ = (
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="budget_ordered",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    budget_min: Mapped[int | None] = mapped_column(BigInteger)
    budget_max: Mapped[int | None] = mapped_column(BigInteger)
    preferred_location: Mapped[str | None] = mapped_column(String(120))
    property_type: Mapped[PropertyType | None] = mapped_column(enum_column(PropertyType))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    purchase_timeline_days: Mapped[int | None] = mapped_column(Integer)
    urgency: Mapped[str | None] = mapped_column(String(10))
    intent: Mapped[str | None] = mapped_column(String(40))
    loan_preapproved: Mapped[bool | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[RequirementSource] = mapped_column(
        enum_column(RequirementSource), default=RequirementSource.MANUAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="requirements")

    @property
    def budget_value(self) -> int | None:
        """The single budget figure used for scoring: the ceiling if known, else the floor."""
        return self.budget_max or self.budget_min
