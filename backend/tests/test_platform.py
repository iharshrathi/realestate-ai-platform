"""Cross-cutting concerns: health, rate limiting, error handling, config, seeding, schema."""

import pytest
from sqlalchemy import func, select

from app.core.config import INSECURE_DEFAULT_SECRET, Settings, get_settings
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.models import (
    AgentLog,
    CustomerRequirement,
    FollowUp,
    Lead,
    LeadInteraction,
    MarketingCampaign,
    Prediction,
    Property,
    User,
)


def test_health_check(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_security_and_correlation_headers(client):
    response = client.get("/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_login_is_rate_limited(client, agent, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_login_per_minute", 3)
    attempts = [
        client.post(
            "/api/v1/auth/login",
            data={"username": "agent@example.com", "password": "wrong-password"},
        ).status_code
        for _ in range(5)
    ]
    assert attempts == [401, 401, 401, 429, 429]


def test_chatbot_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_chat_per_minute", 2)
    body = {"messages": [{"role": "user", "content": "hello"}]}
    codes = [client.post("/api/v1/chatbot/message", json=body).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]


def test_global_rate_limit_applies_to_api_routes(client, monkeypatch):
    # the middleware captured the settings object at start-up, so mutate the same instance
    monkeypatch.setattr(get_settings(), "rate_limit_global_per_minute", 2)
    codes = [client.get("/api/v1/auth/me").status_code for _ in range(4)]
    assert codes == [401, 401, 429, 429]
    assert client.get("/health").status_code == 200  # probes are not limited


def test_unexpected_errors_are_hidden_from_clients(db, agent_h, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routers import ai
    from app.main import app

    def boom(*_, **__):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(ai.chatbot_service, "handle_message", boom)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/chatbot/message", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 500
    assert "secret" not in response.text and response.json()["detail"] == "Internal server error"
    assert response.json()["request_id"]


def test_malformed_json_and_unknown_routes(client, agent_h):
    assert (
        client.post(
            "/api/v1/leads",
            content="{not json",
            headers={**agent_h, "content-type": "application/json"},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/does-not-exist", headers=agent_h).status_code == 404


def test_production_refuses_insecure_secret(monkeypatch):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(environment="production", secret_key=INSECURE_DEFAULT_SECRET)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="short")
    Settings(environment="production", secret_key="x" * 40)  # fine


def test_threshold_order_is_validated():
    with pytest.raises(ValueError, match="WARM_THRESHOLD"):
        Settings(hot_threshold=0.3, warm_threshold=0.5)


def test_all_nine_required_tables_exist():
    assert set(Base.metadata.tables) == {
        "users", "leads", "properties", "customer_requirements", "lead_interactions",
        "follow_ups", "predictions", "marketing_campaigns", "agent_logs",
    }  # fmt: skip


def test_database_constraints_reject_bad_rows(db):
    from sqlalchemy.exc import IntegrityError

    from app.models.enums import LeadSource

    cases = [
        Lead(full_name="No contact", source=LeadSource.DIRECT),  # contact_required
        Property(
            title="Free house", location="X", property_type="plot", price_inr=0
        ),  # price_positive
        CustomerRequirement(lead_id=999, budget_max=1),  # FK to a missing lead
    ]
    for row in cases:
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_deleting_a_lead_cascades_to_children(db, agent, properties, trained_model):
    from app.services import scoring_service
    from tests import factories

    lead = factories.make_lead(db, assigned_to=agent, interactions=2, requirement={"budget_max": 1})
    scoring_service.score_lead(db, lead)
    db.add(FollowUp(lead_id=lead.id, channel="call"))
    db.commit()
    db.delete(lead)
    db.commit()
    for model in (CustomerRequirement, LeadInteraction, Prediction, FollowUp):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_seed_creates_clearly_synthetic_data(db, trained_model):
    counts = seed_demo_data(db, n_leads=60)
    assert (
        counts["users"] == 5
        and counts["leads"] == 60
        and counts["properties"] > 20
        and counts["scored"] > 10
    )
    for model in (Lead, Property, MarketingCampaign):
        assert (
            db.scalar(select(func.count()).select_from(model).where(model.is_synthetic.is_(False)))
            == 0
        )
    assert db.scalar(select(func.count(Lead.id)).where(Lead.email.not_like("%@example.com"))) == 0
    assert db.scalar(select(func.count(Prediction.id))) == counts["scored"]
    converted = db.scalar(select(func.count(Lead.id)).where(Lead.status == "converted"))
    assert 0 < converted < 40
    assert db.scalar(select(func.count(AgentLog.id))) == 0  # seeding is not an agent action
    admin = db.scalars(select(User).where(User.email == "admin@example.com")).one()
    assert admin.hashed_password != get_settings().seed_password.get_secret_value()  # stored hashed


def test_seed_is_usable_through_the_api(client, db, trained_model):
    seed_demo_data(db, n_leads=60)
    token = client.post(
        "/api/v1/auth/login", data={"username": "manager@example.com", "password": "TestPassw0rd!"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/leads", headers=headers).json()["total"] == 60
    assert client.get("/api/v1/analytics/overview", headers=headers).json()["synthetic_leads"] == 60
    lead_id = client.get("/api/v1/leads", params={"band": "hot"}, headers=headers).json()["items"][
        0
    ]["id"]
    detail = client.get(f"/api/v1/leads/{lead_id}", headers=headers).json()
    assert detail["latest_prediction"]["factors"] and detail["requirement"]
