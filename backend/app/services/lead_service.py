"""Lead CRUD, filtering, interactions and requirement history."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.time import utcnow
from app.models import CustomerRequirement, Lead, LeadInteraction, MarketingCampaign, User
from app.models.enums import (
    InteractionDirection,
    InteractionType,
    LeadStatus,
    RequirementSource,
    UserRole,
)
from app.schemas.interaction import InteractionCreate
from app.schemas.lead import LeadCreate, LeadQuery, LeadUpdate
from app.schemas.requirement import RequirementIn

# Interaction types that imply a direction when the caller does not give one.
_DEFAULT_DIRECTION = {
    InteractionType.ENQUIRY: InteractionDirection.INBOUND,
    InteractionType.NOTE: InteractionDirection.INTERNAL,
    InteractionType.SITE_VISIT: InteractionDirection.INBOUND,
}

_SORT_COLUMNS = {
    "created_at": Lead.created_at,
    "full_name": Lead.full_name,
    "latest_probability": Lead.latest_probability,
    "status": Lead.status,
}


# ------------------------------------------------------------------------------- access
def visible_leads(user: User) -> Select[tuple[Lead]]:
    """Leads a user may see: admins/managers see all, agents see their own + unassigned."""
    stmt = select(Lead)
    if user.role == UserRole.AGENT:
        stmt = stmt.where(or_(Lead.assigned_to_id == user.id, Lead.assigned_to_id.is_(None)))
    return stmt


def can_access(user: User, lead: Lead) -> bool:
    return (
        user.role in (UserRole.ADMIN, UserRole.MANAGER)
        or lead.assigned_to_id is None
        or lead.assigned_to_id == user.id
    )


def get_lead_for_user(db: Session, lead_id: int, user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or not can_access(user, lead):
        raise NotFoundError("Lead not found")  # 404 (not 403) so IDs cannot be probed
    return lead


# ------------------------------------------------------------------------------- queries
def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_leads(db: Session, user: User, query: LeadQuery) -> tuple[list[Lead], int]:
    stmt = visible_leads(user)
    if query.q:
        pattern = f"%{_escape_like(query.q.strip())}%"
        stmt = stmt.where(
            or_(
                Lead.full_name.ilike(pattern, escape="\\"),
                Lead.email.ilike(pattern, escape="\\"),
                Lead.phone.ilike(pattern, escape="\\"),
            )
        )
    if query.status:
        stmt = stmt.where(Lead.status == query.status)
    if query.source:
        stmt = stmt.where(Lead.source == query.source)
    if query.band:
        stmt = stmt.where(Lead.latest_band == query.band)
    if query.assigned_to_id:
        stmt = stmt.where(Lead.assigned_to_id == query.assigned_to_id)
    if query.created_from:
        stmt = stmt.where(Lead.created_at >= datetime.combine(query.created_from, time.min, UTC))
    if query.created_to:
        stmt = stmt.where(
            Lead.created_at < datetime.combine(query.created_to + timedelta(days=1), time.min, UTC)
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = _SORT_COLUMNS[query.sort_by]
    ordering = column.asc() if query.order == "asc" else column.desc()
    if query.sort_by == "latest_probability":
        ordering = ordering.nulls_last()
    stmt = stmt.order_by(ordering, Lead.id.desc())
    stmt = stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
    return list(db.scalars(stmt).unique()), total


def current_requirement(db: Session, lead_id: int) -> CustomerRequirement | None:
    return db.scalars(
        select(CustomerRequirement)
        .where(CustomerRequirement.lead_id == lead_id)
        .order_by(CustomerRequirement.id.desc())
        .limit(1)
    ).first()


# ------------------------------------------------------------------------------ commands
def _ensure_unique_contact(
    db: Session, *, email: str | None, phone: str | None, exclude_id: int | None = None
) -> None:
    conditions = []
    if email:
        conditions.append(func.lower(Lead.email) == email.lower())
    if phone:
        conditions.append(Lead.phone == phone)
    if not conditions:
        return
    stmt = select(Lead.id).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Lead.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise ConflictError("A lead with this email or phone already exists")


def find_lead_by_contact(db: Session, *, email: str | None, phone: str | None) -> Lead | None:
    conditions = []
    if email:
        conditions.append(func.lower(Lead.email) == email.lower())
    if phone:
        conditions.append(Lead.phone == phone)
    if not conditions:
        return None
    return db.scalars(select(Lead).where(or_(*conditions)).limit(1)).first()


def _check_references(db: Session, *, campaign_id: int | None, assigned_to_id: int | None) -> None:
    if campaign_id is not None and db.get(MarketingCampaign, campaign_id) is None:
        raise NotFoundError("Campaign not found")
    if assigned_to_id is not None:
        assignee = db.get(User, assigned_to_id)
        if assignee is None or not assignee.is_active:
            raise NotFoundError("Assignee not found")


def create_lead(
    db: Session,
    data: LeadCreate,
    actor: User,
    *,
    requirement_source: RequirementSource = RequirementSource.MANUAL,
) -> Lead:
    _ensure_unique_contact(db, email=data.email, phone=data.phone)
    _check_references(db, campaign_id=data.campaign_id, assigned_to_id=data.assigned_to_id)
    if actor.role == UserRole.AGENT and data.assigned_to_id not in (None, actor.id):
        raise ForbiddenError("Agents can only assign leads to themselves")

    lead = Lead(
        full_name=data.full_name.strip(),
        email=data.email.lower() if data.email else None,
        phone=data.phone,
        source=data.source,
        campaign_id=data.campaign_id,
        # Agents who create a lead own it by default.
        assigned_to_id=data.assigned_to_id
        if data.assigned_to_id is not None
        else (actor.id if actor.role == UserRole.AGENT else None),
    )
    db.add(lead)
    db.flush()

    if data.requirement:
        db.add(
            CustomerRequirement(
                lead_id=lead.id, source=requirement_source, **data.requirement.model_dump()
            )
        )
    if data.message:
        db.add(
            LeadInteraction(
                lead_id=lead.id,
                type=InteractionType.ENQUIRY,
                direction=InteractionDirection.INBOUND,
                content=data.message,
                created_by_id=actor.id,
            )
        )
    db.commit()
    db.refresh(lead)
    return lead


def update_lead(db: Session, lead: Lead, data: LeadUpdate, actor: User) -> Lead:
    changes = data.model_dump(exclude_unset=True)
    _ensure_unique_contact(
        db, email=changes.get("email"), phone=changes.get("phone"), exclude_id=lead.id
    )
    if "campaign_id" in changes or "assigned_to_id" in changes:
        _check_references(
            db,
            campaign_id=changes.get("campaign_id"),
            assigned_to_id=changes.get("assigned_to_id"),
        )
    if (
        actor.role == UserRole.AGENT
        and "assigned_to_id" in changes
        and changes["assigned_to_id"] not in (None, actor.id)
    ):
        raise ForbiddenError("Agents can only assign leads to themselves")

    for field, value in changes.items():
        if field in ("full_name", "email", "phone", "source") and value is None:
            continue  # these are required / identity fields: ignore explicit nulls
        setattr(lead, field, value.lower() if field == "email" and value else value)

    if "status" in changes and changes["status"] is not None:
        if lead.status == LeadStatus.CONVERTED and lead.converted_at is None:
            lead.converted_at = utcnow()
        elif lead.status != LeadStatus.CONVERTED:
            lead.converted_at = None
    db.commit()
    db.refresh(lead)
    return lead


def delete_lead(db: Session, lead: Lead) -> None:
    db.delete(lead)
    db.commit()


# ---------------------------------------------------------------------- interactions
def add_interaction(
    db: Session, lead: Lead, data: InteractionCreate, actor: User | None
) -> LeadInteraction:
    direction = data.direction or _DEFAULT_DIRECTION.get(data.type, InteractionDirection.OUTBOUND)
    interaction = LeadInteraction(
        lead_id=lead.id,
        type=data.type,
        direction=direction,
        content=data.content,
        occurred_at=data.occurred_at or utcnow(),
        created_by_id=actor.id if actor else None,
    )
    db.add(interaction)
    # First outbound contact moves a brand-new lead to "contacted" (a human action).
    if (
        actor is not None
        and lead.status == LeadStatus.NEW
        and direction == InteractionDirection.OUTBOUND
    ):
        lead.status = LeadStatus.CONTACTED
    lead.updated_at = utcnow()
    db.commit()
    db.refresh(interaction)
    return interaction


def add_requirement(
    db: Session,
    lead: Lead,
    data: RequirementIn,
    source: RequirementSource,
    raw_text: str | None = None,
) -> CustomerRequirement:
    requirement = CustomerRequirement(
        lead_id=lead.id, source=source, raw_text=raw_text, **data.model_dump()
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement
