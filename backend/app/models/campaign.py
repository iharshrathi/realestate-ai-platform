from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import LeadSource, enum_column


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (
        CheckConstraint("spend_inr >= 0", name="spend_non_negative"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="dates_ordered"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    channel: Mapped[LeadSource] = mapped_column(enum_column(LeadSource), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    spend_inr: Mapped[int] = mapped_column(BigInteger, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
