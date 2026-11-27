from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import PropertyStatus, PropertyType, enum_column


class Property(Base):
    """A verified listing. The chatbot may only talk about rows in this table."""

    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint("price_inr > 0", name="price_positive"),
        CheckConstraint("bedrooms IS NULL OR bedrooms >= 0", name="bedrooms_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(120), index=True)
    property_type: Mapped[PropertyType] = mapped_column(enum_column(PropertyType), index=True)
    price_inr: Mapped[int] = mapped_column(BigInteger, index=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    area_sqft: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    amenities: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[PropertyStatus] = mapped_column(
        enum_column(PropertyStatus), default=PropertyStatus.AVAILABLE, index=True
    )
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
