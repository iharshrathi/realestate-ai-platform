from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.enums import PropertyStatus, PropertyType
from app.schemas.common import Page
from app.schemas.property import PropertyCreate, PropertyOut, PropertyUpdate, Recommendation
from app.services import property_service
from app.services.recommendation_service import Criteria, recommend

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=Page[PropertyOut])
def list_properties(
    db: DbSession,
    _: CurrentUser,
    status_filter: Annotated[PropertyStatus | None, Query(alias="status")] = None,
    property_type: PropertyType | None = None,
    location: Annotated[str | None, Query(max_length=120)] = None,
    max_price: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PropertyOut]:
    items, total = property_service.list_properties(
        db,
        status=status_filter,
        property_type=property_type,
        location=location,
        max_price=max_price,
        page=page,
        page_size=page_size,
    )
    return Page[PropertyOut](
        items=[PropertyOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/search", response_model=list[Recommendation])
def search_properties(
    db: DbSession,
    _: CurrentUser,
    budget_max: Annotated[int | None, Query(gt=0)] = None,
    budget_min: Annotated[int | None, Query(ge=0)] = None,
    location: Annotated[str | None, Query(max_length=120)] = None,
    property_type: PropertyType | None = None,
    bedrooms: Annotated[int | None, Query(ge=0, le=20)] = None,
    text: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[Recommendation]:
    """Rank available listings for ad-hoc criteria (structured match + optional free-text retrieval)."""
    criteria = Criteria(budget_min, budget_max, location, property_type, bedrooms, text)
    return recommend(db, criteria, limit=limit)


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: DbSession, _: CurrentUser) -> PropertyOut:
    return PropertyOut.model_validate(property_service.get_property(db, property_id))


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_property(data: PropertyCreate, db: DbSession, _: ManagerUser) -> PropertyOut:
    return PropertyOut.model_validate(property_service.create_property(db, data))


@router.patch("/{property_id}", response_model=PropertyOut)
def update_property(
    property_id: int, data: PropertyUpdate, db: DbSession, _: ManagerUser
) -> PropertyOut:
    prop = property_service.get_property(db, property_id)
    return PropertyOut.model_validate(property_service.update_property(db, prop, data))


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, db: DbSession, _: ManagerUser) -> Response:
    property_service.delete_property(db, property_service.get_property(db, property_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
