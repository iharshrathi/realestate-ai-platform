"""Customer-facing real-estate chatbot with retrieval-augmented generation (RAG).

Pipeline for every message
--------------------------
1. NLP rules extract requirements + contact details from the latest message (no LLM needed).
2. Structured matching + retrieval select listings from the ``properties`` table only.
3. The answer is written either by an LLM (when configured) constrained to those listings, or by
   a deterministic rules-based responder. The response says which one was used (``mode``).
4. Grounding check: if the LLM mentions a listing id that was not retrieved, its answer is
   discarded and the rules-based reply is used instead. The bot cannot invent listings.
5. A qualified enquiry is saved as a *new* lead, only when the visitor explicitly consented.
   The chatbot can create leads and append a note to a lead it created; it cannot edit anything else.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AgentLog, CustomerRequirement, Lead, LeadInteraction, Property
from app.models.enums import (
    AgentRunStatus,
    InteractionDirection,
    InteractionType,
    LeadSource,
    RequirementSource,
)
from app.schemas.chat import ChatRecommendation, ChatRequest, ChatResponse, CollectedProfile
from app.schemas.nlp import ExtractedRequirements
from app.schemas.property import PropertyPublic, Recommendation
from app.services import lead_service, llm, nlp_service
from app.services.recommendation_service import Criteria, recommend

logger = logging.getLogger(__name__)

_CITED_ID_RE = re.compile(r"\[P(\d+)\]")
_REQUIREMENT_FIELDS = (
    "budget_min",
    "budget_max",
    "preferred_location",
    "property_type",
    "bedrooms",
    "purchase_timeline_days",
    "urgency",
)
_CONTACT_FIELDS = ("name", "phone", "email")


# ------------------------------------------------------------------------- state merging
def merge_profile(
    collected: CollectedProfile,
    extracted: ExtractedRequirements,
    contact: nlp_service.ContactDetails,
) -> CollectedProfile:
    """Update the profile with anything newly found. Newer information overrides older."""
    data = collected.model_dump()
    for field in _REQUIREMENT_FIELDS:
        value = getattr(extracted, field)
        if value is not None:
            data[field] = value
    # A new budget statement replaces the previous range entirely.
    if extracted.budget_min is not None or extracted.budget_max is not None:
        data["budget_min"], data["budget_max"] = extracted.budget_min, extracted.budget_max
    for field in _CONTACT_FIELDS:
        value = getattr(contact, field)
        if value:
            data[field] = value
    return _safe_profile(data, fallback=collected)


def _safe_profile(data: dict, fallback: CollectedProfile) -> CollectedProfile:
    """Validate merged data; drop a bad extracted contact value rather than failing the chat."""
    try:
        return CollectedProfile.model_validate(data)
    except ValueError:
        for field in ("phone", "email"):
            data[field] = getattr(fallback, field)
        return CollectedProfile.model_validate(data)


def next_missing(profile: CollectedProfile) -> str | None:
    """The next thing the bot should ask about, in a natural order."""
    if profile.budget_max is None and profile.budget_min is None:
        return "budget"
    if not profile.preferred_location:
        return "location"
    if not profile.property_type:
        return "property_type"
    if profile.purchase_timeline_days is None:
        return "timeline"
    if not profile.name:
        return "name"
    if not (profile.phone or profile.email):
        return "contact"
    return None


_QUESTIONS = {
    "budget": "What budget range are you considering?",
    "location": "Which area or locality do you prefer?",
    "property_type": "Are you looking for an apartment, villa, plot or a commercial property?",
    "timeline": "How soon are you planning to buy (for example, within 3 months)?",
    "name": "May I know your name?",
    "contact": "What is the best phone number or email to reach you on?",
}


# ------------------------------------------------------------------------------- replies
def _price(value: int) -> str:
    return f"₹{value / 1e7:.2f} Cr" if value >= 1e7 else f"₹{value / 1e5:.0f} L"


def rules_reply(
    profile: CollectedProfile,
    recs: list[Recommendation],
    *,
    intent: str,
    consent: bool,
    saved_now: bool,
) -> str:
    """Deterministic response used when no LLM is configured (or the LLM answer was rejected)."""
    lines: list[str] = []
    if intent == "not_interested":
        return "No problem at all. Thanks for stopping by, and feel free to come back any time."
    if recs:
        lines.append("Here are the best matches from our current listings:")
        for rec in recs[:3]:
            p = rec.property
            lines.append(f"• [P{p.id}] {p.title} – {p.location}, {_price(p.price_inr)}")
    elif profile.budget_max or profile.preferred_location or profile.property_type:
        lines.append(
            "I couldn't find an available listing that matches that right now. "
            "A sales executive can look for off-market options for you."
        )
    else:
        lines.append("Happy to help you find a property!")

    if saved_now:
        lines.append(
            "Thanks! I've passed your details to our sales team and they will contact you shortly."
        )
    elif (nxt := next_missing(profile)) is None and not profile.lead_saved and not consent:
        lines.append("To have our team contact you, please tick the consent box below.")
    elif nxt:
        lines.append(_QUESTIONS[nxt])
    return "\n".join(lines)


_LLM_SYSTEM = (
    "You are a friendly assistant for a real-estate company. Answer ONLY using the LISTINGS "
    "provided. If the listings do not contain the answer, say you don't have that information and "
    "offer to connect the customer with a sales executive. Never invent listings, prices, "
    "availability or discounts. When you mention a listing, cite it as [P<id>]. Keep replies "
    "under 120 words and end by asking for ONE missing detail if any are listed."
)


def _listing_context(recs: list[Recommendation]) -> str:
    rows = []
    for rec in recs:
        p = rec.property
        rows.append(
            f"[P{p.id}] {p.title} | {p.property_type.value} | {p.location} | {_price(p.price_inr)} | "
            f"{p.bedrooms or '-'} BHK | {p.area_sqft or '-'} sqft | amenities: {', '.join(p.amenities)} | "
            f"{p.description}"
        )
    return "\n".join(rows) or "(no matching listings)"


def llm_reply(
    request: ChatRequest, profile: CollectedProfile, recs: list[Recommendation]
) -> str | None:
    """Ask the LLM for an answer grounded in the retrieved listings; ``None`` if it fails or cheats."""
    history = "\n".join(f"{t.role.upper()}: {t.content}" for t in request.messages[-8:])
    missing = next_missing(profile)
    reply = llm.safe_complete(
        system=_LLM_SYSTEM,
        prompt=(
            f"LISTINGS:\n{_listing_context(recs)}\n\n"
            f"CUSTOMER PROFILE SO FAR: {profile.model_dump(exclude_none=True)}\n"
            f"MISSING DETAIL TO ASK FOR: {_QUESTIONS.get(missing, 'none') if missing else 'none'}\n\n"
            f"CONVERSATION:\n{history}\n\nASSISTANT:"
        ),
    )
    if not reply:
        return None
    allowed = {rec.property.id for rec in recs}
    cited = {int(i) for i in _CITED_ID_RE.findall(reply)}
    if not cited <= allowed:
        logger.warning(
            "LLM cited listings %s outside retrieved set %s; discarding", cited - allowed, allowed
        )
        return None
    return reply


# -------------------------------------------------------------------------- lead capture
def _save_lead(db: Session, profile: CollectedProfile, request: ChatRequest) -> bool:
    """Create a lead (or append a note to the existing one). Returns True if anything was saved."""
    if not (profile.name and (profile.phone or profile.email)):
        return False
    if profile.budget_max is None and profile.budget_min is None and not profile.preferred_location:
        return False  # not yet a qualified enquiry

    transcript = "\n".join(f"{t.role}: {t.content}" for t in request.messages)
    existing = lead_service.find_lead_by_contact(db, email=profile.email, phone=profile.phone)
    if existing is not None:
        db.add(
            LeadInteraction(
                lead_id=existing.id,
                type=InteractionType.ENQUIRY,
                direction=InteractionDirection.INBOUND,
                content=f"Returned via website chatbot:\n{transcript}"[:5000],
            )
        )
        db.commit()
        return True

    lead = Lead(
        full_name=profile.name,
        email=profile.email.lower() if profile.email else None,
        phone=profile.phone,
        source=LeadSource.WEBSITE,
    )
    db.add(lead)
    db.flush()
    db.add(
        CustomerRequirement(
            lead_id=lead.id,
            source=RequirementSource.CHATBOT,
            budget_min=profile.budget_min,
            budget_max=profile.budget_max,
            preferred_location=profile.preferred_location,
            property_type=profile.property_type,
            bedrooms=profile.bedrooms,
            purchase_timeline_days=profile.purchase_timeline_days,
            urgency=profile.urgency,
            intent="purchase_enquiry",
            raw_text=transcript[:5000],
        )
    )
    db.add(
        LeadInteraction(
            lead_id=lead.id,
            type=InteractionType.ENQUIRY,
            direction=InteractionDirection.INBOUND,
            content=f"Website chatbot conversation:\n{transcript}"[:5000],
        )
    )
    db.add(
        AgentLog(
            run_id=str(uuid.uuid4()),
            agent_name="chatbot",
            action="create_lead",
            lead_id=lead.id,
            status=AgentRunStatus.SUCCESS,
            input_summary={"consent_to_contact": True},
            output_summary={
                "source": "website",
                "has_phone": bool(profile.phone),
                "has_email": bool(profile.email),
            },
        )
    )
    db.commit()
    return True


# ------------------------------------------------------------------------------- entry
def handle_message(db: Session, request: ChatRequest) -> ChatResponse:
    last_message = request.messages[-1].content
    known_locations = list(db.scalars(select(Property.location).distinct()))
    extracted = nlp_service.extract_requirements(last_message, known_locations)
    contact = nlp_service.extract_contact_details(last_message)
    profile = merge_profile(request.collected, extracted, contact)

    criteria = Criteria(
        budget_min=profile.budget_min,
        budget_max=profile.budget_max,
        location=profile.preferred_location,
        property_type=profile.property_type,
        bedrooms=profile.bedrooms,
        free_text=last_message,
    )
    if criteria.is_empty():
        # No structured criteria yet: answer open questions with pure text retrieval.
        recs = recommend(db, Criteria(free_text=last_message), limit=3) if extracted.intents else []
    else:
        recs = recommend(db, criteria, limit=3)

    saved_now = False
    if (
        request.consent_to_contact
        and not profile.lead_saved
        and extracted.intent != "not_interested"
    ):
        saved_now = _save_lead(db, profile, request)
        if saved_now:
            profile = profile.model_copy(update={"lead_saved": True})

    mode = "rules"
    reply = None
    if get_settings().llm_enabled and extracted.intent != "not_interested":
        reply = llm_reply(request, profile, recs)
        if reply and saved_now:
            reply += "\n\nThanks! I've passed your details to our sales team and they will contact you shortly."
    if reply:
        mode = "llm"
    else:
        reply = rules_reply(
            profile,
            recs,
            intent=extracted.intent,
            consent=request.consent_to_contact,
            saved_now=saved_now,
        )

    cited = sorted({int(i) for i in _CITED_ID_RE.findall(reply)} & {r.property.id for r in recs})
    return ChatResponse(
        reply=reply,
        collected=profile,
        recommendations=[
            ChatRecommendation(
                property=PropertyPublic.model_validate(r.property.model_dump()),
                match_score=r.match_score,
                reasons=r.reasons,
            )
            for r in recs
        ],
        lead_saved=profile.lead_saved,
        mode=mode,  # type: ignore[arg-type]
        cited_property_ids=cited,
    )
