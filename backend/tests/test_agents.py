"""LangGraph agent workflows, audit logging and the human-approval boundary."""

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import AgentLog, CustomerRequirement, FollowUp, Lead
from app.services import scoring_service
from tests import factories

IDENTITY_FIELDS = (
    "id",
    "full_name",
    "email",
    "phone",
    "source",
    "status",
    "campaign_id",
    "assigned_to_id",
    "is_synthetic",
)


def _identity(lead):
    return {name: getattr(lead, name) for name in IDENTITY_FIELDS}


MESSAGE = "I'm looking for a 2 BHK apartment in Baner under 90 lakh, want to buy within 2 months"


def run(client, lead, headers, message=None):
    response = client.post(
        f"/api/v1/agents/leads/{lead.id}/run", json={"message": message}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_pipeline_runs_all_agents_in_order(client, db, agent, agent_h, properties, trained_model):
    lead = factories.make_lead(
        db,
        assigned_to=agent,
        interactions=5,
        requirement={"budget_max": 8_500_000, "preferred_location": "Baner"},
    )
    result = run(client, lead, agent_h, MESSAGE)

    agents = [s["agent"] for s in result["steps"]]
    # cold leads skip the recommendation agent, hot/warm leads include it
    expected = [
        "lead_qualification_agent",
        "lead_scoring_agent",
        "property_recommendation_agent",
        "follow_up_agent",
    ]
    assert agents == expected or agents == [
        a for a in expected if a != "property_recommendation_agent"
    ]
    assert all(s["status"] == "success" for s in result["steps"])
    assert (
        result["requirement"]["budget_max"] == 9_000_000
        and result["requirement"]["intent"] == "purchase_enquiry"
    )
    assert result["prediction"]["band"] in {"hot", "warm", "cold"}
    assert result["follow_up"]["status"] == "draft"
    assert result["errors"] == []


def test_conditional_routing_by_score_band(
    client, db, agent, agent_h, properties, trained_model, monkeypatch
):
    lead = factories.make_lead(
        db,
        assigned_to=agent,
        requirement={
            "budget_max": 8_500_000,
            "preferred_location": "Baner",
            "property_type": "apartment",
        },
    )
    real_score = scoring_service.score_lead

    def force(band_probability):
        def fake(db_, lead_):
            from app.models.enums import ScoreBand

            prediction = real_score(db_, lead_)
            prediction.band = ScoreBand.HOT if band_probability > 0.5 else ScoreBand.COLD
            return prediction

        return fake

    from app.agents import lead_graph

    monkeypatch.setattr(lead_graph.scoring_service, "score_lead", force(0.9))
    hot_agents = [s["agent"] for s in run(client, lead, agent_h)["steps"]]
    assert "property_recommendation_agent" in hot_agents

    monkeypatch.setattr(lead_graph.scoring_service, "score_lead", force(0.1))
    cold_agents = [s["agent"] for s in run(client, lead, agent_h)["steps"]]
    assert (
        "property_recommendation_agent" not in cold_agents and cold_agents[-1] == "follow_up_agent"
    )


def test_agents_cannot_send_messages_or_change_business_records(
    client, db, agent, agent_h, properties, trained_model
):
    """The write boundary: agents only append requirements/predictions/logs and create DRAFTS."""
    lead = factories.make_lead(db, name="Rohan Mehta", assigned_to=agent, interactions=3)
    before = _identity(lead)
    interactions_before = len(lead.interactions)

    run(client, lead, agent_h, MESSAGE)
    run(client, lead, agent_h, MESSAGE)  # re-running must not pile up drafts or escalate anything

    db.expire_all()
    fresh = db.get(Lead, lead.id)
    after = _identity(fresh)
    assert after == before  # status, assignment, contact details untouched
    assert len(fresh.interactions) == interactions_before  # nothing was "sent" or logged as sent

    follow_ups = db.scalars(select(FollowUp).where(FollowUp.lead_id == lead.id)).all()
    assert len(follow_ups) == 1  # idempotent draft
    assert (
        follow_ups[0].status.value == "draft"
        and follow_ups[0].approved_by_id is None
        and follow_ups[0].sent_at is None
    )
    # the only way forward is a human approval
    assert (
        client.post(f"/api/v1/follow-ups/{follow_ups[0].id}/complete", headers=agent_h).status_code
        == 409
    )


def test_nlp_requirements_are_appended_not_overwritten(client, db, agent, agent_h, trained_model):
    lead = factories.make_lead(
        db,
        assigned_to=agent,
        requirement={"budget_max": 5_000_000, "preferred_location": "Wakad", "bedrooms": 1},
    )
    run(client, lead, agent_h, "Actually I want a 3 BHK in Baner")
    rows = db.scalars(
        select(CustomerRequirement)
        .where(CustomerRequirement.lead_id == lead.id)
        .order_by(CustomerRequirement.id)
    ).all()
    assert len(rows) == 2
    assert (rows[0].preferred_location, rows[0].bedrooms) == (
        "Wakad",
        1,
    )  # the human entry is preserved
    assert rows[1].source.value == "nlp" and (rows[1].preferred_location, rows[1].bedrooms) == (
        "Baner",
        3,
    )
    assert rows[1].budget_max == 5_000_000  # fields not mentioned are carried over


def test_every_step_is_audited(client, db, agent, agent_h, manager_h, properties, trained_model):
    lead = factories.make_lead(db, assigned_to=agent, interactions=2)
    result = run(client, lead, agent_h, MESSAGE)
    logs = db.scalars(
        select(AgentLog).where(AgentLog.run_id == result["run_id"]).order_by(AgentLog.id)
    ).all()
    assert [log.agent_name for log in logs] == [s["agent"] for s in result["steps"]]
    assert all(
        log.lead_id == lead.id and log.triggered_by_id == agent.id and log.duration_ms >= 0
        for log in logs
    )
    assert logs[0].input_summary["message"].startswith("I'm looking")

    api = client.get(
        "/api/v1/agents/logs", params={"run_id": result["run_id"]}, headers=manager_h
    ).json()
    assert api["total"] == len(logs)
    assert (
        client.get("/api/v1/agents/logs", headers=agent_h).status_code == 403
    )  # audit log is for managers


def test_pipeline_degrades_gracefully_without_a_model(
    client, db, agent, agent_h, manager_h, monkeypatch, tmp_path, properties
):
    monkeypatch.setattr(get_settings(), "model_path", tmp_path / "missing.joblib")
    lead = factories.make_lead(db, assigned_to=agent, interactions=2)
    result = run(client, lead, agent_h, MESSAGE)
    assert result["prediction"] is None and result["follow_up"]["status"] == "draft"
    assert any("scoring" in e for e in result["errors"])
    statuses = {s["agent"]: s["status"] for s in result["steps"]}
    assert statuses["lead_scoring_agent"] == "failed" and statuses["follow_up_agent"] == "success"
    failed = client.get(
        "/api/v1/agents/logs", params={"run_id": result["run_id"]}, headers=manager_h
    ).json()["items"]
    assert any(item["status"] == "failed" and item["error"] for item in failed)


def test_a_crashing_agent_does_not_break_the_run(
    client, db, agent, agent_h, trained_model, monkeypatch
):
    from app.agents import lead_graph

    def boom(*_, **__):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(lead_graph.followup_service, "suggest_follow_up", boom)
    lead = factories.make_lead(db, assigned_to=agent)
    result = run(client, lead, agent_h, MESSAGE)
    assert result["follow_up"] is None and any("database exploded" in e for e in result["errors"])
    assert result["prediction"] is not None  # earlier work is kept


def test_agents_respect_lead_visibility(client, db, other_agent, agent_h, trained_model):
    theirs = factories.make_lead(db, assigned_to=other_agent)
    assert (
        client.post(f"/api/v1/agents/leads/{theirs.id}/run", json={}, headers=agent_h).status_code
        == 404
    )
    assert db.scalar(select(func.count(AgentLog.id))) == 0


def test_sales_intelligence_agent(client, db, agent, manager_h, agent_h, trained_model):
    factories.make_lead(db, assigned_to=agent)
    assert client.post("/api/v1/agents/sales-intelligence/run", headers=agent_h).status_code == 403
    response = client.post("/api/v1/agents/sales-intelligence/run", headers=manager_h)
    assert response.status_code == 200
    body = response.json()
    assert "insights" in body and body["forecast"]["caveat"]
    names = {log.agent_name for log in db.scalars(select(AgentLog))}
    assert names == {"sales_intelligence_agent"}
