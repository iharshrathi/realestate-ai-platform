import sys
import types

from pydantic import SecretStr

from app.core.config import get_settings
from app.services import llm

CAMPAIGN = {
    "name": "Monsoon Offer",
    "channel": "facebook_ads",
    "start_date": "2026-06-01",
    "spend_inr": 250000,
}


# ------------------------------------------------------------------------------ campaigns
def test_campaign_crud_and_permissions(client, agent_h, manager_h):
    assert client.post("/api/v1/campaigns", json=CAMPAIGN, headers=agent_h).status_code == 403
    created = client.post("/api/v1/campaigns", json=CAMPAIGN, headers=manager_h)
    assert created.status_code == 201 and created.json()["is_synthetic"] is False
    assert (
        client.post("/api/v1/campaigns", json=CAMPAIGN, headers=manager_h).status_code == 409
    )  # unique name
    cid = created.json()["id"]
    patched = client.patch(
        f"/api/v1/campaigns/{cid}", json={"spend_inr": 300000}, headers=manager_h
    )
    assert patched.json()["spend_inr"] == 300000
    assert (
        client.patch("/api/v1/campaigns/999", json={"spend_inr": 1}, headers=manager_h).status_code
        == 404
    )
    assert [c["name"] for c in client.get("/api/v1/campaigns", headers=agent_h).json()] == [
        "Monsoon Offer"
    ]


def test_campaign_validation(client, manager_h):
    assert (
        client.post(
            "/api/v1/campaigns", json={**CAMPAIGN, "end_date": "2026-05-01"}, headers=manager_h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/campaigns", json={**CAMPAIGN, "spend_inr": -1}, headers=manager_h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/campaigns", json={**CAMPAIGN, "channel": "radio"}, headers=manager_h
        ).status_code
        == 422
    )


def test_lead_can_be_attached_to_a_campaign(client, manager_h):
    cid = client.post("/api/v1/campaigns", json=CAMPAIGN, headers=manager_h).json()["id"]
    lead = {
        "full_name": "A B",
        "email": "ab@example.com",
        "source": "facebook_ads",
        "campaign_id": cid,
    }
    assert client.post("/api/v1/leads", json=lead, headers=manager_h).json()["campaign_id"] == cid


# ----------------------------------------------------------------------------------- LLM
def test_llm_is_disabled_by_default():
    llm.get_llm.cache_clear()
    assert get_settings().llm_enabled is False
    assert llm.get_llm() is None
    assert llm.safe_complete(system="s", prompt="p") is None


def test_json_extraction_from_model_output():
    assert llm.parse_json_object('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_object("no json here") is None
    assert llm.parse_json_object("{broken") is None
    assert llm.parse_json_object("[1, 2]") is None


class _FakeMessages:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        block = types.SimpleNamespace(type="text", text=self.behaviour)
        return types.SimpleNamespace(
            content=[block, types.SimpleNamespace(type="tool_use", text="ignored")]
        )


def _install_fake_anthropic(monkeypatch, behaviour):
    messages = _FakeMessages(behaviour)

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.kwargs, self.messages = kwargs, messages

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("sk-test"))
    llm.get_llm.cache_clear()
    return messages


def test_anthropic_client_wrapper(monkeypatch):
    messages = _install_fake_anthropic(monkeypatch, "  Hello there  ")
    try:
        assert llm.safe_complete(system="be brief", prompt="hi", max_tokens=50) == "Hello there"
        call = messages.calls[0]
        assert call["system"] == "be brief" and call["max_tokens"] == 50
        assert call["model"] == get_settings().llm_model
        assert call["messages"] == [{"role": "user", "content": "hi"}]
    finally:
        llm.get_llm.cache_clear()


def test_llm_errors_never_propagate(monkeypatch):
    _install_fake_anthropic(monkeypatch, RuntimeError("rate limited"))
    try:
        assert llm.safe_complete(system="s", prompt="p") is None
    finally:
        llm.get_llm.cache_clear()
