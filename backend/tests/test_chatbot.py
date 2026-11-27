from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Lead, LeadInteraction, Property
from app.models.enums import PropertyStatus
from app.services import chatbot_service as bot
from app.services import llm

URL = "/api/v1/chatbot/message"


def chat(client, text, collected=None, consent=False, history=None):
    messages = [*(history or []), {"role": "user", "content": text}]
    response = client.post(
        URL,
        json={"messages": messages, "collected": collected or {}, "consent_to_contact": consent},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _enable_llm(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", type(settings.secret_key)("fake"))


def test_chatbot_is_public_and_validates_input(client):
    assert client.post(URL, json={"messages": []}).status_code == 422
    assert (
        client.post(URL, json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code
        == 422
    )
    assert (
        client.post(URL, json={"messages": [{"role": "user", "content": "x" * 5000}]}).status_code
        == 422
    )
    assert (
        client.post(URL, json={"messages": [{"role": "system", "content": "hi"}]}).status_code
        == 422
    )


def test_recommendations_come_only_from_real_available_listings(client, db, properties):
    sold = db.get(Property, properties[1].id)
    sold.status = PropertyStatus.SOLD
    db.commit()

    body = chat(client, "I'm looking for a 2 BHK apartment in Baner under 90 lakh")
    assert body["mode"] == "rules"
    ids = [r["property"]["id"] for r in body["recommendations"]]
    assert ids and ids[0] == properties[0].id
    assert properties[1].id not in ids  # sold listings are never offered
    real_available = set(
        db.scalars(select(Property.id).where(Property.status == PropertyStatus.AVAILABLE))
    )
    assert set(ids) <= real_available
    assert f"[P{ids[0]}]" in body["reply"] and set(body["cited_property_ids"]) <= set(ids)
    assert (
        body["collected"]["budget_max"] == 9_000_000
        and body["collected"]["preferred_location"] == "Baner"
    )
    assert "email" not in body["recommendations"][0]["property"]  # public subset only


def test_chatbot_does_not_invent_listings(client, properties):
    body = chat(client, "Do you have a villa in Hinjewadi under 50 lakh?")
    assert body["recommendations"] == []
    assert "couldn't find" in body["reply"].lower()
    assert "[P" not in body["reply"]


def test_chatbot_asks_for_missing_details_in_order(client, properties):
    first = chat(client, "Hello, I want to buy a flat")
    assert "budget" in first["reply"].lower()
    second = chat(client, "around 90 lakh", collected=first["collected"])
    assert "area or locality" in second["reply"].lower()


def test_lead_requires_explicit_consent_and_is_created_once(client, db, properties):
    profile = {
        "budget_max": 9_000_000,
        "preferred_location": "Baner",
        "property_type": "apartment",
        "purchase_timeline_days": 60,
    }
    text = "My name is Priya Sharma and my number is 98765 43210"

    no_consent = chat(client, text, collected=profile, consent=False)
    assert no_consent["lead_saved"] is False and "consent" in no_consent["reply"].lower()
    assert db.scalar(select(func.count(Lead.id))) == 0

    saved = chat(client, text, collected=profile, consent=True)
    assert saved["lead_saved"] is True and saved["collected"]["lead_saved"] is True
    lead = db.scalars(select(Lead)).one()
    assert (
        lead.full_name == "Priya Sharma"
        and lead.phone == "9876543210"
        and lead.source.value == "website"
    )
    assert lead.status.value == "new" and lead.assigned_to_id is None
    db.refresh(lead)
    assert (
        lead.requirements[0].source.value == "chatbot"
        and lead.requirements[0].budget_max == 9_000_000
    )
    assert any("chatbot" in i.content.lower() for i in lead.interactions)

    # a later message from the same session does not create another lead
    again = chat(client, "thanks!", collected=saved["collected"], consent=True)
    assert again["lead_saved"] is True and db.scalar(select(func.count(Lead.id))) == 1


def test_returning_visitor_is_attached_to_the_existing_lead(client, db, properties):
    profile = {"budget_max": 9_000_000, "preferred_location": "Baner"}
    text = "I'm Priya Sharma, phone 98765 43210"
    chat(client, text, collected=profile, consent=True)
    chat(client, text, collected=profile, consent=True)  # new browser session, same person
    assert db.scalar(select(func.count(Lead.id))) == 1
    assert db.scalar(select(func.count(LeadInteraction.id))) == 2


def test_unqualified_enquiry_is_not_saved(client, db):
    body = chat(client, "My name is Priya Sharma and my number is 98765 43210", consent=True)
    assert body["lead_saved"] is False and db.scalar(select(func.count(Lead.id))) == 0


def test_not_interested_visitors_are_never_saved(client, db, properties):
    profile = {"budget_max": 9_000_000, "name": "Priya Sharma", "phone": "9876543210"}
    body = chat(client, "Not interested, stop messaging me", collected=profile, consent=True)
    assert body["lead_saved"] is False and db.scalar(select(func.count(Lead.id))) == 0


def test_llm_answer_citing_unknown_listing_is_discarded(client, properties, monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(
        llm, "safe_complete", lambda **_: "Great news: [P9999] is a lovely penthouse for ₹1 Cr!"
    )
    body = chat(client, "2 BHK apartment in Baner under 90 lakh")
    assert (
        body["mode"] == "rules" and "9999" not in body["reply"] and "penthouse" not in body["reply"]
    )


def test_grounded_llm_answer_is_used(client, properties, monkeypatch):
    _enable_llm(monkeypatch)
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return (
            f"I recommend [P{properties[0].id}] since it fits your budget. When do you plan to buy?"
        )

    monkeypatch.setattr(llm, "safe_complete", fake)
    body = chat(client, "2 BHK apartment in Baner under 90 lakh")
    assert body["mode"] == "llm" and body["cited_property_ids"] == [properties[0].id]
    # the prompt only contains verified listings and tells the model not to invent any
    assert "Orchid Park" in captured["prompt"] and "Riverstone Villa" not in captured["prompt"]
    assert "ONLY" in captured["system"] and "Never invent" in captured["system"]


def test_llm_failure_falls_back_to_rules(client, properties, monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(llm, "safe_complete", lambda **_: None)
    assert chat(client, "2 BHK apartment in Baner")["mode"] == "rules"


def test_profile_merge_prefers_newer_budget():
    from app.schemas.chat import CollectedProfile
    from app.services import nlp_service

    old = CollectedProfile(budget_min=5_000_000, budget_max=7_000_000)
    extracted = nlp_service.extract_requirements("actually my budget is 1 crore", use_llm=False)
    merged = bot.merge_profile(old, extracted, nlp_service.ContactDetails())
    assert (merged.budget_min, merged.budget_max) == (None, 10_000_000)
