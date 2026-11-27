from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import FollowUp, LeadInteraction
from app.models.enums import InteractionDirection, InteractionType, LeadStatus, ScoreBand
from app.services import followup_service as fs
from tests import factories


def _suggest(client, lead, headers):
    response = client.post(f"/api/v1/leads/{lead.id}/follow-ups/suggest", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_suggested_follow_up_is_always_a_draft_and_personalised(
    client, db, agent, agent_h, properties
):
    lead = factories.make_lead(
        db, name="Rohan Mehta", assigned_to=agent,
        requirement={"budget_max": 9_000_000, "preferred_location": "Baner", "bedrooms": 2, "property_type": "apartment"},
        interactions=1,
    )  # fmt: skip
    body = _suggest(client, lead, agent_h)
    follow_up = body["follow_up"]
    assert follow_up["status"] == "draft"  # a human must approve before anything is sent
    assert follow_up["generated_by"] == "template" and follow_up["approved_by_id"] is None
    assert follow_up["message"].startswith("Hi Rohan")
    assert "Baner" in follow_up["message"] and "Orchid Park" in follow_up["message"]
    assert follow_up["priority"] in {"high", "medium", "low"} and follow_up["rationale"]
    assert body["template_key"] and [p["title"] for p in body["recommended_properties"]]
    assert follow_up["channel"] == "whatsapp"


def test_suggest_is_idempotent_for_unreviewed_drafts(client, db, lead, agent_h):
    first = _suggest(client, lead, agent_h)["follow_up"]["id"]
    second = _suggest(client, lead, agent_h)["follow_up"]["id"]
    assert first == second
    assert db.scalars(select(FollowUp).where(FollowUp.lead_id == lead.id)).all().__len__() == 1


def test_template_selection_logic(db, agent, properties):
    now = utcnow()
    fresh = factories.make_lead(db, assigned_to=agent)
    assert (
        fs.choose_template(
            fresh, intent=None, days_since_contact=None, last=None, has_properties=False
        )
        == "first_response"
    )

    visited = factories.make_lead(db, assigned_to=agent, status=LeadStatus.SITE_VISIT)
    visit = LeadInteraction(
        lead_id=visited.id,
        type=InteractionType.SITE_VISIT,
        direction=InteractionDirection.INBOUND,
        occurred_at=now,
    )
    assert (
        fs.choose_template(
            visited, intent=None, days_since_contact=1, last=visit, has_properties=True
        )
        == "post_visit_check_in"
    )

    contacted = factories.make_lead(
        db, assigned_to=agent, status=LeadStatus.CONTACTED, interactions=3
    )
    last = contacted.interactions[-1]
    assert (
        fs.choose_template(
            contacted, intent=None, days_since_contact=20, last=last, has_properties=True
        )
        == "re_engage"
    )
    assert (
        fs.choose_template(
            contacted,
            intent="financing_enquiry",
            days_since_contact=2,
            last=last,
            has_properties=True,
        )
        == "financing_help"
    )
    assert (
        fs.choose_template(
            contacted, intent="price_enquiry", days_since_contact=2, last=last, has_properties=True
        )
        == "price_discussion"
    )
    assert (
        fs.choose_template(
            contacted,
            intent="site_visit_request",
            days_since_contact=2,
            last=last,
            has_properties=True,
        )
        == "site_visit_invite"
    )


def test_priority_scoring_is_transparent(db, agent):
    hot = factories.make_lead(
        db, assigned_to=agent, latest_probability=0.8, latest_band=ScoreBand.HOT
    )
    level, reasons = fs.compute_priority(
        hot, urgency="high", days_since_contact=9, last_inbound_unanswered=True
    )
    assert (
        level.value == "high"
        and any("hot" in r for r in reasons)
        and any("9 days" in r for r in reasons)
    )
    cold = factories.make_lead(
        db, assigned_to=agent, latest_probability=0.05, latest_band=ScoreBand.COLD
    )
    level, _ = fs.compute_priority(
        cold, urgency=None, days_since_contact=0, last_inbound_unanswered=False
    )
    assert level.value == "low"


def test_approval_workflow_end_to_end(client, db, lead, agent, agent_h):
    follow_up = _suggest(client, lead, agent_h)["follow_up"]
    fid = follow_up["id"]

    # cannot be completed/"sent" while still a draft
    assert client.post(f"/api/v1/follow-ups/{fid}/complete", headers=agent_h).status_code == 409

    approved = client.post(f"/api/v1/follow-ups/{fid}/approve", headers=agent_h).json()
    assert approved["status"] == "approved" and approved["approved_by_id"] == agent.id
    assert (
        client.post(f"/api/v1/follow-ups/{fid}/approve", headers=agent_h).status_code == 409
    )  # not twice

    pending = client.get("/api/v1/follow-ups", params={"group": "pending"}, headers=agent_h).json()
    assert [f["id"] for f in pending["items"]] == [fid]

    done = client.post(f"/api/v1/follow-ups/{fid}/complete", headers=agent_h).json()
    assert done["status"] == "sent" and done["sent_at"]
    assert (
        client.get("/api/v1/follow-ups", params={"group": "pending"}, headers=agent_h).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/v1/follow-ups", params={"group": "completed"}, headers=agent_h).json()[
            "total"
        ]
        == 1
    )

    # the outreach is logged on the lead's activity history and moves NEW -> CONTACTED
    db.expire_all()
    logged = db.scalars(select(LeadInteraction).where(LeadInteraction.lead_id == lead.id)).all()
    assert any(i.direction.value == "outbound" and i.content == done["message"] for i in logged)
    assert client.get(f"/api/v1/leads/{lead.id}", headers=agent_h).json()["status"] == "contacted"


def test_editing_an_approved_ai_draft_requires_reapproval(client, lead, agent_h):
    fid = _suggest(client, lead, agent_h)["follow_up"]["id"]
    client.post(f"/api/v1/follow-ups/{fid}/approve", headers=agent_h)
    edited = client.patch(
        f"/api/v1/follow-ups/{fid}", json={"message": "Hi, new wording"}, headers=agent_h
    ).json()
    assert (
        edited["status"] == "draft"
        and edited["approved_by_id"] is None
        and edited["message"] == "Hi, new wording"
    )


def test_reject_and_finalised_items_cannot_change(client, lead, agent_h):
    fid = _suggest(client, lead, agent_h)["follow_up"]["id"]
    assert (
        client.post(f"/api/v1/follow-ups/{fid}/reject", headers=agent_h).json()["status"]
        == "rejected"
    )
    assert client.post(f"/api/v1/follow-ups/{fid}/approve", headers=agent_h).status_code == 409
    assert (
        client.patch(
            f"/api/v1/follow-ups/{fid}", json={"message": "x"}, headers=agent_h
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/follow-ups", params={"group": "rejected"}, headers=agent_h).json()[
            "total"
        ]
        == 1
    )


def test_manual_follow_up_by_a_human_is_approved_immediately(client, lead, agent, agent_h):
    response = client.post(
        f"/api/v1/leads/{lead.id}/follow-ups",
        json={"channel": "call", "message": "Call at 6pm", "priority": "high"},
        headers=agent_h,
    )
    assert response.status_code == 201
    body = response.json()
    assert (
        body["generated_by"] == "human"
        and body["status"] == "approved"
        and body["approved_by_id"] == agent.id
    )
    done = client.post(f"/api/v1/follow-ups/{body['id']}/complete", headers=agent_h).json()
    assert done["status"] == "completed"  # calls are "completed", messages are "sent"


def test_follow_up_access_follows_lead_visibility(client, db, other_agent, agent_h, other_agent_h):
    theirs = factories.make_lead(db, assigned_to=other_agent)
    fid = _suggest(client, theirs, other_agent_h)["follow_up"]["id"]
    assert client.post(f"/api/v1/follow-ups/{fid}/approve", headers=agent_h).status_code == 404
    assert client.get("/api/v1/follow-ups", headers=agent_h).json()["total"] == 0
    assert (
        client.post(f"/api/v1/leads/{theirs.id}/follow-ups/suggest", headers=agent_h).status_code
        == 404
    )


def test_pending_list_is_sorted_by_priority(client, db, agent, agent_h):
    now = utcnow()
    low = factories.make_lead(db, assigned_to=agent)
    high = factories.make_lead(db, assigned_to=agent)
    for lead, priority in ((low, "low"), (high, "high")):
        client.post(
            f"/api/v1/leads/{lead.id}/follow-ups",
            json={
                "channel": "call",
                "priority": priority,
                "due_at": (now + timedelta(days=1)).isoformat(),
            },
            headers=agent_h,
        )
    items = client.get("/api/v1/follow-ups", headers=agent_h).json()["items"]
    assert [i["priority"] for i in items] == ["high", "low"]


# ---------------------------------------------------------------- LLM guardrails
def test_llm_text_with_invented_numbers_or_links_is_rejected():
    facts = "Hi Rohan, a 2 BHK in Baner for ₹85 L. – Agent"
    assert fs.llm_message_is_grounded("Hi Rohan, I found a 2 BHK in Baner for ₹85 L.", facts)
    assert not fs.llm_message_is_grounded("Hi Rohan, 10% discount on the 2 BHK today!", facts)
    assert not fs.llm_message_is_grounded("Hi Rohan, ₹60 L is the price", facts)
    assert not fs.llm_message_is_grounded("See https://evil.example/deal", facts)
    assert not fs.llm_message_is_grounded("   ", facts)


def _enable_llm(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", type(settings.secret_key)("fake"))


def test_grounded_llm_message_is_used_and_labelled(client, db, agent, agent_h, monkeypatch):
    _enable_llm(monkeypatch)
    lead = factories.make_lead(db, name="Rohan Mehta", assigned_to=agent)
    monkeypatch.setattr(
        fs.llm,
        "safe_complete",
        lambda **_: "Hi Rohan, hope you are well! Happy to help whenever you are ready. – Agent",
    )
    follow_up = _suggest(client, lead, agent_h)["follow_up"]
    assert follow_up["generated_by"] == "llm" and follow_up["status"] == "draft"


def test_ungrounded_llm_message_falls_back_to_template(client, db, agent, agent_h, monkeypatch):
    _enable_llm(monkeypatch)
    lead = factories.make_lead(db, name="Rohan Mehta", assigned_to=agent)
    monkeypatch.setattr(
        fs.llm, "safe_complete", lambda **_: "Hi Rohan, flat 25% off if you book today!"
    )
    follow_up = _suggest(client, lead, agent_h)["follow_up"]
    assert follow_up["generated_by"] == "template" and "25%" not in follow_up["message"]


def test_llm_outage_falls_back_to_template(client, db, agent, agent_h, monkeypatch):
    _enable_llm(monkeypatch)
    lead = factories.make_lead(db, name="Rohan Mehta", assigned_to=agent)
    monkeypatch.setattr(fs.llm, "safe_complete", lambda **_: None)
    assert _suggest(client, lead, agent_h)["follow_up"]["generated_by"] == "template"


def test_customer_request_outranks_past_site_visit(db, agent, properties):
    """If the customer wrote last asking for something, answer that rather than a generic check-in."""
    lead = factories.make_lead(db, assigned_to=agent, status=LeadStatus.SITE_VISIT, interactions=1)
    asked = LeadInteraction(
        lead_id=lead.id,
        type=InteractionType.WHATSAPP,
        direction=InteractionDirection.INBOUND,
        occurred_at=utcnow(),
    )
    assert (
        fs.choose_template(
            lead, intent="site_visit_request", days_since_contact=0, last=asked, has_properties=True
        )
        == "site_visit_invite"
    )
    assert (
        fs.choose_template(
            lead, intent="price_enquiry", days_since_contact=0, last=asked, has_properties=True
        )
        == "price_discussion"
    )
    visit = LeadInteraction(
        lead_id=lead.id,
        type=InteractionType.SITE_VISIT,
        direction=InteractionDirection.INBOUND,
        occurred_at=utcnow(),
    )
    assert (
        fs.choose_template(
            lead, intent="site_visit_request", days_since_contact=0, last=visit, has_properties=True
        )
        == "post_visit_check_in"
    )
