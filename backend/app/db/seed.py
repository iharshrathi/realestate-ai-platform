"""Demo data: users, listings, campaigns and leads.

EVERYTHING created here is SYNTHETIC (``is_synthetic = true``) and generated from hand-written
rules. Names are made up, e-mail addresses use ``example.com`` and phone numbers use an obviously
fake ``+910000…`` prefix. Never present these records as real business results.
"""

from __future__ import annotations

import logging
import random
from datetime import timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ModelNotAvailableError
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    CustomerRequirement,
    FollowUp,
    Lead,
    LeadInteraction,
    MarketingCampaign,
    Property,
    User,
)
from app.models.enums import (
    OPEN_STATUSES,
    FollowUpAuthor,
    FollowUpChannel,
    FollowUpStatus,
    InteractionDirection,
    InteractionType,
    LeadSource,
    LeadStatus,
    Priority,
    PropertyType,
    RequirementSource,
    UserRole,
)
from app.services import scoring_service
from ml.reference import LOCATION_PRICE_INDEX, UNKNOWN, market_price
from ml.synthetic_data import generate_leads

logger = logging.getLogger(__name__)

DEFAULT_DEV_PASSWORD = "ChangeMe123!"
SEED_USERS = [
    ("admin@example.com", "Asha Admin", UserRole.ADMIN),
    ("manager@example.com", "Manav Manager", UserRole.MANAGER),
    ("agent1@example.com", "Aarav Agent", UserRole.AGENT),
    ("agent2@example.com", "Diya Agent", UserRole.AGENT),
    ("agent3@example.com", "Kabir Agent", UserRole.AGENT),
]
FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Ishaan",
    "Rohan",
    "Karan",
    "Neha",
    "Priya",
    "Ananya",
    "Sneha",
    "Meera",
    "Riya",
    "Sanjay",
    "Anil",
    "Sunita",
    "Pooja",
    "Nikhil",
    "Tanvi",
    "Rahul",
    "Kavya",
]
LAST_NAMES = [
    "Sharma",
    "Patil",
    "Deshmukh",
    "Kulkarni",
    "Joshi",
    "Mehta",
    "Iyer",
    "Nair",
    "Reddy",
    "Khan",
    "Gupta",
    "Singh",
    "Shah",
    "Pawar",
    "Bhosale",
    "Jadhav",
]
PROJECT_NAMES = [
    "Lakeview Heights",
    "Green Meadows",
    "Skyline Residency",
    "Orchid Park",
    "Maple Grove",
    "Sunrise Towers",
    "Riverstone",
    "Palm Court",
    "Silver Oaks",
    "Horizon Square",
]
AMENITIES = [
    "gym",
    "swimming pool",
    "clubhouse",
    "covered parking",
    "24x7 security",
    "garden",
    "children's play area",
    "power backup",
    "EV charging",
    "jogging track",
]
CAMPAIGNS = [
    ("Website SEO and landing pages", LeadSource.WEBSITE, 180_000),
    ("Google search ads", LeadSource.WEBSITE, 420_000),
    ("Facebook lead ads – monsoon offer", LeadSource.FACEBOOK_ADS, 350_000),
    ("Instagram carousel ads", LeadSource.FACEBOOK_ADS, 260_000),
    ("Sunday newspaper supplement", LeadSource.NEWSPAPER, 300_000),
    ("Newspaper classified insert", LeadSource.NEWSPAPER, 120_000),
    ("Customer referral programme", LeadSource.DIRECT, 90_000),
    ("Walk-in and hoarding", LeadSource.DIRECT, 150_000),
]


def seed_password() -> str:
    settings = get_settings()
    if settings.seed_password:
        return settings.seed_password.get_secret_value()
    if settings.environment == "production":
        raise RuntimeError("Set SEED_PASSWORD before seeding a production database")
    return DEFAULT_DEV_PASSWORD


def seed_users(db: Session) -> list[User]:
    users = []
    password_hash = hash_password(seed_password())
    for email, name, role in SEED_USERS:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(email=email, full_name=name, role=role, hashed_password=password_hash)
            db.add(user)
        users.append(user)
    db.commit()
    return users


def seed_properties(db: Session, rng: random.Random) -> list[Property]:
    listings: list[Property] = []
    for location in LOCATION_PRICE_INDEX:
        for ptype in PropertyType:
            for _ in range(2 if ptype in (PropertyType.APARTMENT, PropertyType.PLOT) else 1):
                bhk = (
                    rng.choice([1, 2, 2, 3, 3, 4])
                    if ptype == PropertyType.APARTMENT
                    else rng.choice([3, 4, 5])
                    if ptype == PropertyType.VILLA
                    else None
                )
                price = market_price(location, ptype.value) * rng.uniform(0.8, 1.25)
                if bhk:
                    price *= 0.7 + 0.15 * bhk
                project = rng.choice(PROJECT_NAMES)
                kind = f"{bhk} BHK {ptype.value}" if bhk else ptype.value
                listings.append(
                    Property(
                        title=f"{project} – {kind}",
                        location=location,
                        property_type=ptype,
                        price_inr=int(round(price, -5)),
                        bedrooms=bhk,
                        area_sqft=(
                            400 + 280 * bhk
                            if ptype == PropertyType.APARTMENT and bhk
                            else 1200 + 350 * bhk
                            if bhk
                            else rng.choice([1000, 1500, 2400, 3000])
                        ),
                        description=(
                            f"Synthetic demo listing: {kind} in {location}, "
                            f"{rng.choice(['ready to move', 'under construction', 'near the metro', 'close to schools and hospitals'])}."
                        ),
                        amenities=rng.sample(AMENITIES, k=rng.randint(3, 6)),
                        is_synthetic=True,
                    )
                )
    db.add_all(listings)
    db.commit()
    return listings


def seed_campaigns(db: Session) -> list[MarketingCampaign]:
    today = utcnow().date()
    campaigns = [
        MarketingCampaign(
            name=name,
            channel=channel,
            start_date=today - timedelta(days=210),
            spend_inr=spend,
            notes="Synthetic demo campaign",
            is_synthetic=True,
        )
        for name, channel, spend in CAMPAIGNS
    ]
    db.add_all(campaigns)
    db.commit()
    return campaigns


def _enquiry_text(
    location: str, ptype: str, budget: float, timeline: float, rng: random.Random
) -> str:
    kind = (
        "a property"
        if ptype == UNKNOWN
        else f"a {rng.choice([1, 2, 3, 4]) if ptype == 'apartment' else ''} {ptype}".replace(
            "  ", " "
        )
    )
    where = "" if location == UNKNOWN else f" in {location}"
    money = "" if np.isnan(budget) else f" My budget is around {budget / 1e5:.0f} lakh."
    when = "" if np.isnan(timeline) else f" I plan to buy within {int(timeline)} days."
    return f"Hi, I'm looking for {kind}{where}.{money}{when} Please share details."


def _pick_status(row, rng: random.Random) -> LeadStatus:
    if row.converted:
        return LeadStatus.CONVERTED
    if row.lead_age_days > 120 and rng.random() < 0.5:
        return LeadStatus.LOST
    if row.site_visits > 0:
        return rng.choices(
            [LeadStatus.SITE_VISIT, LeadStatus.NEGOTIATION, LeadStatus.LOST, LeadStatus.QUALIFIED],
            weights=[4, 2, 3, 2],
        )[0]
    if row.interaction_count > 3:
        return rng.choices(
            [LeadStatus.QUALIFIED, LeadStatus.CONTACTED, LeadStatus.LOST], weights=[3, 4, 3]
        )[0]
    if row.interaction_count > 0:
        return rng.choices(
            [LeadStatus.CONTACTED, LeadStatus.NEW, LeadStatus.LOST], weights=[5, 3, 1]
        )[0]
    return LeadStatus.NEW


def seed_leads(
    db: Session, n: int, users: list[User], campaigns: list[MarketingCampaign], rng: random.Random
) -> list[Lead]:
    now = utcnow()
    agents = [u for u in users if u.role == UserRole.AGENT]
    frame = generate_leads(n, seed=7)  # different seed from the training set
    leads: list[Lead] = []

    for index, row in enumerate(frame.itertuples(index=False)):
        created_at = now - timedelta(days=int(row.lead_age_days), hours=rng.randint(0, 20))
        source = LeadSource(row.source)
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        matching = [c for c in campaigns if c.channel == source]
        status = _pick_status(row, rng)
        lead = Lead(
            full_name=name,
            email=f"{name.lower().replace(' ', '.')}.{index}@example.com",
            phone=f"+9100000{index:05d}",
            source=source,
            status=status,
            campaign_id=rng.choice(matching).id if matching else None,
            assigned_to_id=rng.choice(agents).id if agents and rng.random() > 0.1 else None,
            is_synthetic=True,
            created_at=created_at,
            updated_at=created_at + timedelta(days=rng.randint(0, int(row.lead_age_days))),
            converted_at=(
                min(created_at + timedelta(days=rng.randint(7, 70)), now - timedelta(hours=1))
                if status == LeadStatus.CONVERTED
                else None
            ),
        )
        db.add(lead)
        db.flush()

        has_budget = not np.isnan(row.budget_inr)
        db.add(
            CustomerRequirement(
                lead_id=lead.id,
                budget_max=int(row.budget_inr) if has_budget else None,
                budget_min=int(row.budget_inr * 0.8) if has_budget else None,
                preferred_location=None
                if row.preferred_location == UNKNOWN
                else row.preferred_location,
                property_type=None
                if row.property_type == UNKNOWN
                else PropertyType(row.property_type),
                bedrooms=rng.choice([1, 2, 3, 4]) if row.property_type == "apartment" else None,
                purchase_timeline_days=None
                if np.isnan(row.purchase_timeline_days)
                else int(row.purchase_timeline_days),
                urgency=None
                if np.isnan(row.purchase_timeline_days)
                else (
                    "high"
                    if row.purchase_timeline_days <= 30
                    else "medium"
                    if row.purchase_timeline_days <= 90
                    else "low"
                ),
                loan_preapproved=bool(row.loan_preapproved),
                source=RequirementSource.IMPORT,
                created_at=created_at,
            )
        )
        _seed_interactions(db, lead, row, created_at, now, rng)
        leads.append(lead)

    db.commit()
    return leads


def _seed_interactions(db: Session, lead: Lead, row, created_at, now, rng: random.Random) -> None:
    count = int(row.interaction_count)
    if count == 0:
        return
    site_visits = min(int(row.site_visits), max(count - 1, 0))
    rest = count - 1 - site_visits
    inbound_rest = min(max(round(row.inbound_ratio * count) - 1 - site_visits, 0), rest)
    kinds: list[tuple[InteractionType, InteractionDirection]] = (
        [(InteractionType.SITE_VISIT, InteractionDirection.INBOUND)] * site_visits
        + [
            (
                rng.choice([InteractionType.CALL, InteractionType.WHATSAPP]),
                InteractionDirection.INBOUND,
            )
            for _ in range(inbound_rest)
        ]
        + [
            (
                rng.choice([InteractionType.CALL, InteractionType.WHATSAPP, InteractionType.EMAIL]),
                InteractionDirection.OUTBOUND,
            )
            for _ in range(rest - inbound_rest)
        ]
    )
    rng.shuffle(kinds)

    last_contact = now - timedelta(days=int(row.days_since_last_contact))
    span = max((last_contact - created_at).total_seconds(), 0)
    offsets = sorted(rng.uniform(0, span) for _ in kinds)
    db.add(
        LeadInteraction(
            lead_id=lead.id,
            type=InteractionType.ENQUIRY,
            direction=InteractionDirection.INBOUND,
            content=_enquiry_text(
                row.preferred_location,
                row.property_type,
                row.budget_inr,
                row.purchase_timeline_days,
                rng,
            ),
            occurred_at=created_at,
        )
    )
    for (kind, direction), offset in zip(kinds, offsets, strict=True):
        db.add(
            LeadInteraction(
                lead_id=lead.id,
                type=kind,
                direction=direction,
                content="Synthetic interaction",
                occurred_at=created_at + timedelta(seconds=offset),
            )
        )


def seed_follow_ups(db: Session, leads: list[Lead], rng: random.Random, limit: int = 40) -> None:
    """A few human-created follow-ups so the follow-up board is not empty."""
    now = utcnow()
    open_leads = [lead for lead in leads if lead.status in OPEN_STATUSES]
    for lead in rng.sample(open_leads, k=min(limit, len(open_leads))):
        done = rng.random() < 0.35
        db.add(
            FollowUp(
                lead_id=lead.id,
                assigned_to_id=lead.assigned_to_id,
                channel=FollowUpChannel.CALL,
                message="Call to check requirements and answer questions (synthetic demo task).",
                priority=rng.choice(list(Priority)),
                status=FollowUpStatus.COMPLETED if done else FollowUpStatus.APPROVED,
                generated_by=FollowUpAuthor.HUMAN,
                due_at=now + timedelta(days=rng.randint(-5, 6)),
                sent_at=now - timedelta(days=rng.randint(1, 5)) if done else None,
                approved_by_id=lead.assigned_to_id,
                approved_at=now - timedelta(days=7),
            )
        )
    db.commit()


def score_open_leads(db: Session, leads: list[Lead]) -> int:
    """Score open leads with the trained model so the UI has predictions to show."""
    scored = 0
    for lead in leads:
        if lead.status not in OPEN_STATUSES:
            continue
        try:
            scoring_service.score_lead(db, lead)
        except ModelNotAvailableError:
            logger.warning("No trained model found; leads were not scored. Run `make train`.")
            break
        scored += 1
    return scored


def seed_demo_data(
    db: Session, n_leads: int = 300, seed: int = 11, score: bool = True
) -> dict[str, int]:
    rng = random.Random(seed)
    users = seed_users(db)
    properties = seed_properties(db, rng)
    campaigns = seed_campaigns(db)
    leads = seed_leads(db, n_leads, users, campaigns, rng)
    seed_follow_ups(db, leads, rng)
    scored = score_open_leads(db, leads) if score else 0
    return {
        "users": len(users),
        "properties": len(properties),
        "campaigns": len(campaigns),
        "leads": len(leads),
        "scored": scored,
    }


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(func.count(User.id))) == 0:
        logger.info("Empty database: seeding synthetic demo data")
        logger.info("Seeded: %s", seed_demo_data(db))
