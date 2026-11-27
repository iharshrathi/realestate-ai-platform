from datetime import timedelta

import jwt

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.enums import UserRole
from tests import factories


def login(client, email, password=factories.PASSWORD):
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


def test_login_success_returns_token_and_user(client, agent):
    response = login(client, "agent@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "agent"
    assert "hashed_password" not in body["user"]


def test_login_is_case_insensitive_on_email(client, agent):
    assert login(client, "AGENT@Example.com").status_code == 200


def test_login_wrong_password_and_unknown_user_look_identical(client, agent):
    wrong = login(client, "agent@example.com", "nope-nope-nope")
    unknown = login(client, "ghost@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_inactive_user_cannot_log_in(client, db):
    factories.make_user(db, "off@example.com", UserRole.AGENT, active=False)
    assert login(client, "off@example.com").status_code == 401


def test_me_requires_a_valid_token(client, agent_h):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code
        == 401
    )
    ok = client.get("/api/v1/auth/me", headers=agent_h)
    assert ok.status_code == 200 and ok.json()["email"] == "agent@example.com"


def test_expired_token_is_rejected(client, agent):
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(agent.id), "exp": utcnow() - timedelta(minutes=1)},
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_token_signed_with_other_key_is_rejected(client, agent):
    token = jwt.encode(
        {"sub": str(agent.id), "exp": utcnow() + timedelta(hours=1)}, "x" * 40, algorithm="HS256"
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_deactivated_user_token_stops_working(client, db, agent, agent_h):
    agent.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me", headers=agent_h).status_code == 401


def test_role_based_access_to_user_management(client, admin_h, manager_h, agent_h):
    assert client.get("/api/v1/users", headers=agent_h).status_code == 403
    assert client.get("/api/v1/users", headers=manager_h).status_code == 200
    payload = {
        "email": "new@example.com",
        "full_name": "New Agent",
        "password": "LongEnough123!",
        "role": "agent",
    }
    assert client.post("/api/v1/users", json=payload, headers=manager_h).status_code == 403
    created = client.post("/api/v1/users", json=payload, headers=admin_h)
    assert created.status_code == 201
    assert client.post("/api/v1/users", json=payload, headers=admin_h).status_code == 409


def test_user_creation_validates_input(client, admin_h):
    bad = {"email": "not-an-email", "full_name": "X", "password": "short"}
    assert client.post("/api/v1/users", json=bad, headers=admin_h).status_code == 422


def test_admin_can_deactivate_user(client, admin_h, agent):
    response = client.patch(f"/api/v1/users/{agent.id}", json={"is_active": False}, headers=admin_h)
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert login(client, "agent@example.com").status_code == 401
