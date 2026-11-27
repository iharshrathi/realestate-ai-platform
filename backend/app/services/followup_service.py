"""Follow-up assistant: prioritise, draft (template ± LLM), and manage the approval workflow.

Human-in-the-loop guarantees (enforced here, covered by tests):

* AI-generated follow-ups are always created as ``draft``.
* Only a human action can move a follow-up to ``approved``.
* Only an ``approved`` follow-up can be completed/marked as sent, and "sent" just records that
  a human sent it. This system never delivers messages by itself.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.time import ensure_utc, utcnow
from app.models import CustomerRequirement, FollowUp, Lead, LeadInteraction, User
from app.models.enums import (
    DONE_FOLLOW_UP_STATUSES,
    PENDING_FOLLOW_UP_STATUSES,
    FollowUpAuthor,
    FollowUpChannel,
    FollowUpStatus,
    InteractionDirection,
    InteractionType,
    LeadStatus,
    Priority,
    ScoreBand,
)
from app.schemas.follow_up import FollowUpCreate, FollowUpQuery, FollowUpUpdate
from app.schemas.property import Recommendation
from app.services import lead_service, llm
from app.services.recommendation_service import criteria_from_requirement, recommend

logger = logging.getLogger(__name__)

TEMPLATES: dict[str, str] = {
    "first_response": (
        "Hi {name}, thank you for your enquiry with {company}. {requirement_line}{property_line}"
        "Could we have a quick call to understand your needs better? Let me know a convenient time. "
        "– {agent}"
    ),
    "property_shortlist": (
        "Hi {name}, {requirement_line}{property_line}"
        "Would you like to see any of these in person? I can arrange a visit. – {agent}"
    ),
    "site_visit_invite": (
        "Hi {name}, {requirement_line}{property_line}"
        "I'd be happy to arrange a site visit at a time that suits you this week. "
        "What day works best? – {agent}"
    ),
    "post_visit_check_in": (
        "Hi {name}, thank you for visiting with us. How did you find the property? "
        "I'm happy to answer questions or show you similar options. – {agent}"
    ),
    "price_discussion": (
        "Hi {name}, thanks for your interest. {requirement_line}{property_line}"
        "I can share a detailed price breakdown and payment options. Shall we discuss on a call? "
        "– {agent}"
    ),
    "financing_help": (
        "Hi {name}, {requirement_line}If it helps, we can connect you with home-loan advisers to "
        "check your eligibility and EMI options. Would you like that? – {agent}"
    ),
    "re_engage": (
        "Hi {name}, it's been a little while since we last spoke. {requirement_line}"
        "Are you still looking? I'd be glad to share new options. – {agent}"
    ),
}


# ----------------------------------------------------------------------------- priority
def compute_priority(
    lead: Lead,
    *,
    urgency: str | None,
    days_since_contact: int | None,
    last_inbound_unanswered: bool,
) -> tuple[Priority, list[str]]:
    """Transparent points-based priority. Returns the level and the reasons behind it."""
    points, reasons = 0, []
    band_points = {ScoreBand.HOT: 3, ScoreBand.WARM: 2, ScoreBand.COLD: 1}
    if lead.latest_band:
        points += band_points[lead.latest_band]
        reasons.append(
            f"{lead.latest_band.value} lead ({lead.latest_probability:.0%} conversion chance)"
        )
    if urgency == "high":
        points += 2
        reasons.append("customer wants to buy soon")
    elif urgency == "medium":
        points += 1
    if days_since_contact is not None and days_since_contact >= 7:
        points += 2
        reasons.append(f"no contact for {days_since_contact} days")
    elif days_since_contact is not None and days_since_contact >= 3:
        points += 1
        reasons.append(f"no contact for {days_since_contact} days")
    if last_inbound_unanswered:
        points += 2
        reasons.append("customer's last message has not been answered")
    level = Priority.HIGH if points >= 6 else Priority.MEDIUM if points >= 3 else Priority.LOW
    return level, reasons or ["no strong signals"]


def _due_for(priority: Priority) -> timedelta:
    return {
        Priority.HIGH: timedelta(hours=4),
        Priority.MEDIUM: timedelta(days=1),
        Priority.LOW: timedelta(days=3),
    }[priority]


# ---------------------------------------------------------------------------- templates
_INTENT_TEMPLATES = {
    "financing_enquiry": "financing_help",
    "price_enquiry": "price_discussion",
    "site_visit_request": "site_visit_invite",
}


def choose_template(
    lead: Lead,
    *,
    intent: str | None,
    days_since_contact: int | None,
    last: LeadInteraction | None,
    has_properties: bool,
) -> str:
    """Pick the template that best fits the lead's situation (first matching rule wins)."""
    if last is None or (lead.status == LeadStatus.NEW and not _has_outbound(lead)):
        return "first_response"
    # The customer wrote last and asked for something specific: answer that first.
    waiting = (
        last.direction == InteractionDirection.INBOUND and last.type != InteractionType.SITE_VISIT
    )
    if waiting and intent in _INTENT_TEMPLATES:
        template = _INTENT_TEMPLATES[intent]
        return template if template != "site_visit_invite" or has_properties else "first_response"
    if last.type == InteractionType.SITE_VISIT:
        return "post_visit_check_in"
    if days_since_contact is not None and days_since_contact >= 14:
        return "re_engage"
    if intent in _INTENT_TEMPLATES:
        return _INTENT_TEMPLATES[intent]
    if lead.latest_band == ScoreBand.HOT and has_properties:
        return "site_visit_invite"
    return "property_shortlist" if has_properties else "first_response"


def _has_outbound(lead: Lead) -> bool:
    return any(i.direction == InteractionDirection.OUTBOUND for i in lead.interactions)


def _format_inr(value: int) -> str:
    return f"₹{value / 1e7:.2f} Cr" if value >= 1e7 else f"₹{value / 1e5:.0f} L"


def _requirement_line(req: CustomerRequirement | None) -> str:
    if req is None:
        return ""
    bits = []
    kind = " ".join(
        p
        for p in (
            f"{req.bedrooms} BHK" if req.bedrooms else None,
            req.property_type.value if req.property_type else None,
        )
        if p
    )
    if kind:
        bits.append(f"a {kind}")
    if req.preferred_location:
        bits.append(f"in {req.preferred_location}")
    if req.budget_max:
        bits.append(f"within {_format_inr(req.budget_max)}")
    return f"I understand you're looking for {' '.join(bits)}. " if bits else ""


def _property_line(recommendations: list[Recommendation]) -> str:
    if not recommendations:
        return ""
    lines = [
        f"• {r.property.title} – {r.property.location}, {_format_inr(r.property.price_inr)}"
        for r in recommendations[:3]
    ]
    return "Here are some options that match:\n" + "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ LLM guardrail
_NUMBER_RE = re.compile(r"\d[\d,.]*")


def llm_message_is_grounded(candidate: str, allowed_facts: str) -> bool:
    """Reject LLM text that contains numbers or links not present in the facts we supplied."""
    if not candidate.strip() or len(candidate) > 1200:
        return False
    if "http" in candidate.lower() and "http" not in allowed_facts.lower():
        return False
    allowed = set(_NUMBER_RE.findall(allowed_facts))
    return all(number in allowed for number in _NUMBER_RE.findall(candidate))


_LLM_SYSTEM = (
    "You write short, polite follow-up messages for a real-estate sales agent. Use ONLY the facts "
    "provided. Do not invent prices, discounts, availability, dates, or promises. Keep it under "
    "100 words and keep the agent's sign-off. Output only the message text."
)


def _personalise_with_llm(draft: str, facts: str) -> str | None:
    reply = llm.safe_complete(
        system=_LLM_SYSTEM,
        prompt=f"Facts:\n{facts}\n\nDraft to improve:\n{draft}",
        max_tokens=350,
    )
    if reply and llm_message_is_grounded(reply, f"{facts}\n{draft}"):
        return reply
    if reply:
        logger.warning("Discarded an ungrounded LLM follow-up message")
    return None


# -------------------------------------------------------------------------- suggestion
@dataclass
class Suggestion:
    follow_up: FollowUp
    template_key: str
    priority_reasons: list[str]
    recommendations: list[Recommendation]
    generated_by: FollowUpAuthor


def suggest_follow_up(db: Session, lead: Lead, actor: User, *, use_llm: bool = True) -> Suggestion:
    """Create (or refresh) an AI draft follow-up for a lead. Never sends anything."""
    now = utcnow()
    requirement = lead_service.current_requirement(db, lead.id)
    recommendations = recommend(db, criteria_from_requirement(requirement), limit=3)

    contact_events = [i for i in lead.interactions if i.direction != InteractionDirection.INTERNAL]
    last = max(contact_events, key=lambda i: ensure_utc(i.occurred_at), default=None)
    days_since = (now - ensure_utc(last.occurred_at)).days if last else None
    unanswered = last is not None and last.direction == InteractionDirection.INBOUND

    priority, reasons = compute_priority(
        lead,
        urgency=requirement.urgency if requirement else None,
        days_since_contact=days_since,
        last_inbound_unanswered=unanswered,
    )
    template_key = choose_template(
        lead,
        intent=requirement.intent if requirement else None,
        days_since_contact=days_since,
        last=last,
        has_properties=bool(recommendations),
    )
    agent_name = lead.assigned_to.full_name if lead.assigned_to else actor.full_name
    message = TEMPLATES[template_key].format(
        name=lead.full_name.split()[0],
        company=get_settings().company_name,
        agent=agent_name,
        requirement_line=_requirement_line(requirement),
        property_line=_property_line(recommendations),
    )
    message = re.sub(r"[ \t]+", " ", message).strip()

    author = FollowUpAuthor.TEMPLATE
    if use_llm and get_settings().llm_enabled:
        improved = _personalise_with_llm(message, message)
        if improved:
            message, author = improved, FollowUpAuthor.LLM

    channel = FollowUpChannel.WHATSAPP if lead.phone else FollowUpChannel.EMAIL
    rationale = "; ".join(reasons)

    # Idempotent: refresh the existing unreviewed AI draft instead of piling up duplicates.
    follow_up = db.scalars(
        select(FollowUp).where(
            FollowUp.lead_id == lead.id,
            FollowUp.status == FollowUpStatus.DRAFT,
            FollowUp.generated_by != FollowUpAuthor.HUMAN,
        )
    ).first()
    if follow_up is None:
        follow_up = FollowUp(lead_id=lead.id)
        db.add(follow_up)
    follow_up.assigned_to_id = lead.assigned_to_id or actor.id
    follow_up.channel = channel
    follow_up.message = message
    follow_up.template_key = template_key
    follow_up.priority = priority
    follow_up.rationale = rationale
    follow_up.status = FollowUpStatus.DRAFT  # always: a human must approve
    follow_up.generated_by = author
    follow_up.due_at = now + _due_for(priority)
    db.commit()
    db.refresh(follow_up)
    return Suggestion(follow_up, template_key, reasons, recommendations, author)


# ------------------------------------------------------------------------------ queries
def _follow_up_stmt(user: User) -> Select[tuple[FollowUp]]:
    stmt = (
        select(FollowUp).join(Lead, FollowUp.lead_id == Lead.id).options(joinedload(FollowUp.lead))
    )
    visible_ids = lead_service.visible_leads(user).with_only_columns(Lead.id).subquery()
    return stmt.where(FollowUp.lead_id.in_(select(visible_ids.c.id)))


def list_follow_ups(db: Session, user: User, query: FollowUpQuery) -> tuple[list[FollowUp], int]:
    stmt = _follow_up_stmt(user)
    if query.group == "pending":
        stmt = stmt.where(FollowUp.status.in_(PENDING_FOLLOW_UP_STATUSES))
    elif query.group == "completed":
        stmt = stmt.where(FollowUp.status.in_(DONE_FOLLOW_UP_STATUSES))
    elif query.group == "rejected":
        stmt = stmt.where(FollowUp.status == FollowUpStatus.REJECTED)
    if query.priority:
        stmt = stmt.where(FollowUp.priority == query.priority)
    if query.lead_id:
        stmt = stmt.where(FollowUp.lead_id == query.lead_id)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    priority_rank = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
    stmt = stmt.order_by(FollowUp.due_at.asc().nulls_last(), FollowUp.id.desc())
    stmt = stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
    items = list(db.scalars(stmt).unique())
    if query.group == "pending":  # most urgent first within the page
        items.sort(key=lambda f: (priority_rank[f.priority], f.due_at or utcnow()))
    return items, total


def get_follow_up_for_user(db: Session, follow_up_id: int, user: User) -> FollowUp:
    follow_up = db.get(FollowUp, follow_up_id)
    if follow_up is None:
        raise NotFoundError("Follow-up not found")
    lead_service.get_lead_for_user(db, follow_up.lead_id, user)  # enforces lead visibility
    return follow_up


# ------------------------------------------------------------------------------ commands
def create_manual(db: Session, lead: Lead, data: FollowUpCreate, actor: User) -> FollowUp:
    """A follow-up written by a human. It is approved by its author from the start."""
    now = utcnow()
    follow_up = FollowUp(
        lead_id=lead.id,
        assigned_to_id=lead.assigned_to_id or actor.id,
        channel=data.channel,
        message=data.message,
        priority=data.priority,
        due_at=data.due_at or now + _due_for(data.priority),
        generated_by=FollowUpAuthor.HUMAN,
        status=FollowUpStatus.APPROVED,
        approved_by_id=actor.id,
        approved_at=now,
    )
    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)
    return follow_up


def update_follow_up(db: Session, follow_up: FollowUp, data: FollowUpUpdate) -> FollowUp:
    if follow_up.status not in PENDING_FOLLOW_UP_STATUSES:
        raise ConflictError("Only pending follow-ups can be edited")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None:
            setattr(follow_up, field, value)
    # Editing the text of an approved AI draft invalidates the approval.
    if (
        "message" in changes
        and follow_up.status == FollowUpStatus.APPROVED
        and follow_up.generated_by != FollowUpAuthor.HUMAN
    ):
        follow_up.status = FollowUpStatus.DRAFT
        follow_up.approved_by_id = follow_up.approved_at = None
    db.commit()
    db.refresh(follow_up)
    return follow_up


def approve(db: Session, follow_up: FollowUp, actor: User) -> FollowUp:
    if follow_up.status != FollowUpStatus.DRAFT:
        raise ConflictError(
            f"Only drafts can be approved (current status: {follow_up.status.value})"
        )
    if not follow_up.message.strip():
        raise ConflictError("Cannot approve an empty message")
    follow_up.status = FollowUpStatus.APPROVED
    follow_up.approved_by_id = actor.id
    follow_up.approved_at = utcnow()
    db.commit()
    db.refresh(follow_up)
    return follow_up


def reject(db: Session, follow_up: FollowUp) -> FollowUp:
    if follow_up.status not in PENDING_FOLLOW_UP_STATUSES:
        raise ConflictError("Only pending follow-ups can be rejected")
    follow_up.status = FollowUpStatus.REJECTED
    db.commit()
    db.refresh(follow_up)
    return follow_up


def complete(db: Session, follow_up: FollowUp, actor: User) -> FollowUp:
    """A human confirms the follow-up was sent (or the call was made)."""
    if follow_up.status != FollowUpStatus.APPROVED:
        raise ConflictError("A follow-up must be approved before it can be marked as done")
    now = utcnow()
    follow_up.status = (
        FollowUpStatus.COMPLETED
        if follow_up.channel == FollowUpChannel.CALL
        else FollowUpStatus.SENT
    )
    follow_up.sent_at = now
    # Keep the lead's activity history complete: log the outreach as an interaction.
    lead = follow_up.lead
    interaction_type = InteractionType(follow_up.channel.value)
    db.add(
        LeadInteraction(
            lead_id=lead.id,
            type=interaction_type,
            direction=InteractionDirection.OUTBOUND,
            content=follow_up.message,
            occurred_at=now,
            created_by_id=actor.id,
        )
    )
    if lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.CONTACTED
    db.commit()
    db.refresh(follow_up)
    return follow_up
