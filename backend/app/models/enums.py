"""Enumerations shared by models, schemas and services."""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    AGENT = "agent"


class LeadSource(StrEnum):
    WEBSITE = "website"
    FACEBOOK_ADS = "facebook_ads"
    NEWSPAPER = "newspaper"
    DIRECT = "direct"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    SITE_VISIT = "site_visit"
    NEGOTIATION = "negotiation"
    CONVERTED = "converted"
    LOST = "lost"


# Statuses that count as "qualified or further along the funnel".
QUALIFIED_STATUSES = (LeadStatus.QUALIFIED, LeadStatus.SITE_VISIT, LeadStatus.NEGOTIATION)
OPEN_STATUSES = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.SITE_VISIT,
    LeadStatus.NEGOTIATION,
)


class PropertyType(StrEnum):
    APARTMENT = "apartment"
    VILLA = "villa"
    PLOT = "plot"
    COMMERCIAL = "commercial"


class PropertyStatus(StrEnum):
    AVAILABLE = "available"
    ON_HOLD = "on_hold"
    SOLD = "sold"


class InteractionType(StrEnum):
    ENQUIRY = "enquiry"  # inbound message from the customer
    CALL = "call"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    SITE_VISIT = "site_visit"
    MEETING = "meeting"
    NOTE = "note"  # internal note


class InteractionDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class FollowUpStatus(StrEnum):
    DRAFT = "draft"  # waiting for human approval
    APPROVED = "approved"  # approved, not yet sent
    SENT = "sent"  # a human confirmed it was sent
    COMPLETED = "completed"  # e.g. a call that was made
    REJECTED = "rejected"


PENDING_FOLLOW_UP_STATUSES = (FollowUpStatus.DRAFT, FollowUpStatus.APPROVED)
DONE_FOLLOW_UP_STATUSES = (FollowUpStatus.SENT, FollowUpStatus.COMPLETED)


class FollowUpChannel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    CALL = "call"


class FollowUpAuthor(StrEnum):
    HUMAN = "human"
    TEMPLATE = "template"  # deterministic template, no LLM
    LLM = "llm"  # template personalised by an LLM


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScoreBand(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class RequirementSource(StrEnum):
    MANUAL = "manual"
    NLP = "nlp"
    CHATBOT = "chatbot"
    IMPORT = "import"


class AgentRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


def enum_column(enum_cls: type[StrEnum]) -> sa.Enum:
    """Portable enum column: VARCHAR + CHECK constraint (identical on SQLite and PostgreSQL)."""
    return sa.Enum(
        enum_cls,
        name=enum_cls.__name__.lower(),
        native_enum=False,
        length=24,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda e: [member.value for member in e],
    )
