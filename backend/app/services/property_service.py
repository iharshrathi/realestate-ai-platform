from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Property
from app.models.enums import PropertyStatus, PropertyType
from app.schemas.property import PropertyCreate, PropertyUpdate


def list_properties(
    db: Session,
    *,
    status: PropertyStatus | None = None,
    property_type: PropertyType | None = None,
    location: str | None = None,
    max_price: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Property], int]:
    stmt = select(Property)
    if status:
        stmt = stmt.where(Property.status == status)
    if property_type:
        stmt = stmt.where(Property.property_type == property_type)
    if location:
        stmt = stmt.where(func.lower(Property.location) == location.lower())
    if max_price:
        stmt = stmt.where(Property.price_inr <= max_price)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(Property.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return list(db.scalars(stmt)), total


def get_property(db: Session, property_id: int) -> Property:
    prop = db.get(Property, property_id)
    if prop is None:
        raise NotFoundError("Property not found")
    return prop


def create_property(db: Session, data: PropertyCreate) -> Property:
    prop = Property(**data.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


def update_property(db: Session, prop: Property, data: PropertyUpdate) -> Property:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(prop, field, value)
    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, prop: Property) -> None:
    db.delete(prop)
    db.commit()
