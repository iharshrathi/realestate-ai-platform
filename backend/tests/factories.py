"""Small helpers that create rows directly in the database for tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import count

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.time import utcnow
from app.models import CustomerRequirement, Lead, LeadInteraction, Property, User
from app.models.enums import (
    InteractionDirection,
    InteractionType,
    LeadSource,
    LeadStatus,
    PropertyType,
    UserRole,
)

_counter = count(1)
PASSWORD = "TestPassw0rd!"


def make_user(db: Session, email: str, role: UserRole, *, active: bool = True) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].title(),
        hashed_password=hash_password(PASSWORD),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    return user


def make_property(
    db: Session,
    title: str,
    location: str,
    property_type: PropertyType,
    price: int,
    bedrooms: int | None,
    description: str = "",
    **extra,
) -> Property:
    prop = Property(
        title=title,
        location=location,
        property_type=property_type,
        price_inr=price,
        bedrooms=bedrooms,
        description=description,
        amenities=["gym", "parking"],
        **extra,
    )
    db.add(prop)
    db.commit()
    return prop


def make_lead(
    db: Session,
    *,
    name: str = "Rohan Mehta",
    source: LeadSource = LeadSource.WEBSITE,
    status: LeadStatus = LeadStatus.NEW,
    assigned_to: User | None = None,
    created_at: datetime | None = None,
    converted_at: datetime | None = None,
    requirement: dict | None = None,
    interactions: int = 0,
    **extra,
) -> Lead:
    n = next(_counter)
    lead = Lead(
        full_name=name,
        email=f"lead{n}@example.com",
        phone=f"+91000000{n:04d}",
        source=source,
        status=status,
        assigned_to_id=assigned_to.id if assigned_to else None,
        created_at=created_at or utcnow() - timedelta(days=10),
        converted_at=converted_at,
        **extra,
    )
    db.add(lead)
    db.flush()
    if requirement is not None:
        db.add(CustomerRequirement(lead_id=lead.id, **requirement))
    for i in range(interactions):
        db.add(
            LeadInteraction(
                lead_id=lead.id,
                type=InteractionType.ENQUIRY if i == 0 else InteractionType.CALL,
                direction=InteractionDirection.INBOUND
                if i % 2 == 0
                else InteractionDirection.OUTBOUND,
                content="msg",
                occurred_at=utcnow() - timedelta(days=9 - i),
            )
        )
    db.commit()
    return lead
