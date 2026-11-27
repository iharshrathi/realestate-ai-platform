"""Business analytics: KPIs, monthly trends, channel comparison, forecasts and insights.

Everything here is computed with SQL aggregates and simple, transparent statistics. Insights are
rule-generated from the numbers (never invented); an LLM may optionally *summarise* them.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

import numpy as np
from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import FollowUp, Lead, MarketingCampaign, User
from app.models.enums import (
    OPEN_STATUSES,
    PENDING_FOLLOW_UP_STATUSES,
    QUALIFIED_STATUSES,
    LeadStatus,
    ScoreBand,
)
from app.schemas.analytics import (
    ChannelStats,
    Forecast,
    Insight,
    InsightsResponse,
    MonthlyPoint,
    Overview,
)
from app.services import lead_service, llm

logger = logging.getLogger(__name__)

MIN_LEADS_FOR_CHANNEL_INSIGHT = 20


def overview(db: Session, user: User) -> Overview:
    visible = lead_service.visible_leads(user).subquery()
    status_counts = dict(
        db.execute(select(visible.c.status, func.count()).group_by(visible.c.status)).all()
    )
    total = sum(status_counts.values())
    converted = status_counts.get(LeadStatus.CONVERTED, 0)

    def count(*statuses: LeadStatus) -> int:
        return sum(status_counts.get(s, 0) for s in statuses)

    now = utcnow()
    follow_ups = (
        select(FollowUp.id, FollowUp.due_at)
        .where(
            FollowUp.status.in_(PENDING_FOLLOW_UP_STATUSES),
            FollowUp.lead_id.in_(select(visible.c.id)),
        )
        .subquery()
    )
    pending = db.scalar(select(func.count()).select_from(follow_ups)) or 0
    overdue = (
        db.scalar(select(func.count()).select_from(follow_ups).where(follow_ups.c.due_at < now))
        or 0
    )
    hot = (
        db.scalar(
            select(func.count())
            .select_from(visible)
            .where(visible.c.latest_band == ScoreBand.HOT, visible.c.status.in_(OPEN_STATUSES))
        )
        or 0
    )
    synthetic = (
        db.scalar(select(func.count()).select_from(visible).where(visible.c.is_synthetic.is_(True)))
        or 0
    )
    return Overview(
        total_leads=total,
        new_leads=count(LeadStatus.NEW),
        qualified_leads=count(*QUALIFIED_STATUSES),
        converted_customers=converted,
        lost_leads=count(LeadStatus.LOST),
        pending_follow_ups=pending,
        overdue_follow_ups=overdue,
        hot_leads=hot,
        conversion_rate=round(converted / total, 4) if total else 0.0,
        synthetic_leads=synthetic,
    )


def _month_key(year: float, month: float) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def monthly(db: Session, user: User, months: int = 12) -> list[MonthlyPoint]:
    """Leads created and conversions per month for the last ``months`` months (zero-filled)."""
    visible = lead_service.visible_leads(user).subquery()
    created_year = extract("year", visible.c.created_at).label("y")
    created_month = extract("month", visible.c.created_at).label("m")
    created = db.execute(
        select(created_year, created_month, visible.c.source, func.count()).group_by(
            created_year, created_month, visible.c.source
        )
    ).all()
    won_year = extract("year", visible.c.converted_at).label("y")
    won_month = extract("month", visible.c.converted_at).label("m")
    converted = db.execute(
        select(won_year, won_month, func.count())
        .where(visible.c.converted_at.is_not(None))
        .group_by(won_year, won_month)
    ).all()

    leads: dict[str, int] = defaultdict(int)
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for year, month, source, n in created:
        key = _month_key(year, month)
        leads[key] += n
        by_source[key][source.value] += n
    won: dict[str, int] = {_month_key(y, m): n for y, m, n in converted}

    # Build a continuous list of the last N calendar months ending with the current one.
    now = utcnow()
    keys: list[str] = []
    year, month = now.year, now.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return [
        MonthlyPoint(
            month=k,
            leads=leads.get(k, 0),
            converted=won.get(k, 0),
            by_source=dict(by_source.get(k, {})),
        )
        for k in reversed(keys)
    ]


def channels(db: Session, user: User) -> list[ChannelStats]:
    visible = lead_service.visible_leads(user).subquery()
    converted_flag = case((visible.c.status == LeadStatus.CONVERTED, 1), else_=0)
    hot_flag = case((visible.c.latest_band == ScoreBand.HOT, 1), else_=0)
    rows = db.execute(
        select(
            visible.c.source,
            func.count(),
            func.sum(converted_flag),
            func.avg(visible.c.latest_probability),
            func.sum(hot_flag),
            func.count(visible.c.latest_band),
        ).group_by(visible.c.source)
    ).all()
    spend = dict(
        db.execute(
            select(
                MarketingCampaign.channel, func.coalesce(func.sum(MarketingCampaign.spend_inr), 0)
            ).group_by(MarketingCampaign.channel)
        ).all()
    )
    stats = []
    for source, total, converted, avg_score, hot, scored in rows:
        converted, hot = int(converted or 0), int(hot or 0)
        cost = int(spend.get(source, 0))
        stats.append(
            ChannelStats(
                source=source.value,
                leads=total,
                converted=converted,
                conversion_rate=round(converted / total, 4) if total else 0.0,
                avg_score=round(float(avg_score), 4) if avg_score is not None else None,
                hot_share=round(hot / scored, 4) if scored else None,
                spend_inr=cost,
                cost_per_lead=round(cost / total, 2) if cost and total else None,
                cost_per_conversion=round(cost / converted, 2) if cost and converted else None,
            )
        )
    return sorted(stats, key=lambda s: s.conversion_rate, reverse=True)


def _linear_forecast(values: list[float]) -> float | None:
    """Next value of a straight-line fit. Needs >= 3 points; clipped at zero."""
    if len(values) < 3:
        return None
    x = np.arange(len(values))
    slope, intercept = np.polyfit(x, values, 1)
    return max(float(slope * len(values) + intercept), 0.0)


def forecast(db: Session, user: User) -> Forecast:
    visible = lead_service.visible_leads(user).subquery()
    open_rows = db.execute(
        select(visible.c.latest_probability, visible.c.latest_band).where(
            visible.c.status.in_(OPEN_STATUSES)
        )
    ).all()
    scored = [(p, b) for p, b in open_rows if p is not None]
    expected_by_band: dict[str, float] = {band.value: 0.0 for band in ScoreBand}
    for probability, band in scored:
        expected_by_band[band.value] += probability

    # Trend over the last full months (the current month is incomplete, so it is excluded).
    series = monthly(db, user, months=7)[:-1]
    first_active = next((i for i, p in enumerate(series) if p.leads or p.converted), len(series))
    series = series[first_active:]
    return Forecast(
        open_leads=len(open_rows),
        scored_open_leads=len(scored),
        expected_conversions_open_leads=round(sum(p for p, _ in scored), 1),
        expected_by_band={k: round(v, 1) for k, v in expected_by_band.items()},
        next_month_leads=_round(_linear_forecast([p.leads for p in series])),
        next_month_conversions=_round(_linear_forecast([p.converted for p in series])),
        method=(
            "Expected conversions = sum of calibrated model probabilities over open leads. "
            "Next-month figures are a straight-line fit over recent full months."
        ),
        caveat=(
            "Probabilities come from a model trained on synthetic data unless you retrain it on "
            "real history; treat this as a demonstration, not a sales forecast."
        ),
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def build_insights(db: Session, user: User) -> list[Insight]:
    """Rule-based, number-backed insights."""
    insights: list[Insight] = []
    now = utcnow()
    ov = overview(db, user)
    channel_stats = [c for c in channels(db, user) if c.leads >= MIN_LEADS_FOR_CHANNEL_INSIGHT]

    if len(channel_stats) >= 2:
        best, worst = channel_stats[0], channel_stats[-1]
        insights.append(
            Insight(
                key="channel_quality",
                severity="positive",
                title=f"{_label(best.source)} converts best",
                detail=(
                    f"{_label(best.source)} converts {best.conversion_rate:.0%} of {best.leads} leads, "
                    f"versus {worst.conversion_rate:.0%} for {_label(worst.source)} ({worst.leads} leads)."
                ),
            )
        )
        costed = [c for c in channel_stats if c.cost_per_conversion]
        if len(costed) >= 2:
            cheapest = min(costed, key=lambda c: c.cost_per_conversion or 0)
            insights.append(
                Insight(
                    key="channel_cost",
                    severity="info",
                    title=f"{_label(cheapest.source)} is the cheapest per conversion",
                    detail=f"About ₹{cheapest.cost_per_conversion:,.0f} of campaign spend per converted customer.",
                )
            )

    stale_hot = (
        db.scalar(
            select(func.count()).select_from(
                lead_service.visible_leads(user)
                .where(
                    Lead.latest_band == ScoreBand.HOT,
                    Lead.status.in_(OPEN_STATUSES),
                    Lead.id.not_in(
                        select(FollowUp.lead_id).where(
                            FollowUp.status.in_(PENDING_FOLLOW_UP_STATUSES)
                        )
                    ),
                )
                .subquery()
            )
        )
        or 0
    )
    if stale_hot:
        insights.append(
            Insight(
                key="hot_without_followup",
                severity="warning",
                title=f"{stale_hot} hot lead(s) have no pending follow-up",
                detail="These leads have a high predicted conversion chance but nothing scheduled. "
                "Generate follow-up drafts for them.",
            )
        )

    if ov.overdue_follow_ups:
        insights.append(
            Insight(
                key="overdue_follow_ups",
                severity="warning",
                title=f"{ov.overdue_follow_ups} follow-up(s) are overdue",
                detail=f"{ov.pending_follow_ups} follow-ups are pending in total; clear the overdue ones first.",
            )
        )

    unscored = (
        db.scalar(
            select(func.count()).select_from(
                lead_service.visible_leads(user)
                .where(Lead.latest_probability.is_(None), Lead.status.in_(OPEN_STATUSES))
                .subquery()
            )
        )
        or 0
    )
    if unscored:
        insights.append(
            Insight(
                key="unscored_leads",
                severity="info",
                title=f"{unscored} open lead(s) have not been scored",
                detail="Run the AI pipeline (or score them individually) to prioritise them.",
            )
        )

    series = monthly(db, user, months=3)
    if len(series) == 3 and series[1].leads:
        change = (series[1].leads - series[0].leads) / series[0].leads if series[0].leads else None
        if change is not None:
            insights.append(
                Insight(
                    key="lead_volume_trend",
                    severity="positive" if change >= 0 else "warning",
                    title=f"Lead volume {'up' if change >= 0 else 'down'} {abs(change):.0%} last month",
                    detail=f"{series[1].leads} leads in {series[1].month} versus {series[0].leads} in {series[0].month}.",
                )
            )

    cutoff = now - timedelta(days=30)
    recent_lost = (
        db.scalar(
            select(func.count()).select_from(
                lead_service.visible_leads(user)
                .where(Lead.status == LeadStatus.LOST, Lead.updated_at >= cutoff)
                .subquery()
            )
        )
        or 0
    )
    if recent_lost:
        insights.append(
            Insight(
                key="recent_losses",
                severity="info",
                title=f"{recent_lost} lead(s) marked lost in the last 30 days",
                detail="Review their interaction history for common reasons (price, timing, location).",
            )
        )

    if ov.synthetic_leads:
        insights.append(
            Insight(
                key="synthetic_data",
                severity="info",
                title="Figures include synthetic demo data",
                detail=f"{ov.synthetic_leads} of {ov.total_leads} leads are synthetic. "
                "Do not read these numbers as real business performance.",
            )
        )
    return insights


def _label(source: str) -> str:
    return source.replace("_", " ").title()


def insights_with_narrative(db: Session, user: User, *, use_llm: bool = True) -> InsightsResponse:
    insights = build_insights(db, user)
    narrative = None
    if use_llm and insights:
        facts = "\n".join(f"- {i.title}: {i.detail}" for i in insights)
        narrative = llm.safe_complete(
            system=(
                "You are a sales analyst. Summarise the facts below for a sales manager in at most "
                "90 words. Use only these facts; do not add numbers or causes that are not listed."
            ),
            prompt=facts,
            max_tokens=250,
        )
    synthetic = any(i.key == "synthetic_data" for i in insights)
    return InsightsResponse(
        insights=insights,
        narrative=narrative,
        narrative_source="llm" if narrative else "none",
        data_is_synthetic=synthetic,
    )
