from datetime import timedelta

from app.core.time import utcnow
from app.models import FollowUp, MarketingCampaign
from app.models.enums import (
    FollowUpChannel,
    FollowUpStatus,
    LeadSource,
    LeadStatus,
    ScoreBand,
)
from tests import factories


def _populate(db, agent):
    now = utcnow()
    leads = []
    # website: 4 leads, 2 converted; newspaper: 2 leads, 0 converted
    for i in range(4):
        converted = i < 2
        leads.append(
            factories.make_lead(
                db, source=LeadSource.WEBSITE, assigned_to=agent,
                status=LeadStatus.CONVERTED if converted else LeadStatus.QUALIFIED,
                created_at=now - timedelta(days=40 + i),
                converted_at=now - timedelta(days=10) if converted else None,
                latest_probability=None if converted else 0.8, latest_band=None if converted else ScoreBand.HOT,
            )
        )  # fmt: skip
    for _ in range(2):
        leads.append(
            factories.make_lead(
                db,
                source=LeadSource.NEWSPAPER,
                status=LeadStatus.NEW,
                assigned_to=agent,
                latest_probability=0.2,
                latest_band=ScoreBand.COLD,
                is_synthetic=True,
            )
        )
    leads.append(
        factories.make_lead(db, source=LeadSource.DIRECT, status=LeadStatus.LOST, assigned_to=agent)
    )
    db.add(
        MarketingCampaign(
            name="Web", channel=LeadSource.WEBSITE, start_date=now.date(), spend_inr=100_000
        )
    )
    db.add(
        FollowUp(
            lead_id=leads[2].id,
            channel=FollowUpChannel.CALL,
            status=FollowUpStatus.APPROVED,
            due_at=now - timedelta(days=1),
        )
    )
    db.add(
        FollowUp(
            lead_id=leads[3].id,
            channel=FollowUpChannel.CALL,
            status=FollowUpStatus.DRAFT,
            due_at=now + timedelta(days=1),
        )
    )
    db.add(
        FollowUp(lead_id=leads[0].id, channel=FollowUpChannel.CALL, status=FollowUpStatus.COMPLETED)
    )
    db.commit()
    return leads


def test_overview_kpis(client, db, agent, manager_h):
    _populate(db, agent)
    body = client.get("/api/v1/analytics/overview", headers=manager_h).json()
    assert body["total_leads"] == 7
    assert body["new_leads"] == 2
    assert body["qualified_leads"] == 2
    assert body["converted_customers"] == 2
    assert body["lost_leads"] == 1
    assert body["pending_follow_ups"] == 2 and body["overdue_follow_ups"] == 1
    assert body["hot_leads"] == 2
    assert body["conversion_rate"] == round(2 / 7, 4)
    assert body["synthetic_leads"] == 2


def test_overview_is_scoped_to_what_the_user_can_see(
    client, db, agent, other_agent, agent_h, other_agent_h
):
    factories.make_lead(db, assigned_to=agent)
    factories.make_lead(db, assigned_to=other_agent)
    factories.make_lead(db, assigned_to=other_agent)
    assert client.get("/api/v1/analytics/overview", headers=agent_h).json()["total_leads"] == 1
    assert (
        client.get("/api/v1/analytics/overview", headers=other_agent_h).json()["total_leads"] == 2
    )


def test_manager_only_analytics_endpoints(client, agent_h, manager_h):
    for path in ("monthly", "channels", "forecast", "insights"):
        assert client.get(f"/api/v1/analytics/{path}", headers=agent_h).status_code == 403
        assert client.get(f"/api/v1/analytics/{path}", headers=manager_h).status_code == 200


def test_channel_comparison(client, db, agent, manager_h):
    _populate(db, agent)
    channels = {
        c["source"]: c for c in client.get("/api/v1/analytics/channels", headers=manager_h).json()
    }
    web = channels["website"]
    assert (web["leads"], web["converted"], web["conversion_rate"]) == (4, 2, 0.5)
    assert (
        web["spend_inr"] == 100_000
        and web["cost_per_lead"] == 25_000
        and web["cost_per_conversion"] == 50_000
    )
    assert web["avg_score"] == 0.8 and web["hot_share"] == 1.0
    assert (
        channels["newspaper"]["conversion_rate"] == 0
        and channels["newspaper"]["cost_per_lead"] is None
    )
    ordered = [
        c["source"] for c in client.get("/api/v1/analytics/channels", headers=manager_h).json()
    ]
    assert ordered[0] == "website"  # best converting first


def test_monthly_series_is_continuous_and_counts_leads_and_conversions(
    client, db, agent, manager_h
):
    _populate(db, agent)
    series = client.get("/api/v1/analytics/monthly", params={"months": 6}, headers=manager_h).json()
    assert len(series) == 6
    months = [p["month"] for p in series]
    assert months == sorted(months) and len(set(months)) == 6  # chronological, no gaps
    assert months[-1] == utcnow().strftime("%Y-%m")
    assert sum(p["leads"] for p in series) == 7
    assert sum(p["converted"] for p in series) == 2
    assert sum(p["by_source"].get("website", 0) for p in series) == 4
    assert (
        client.get("/api/v1/analytics/monthly", params={"months": 0}, headers=manager_h).status_code
        == 422
    )


def test_forecast_uses_open_lead_probabilities(client, db, agent, manager_h):
    _populate(db, agent)
    body = client.get("/api/v1/analytics/forecast", headers=manager_h).json()
    assert body["open_leads"] == 4 and body["scored_open_leads"] == 4
    assert body["expected_conversions_open_leads"] == round(0.8 * 2 + 0.2 * 2, 1)
    assert body["expected_by_band"]["hot"] == 1.6 and body["expected_by_band"]["cold"] == 0.4
    assert "synthetic" in body["caveat"].lower()


def test_forecast_with_no_history_does_not_crash(client, manager_h):
    body = client.get("/api/v1/analytics/forecast", headers=manager_h).json()
    assert body["open_leads"] == 0 and body["next_month_leads"] is None


def test_linear_forecast_helper():
    from app.services.analytics_service import _linear_forecast

    assert _linear_forecast([1, 2]) is None
    assert round(_linear_forecast([10, 20, 30, 40]), 1) == 50.0
    assert _linear_forecast([30, 20, 10]) == 0.0  # clipped at zero


def test_insights_are_backed_by_the_data(client, db, agent, manager_h):
    now = utcnow()
    # enough volume per channel for a channel insight
    for i in range(25):
        factories.make_lead(
            db,
            source=LeadSource.WEBSITE,
            status=LeadStatus.CONVERTED if i < 10 else LeadStatus.LOST,
            assigned_to=agent,
            converted_at=now if i < 10 else None,
            is_synthetic=True,
        )
    for i in range(25):
        factories.make_lead(
            db,
            source=LeadSource.FACEBOOK_ADS,
            status=LeadStatus.CONVERTED if i < 2 else LeadStatus.LOST,
            assigned_to=agent,
            converted_at=now if i < 2 else None,
            is_synthetic=True,
        )
    hot = factories.make_lead(
        db, assigned_to=agent, latest_probability=0.9, latest_band=ScoreBand.HOT
    )
    factories.make_lead(db, assigned_to=agent)  # open, never scored
    body = client.get("/api/v1/analytics/insights", headers=manager_h).json()
    by_key = {i["key"]: i for i in body["insights"]}
    assert "Website converts best" in by_key["channel_quality"]["title"]
    assert (
        "37% of 27 leads" in by_key["channel_quality"]["detail"]
        and "8% for Facebook Ads" in by_key["channel_quality"]["detail"]
    )
    assert "1 hot lead" in by_key["hot_without_followup"]["title"]
    assert "1 open lead" in by_key["unscored_leads"]["title"]
    assert body["data_is_synthetic"] is True and "synthetic_data" in by_key
    assert body["narrative"] is None and body["narrative_source"] == "none"  # no LLM configured
    assert hot.id  # silence unused warnings


def test_llm_narrative_is_optional_and_labelled(client, db, agent, manager_h, monkeypatch):
    from app.services import analytics_service

    factories.make_lead(db, assigned_to=agent, latest_probability=0.9, latest_band=ScoreBand.HOT)
    monkeypatch.setattr(
        analytics_service.llm, "safe_complete", lambda **_: "One hot lead needs a follow-up."
    )
    body = client.get("/api/v1/analytics/insights", headers=manager_h).json()
    assert (
        body["narrative"] == "One hot lead needs a follow-up." and body["narrative_source"] == "llm"
    )
