from datetime import timedelta

from app.core.time import utcnow
from app.models.enums import LeadSource, LeadStatus, ScoreBand
from tests import factories

NEW_LEAD = {
    "full_name": "Priya Sharma",
    "email": "priya@example.com",
    "phone": "+91 98765 43210",
    "source": "facebook_ads",
    "message": "Looking for a 2 BHK in Baner",
    "requirement": {
        "budget_max": 9000000,
        "preferred_location": "Baner",
        "property_type": "apartment",
    },
}


def test_create_lead_normalises_phone_and_stores_enquiry(client, agent_h, agent):
    response = client.post("/api/v1/leads", json=NEW_LEAD, headers=agent_h)
    assert response.status_code == 201
    body = response.json()
    assert body["phone"] == "+919876543210"
    assert body["status"] == "new"
    assert body["assigned_to"]["id"] == agent.id  # agents own the leads they create
    assert body["requirement"]["preferred_location"] == "Baner"
    assert body["interaction_count"] == 1


def test_create_lead_requires_contact_and_valid_fields(client, agent_h):
    assert (
        client.post(
            "/api/v1/leads", json={"full_name": "A", "source": "direct"}, headers=agent_h
        ).status_code
        == 422
    )
    bad_phone = {**NEW_LEAD, "phone": "abc"}
    assert client.post("/api/v1/leads", json=bad_phone, headers=agent_h).status_code == 422
    bad_source = {**NEW_LEAD, "source": "tv"}
    assert client.post("/api/v1/leads", json=bad_source, headers=agent_h).status_code == 422
    bad_budget = {**NEW_LEAD, "requirement": {"budget_min": 10, "budget_max": 5}}
    assert client.post("/api/v1/leads", json=bad_budget, headers=agent_h).status_code == 422


def test_duplicate_contact_is_rejected(client, agent_h):
    assert client.post("/api/v1/leads", json=NEW_LEAD, headers=agent_h).status_code == 201
    duplicate = {**NEW_LEAD, "full_name": "Someone Else", "phone": None}
    assert client.post("/api/v1/leads", json=duplicate, headers=agent_h).status_code == 409


def test_requires_authentication(client):
    assert client.get("/api/v1/leads").status_code == 401
    assert client.post("/api/v1/leads", json=NEW_LEAD).status_code == 401


def test_list_filters_sorting_and_pagination(client, db, manager_h, agent):
    now = utcnow()
    factories.make_lead(
        db,
        name="Alice A",
        source=LeadSource.WEBSITE,
        status=LeadStatus.NEW,
        created_at=now - timedelta(days=30),
    )
    factories.make_lead(
        db,
        name="Bob B",
        source=LeadSource.NEWSPAPER,
        status=LeadStatus.QUALIFIED,
        created_at=now - timedelta(days=5),
    )
    factories.make_lead(
        db,
        name="Cara C",
        source=LeadSource.NEWSPAPER,
        status=LeadStatus.CONVERTED,
        created_at=now - timedelta(days=2),
        latest_probability=0.9,
        latest_band=ScoreBand.HOT,
    )

    def ids(**params):
        response = client.get("/api/v1/leads", params=params, headers=manager_h)
        assert response.status_code == 200, response.text
        return [i["full_name"] for i in response.json()["items"]], response.json()["total"]

    assert ids()[1] == 3
    assert ids(source="newspaper")[0] == ["Cara C", "Bob B"]  # newest first by default
    assert ids(status="qualified")[0] == ["Bob B"]
    assert ids(band="hot")[0] == ["Cara C"]
    assert ids(q="alice")[0] == ["Alice A"]
    assert ids(sort_by="full_name", order="asc")[0] == ["Alice A", "Bob B", "Cara C"]
    assert ids(created_from=(now - timedelta(days=6)).date().isoformat())[0] == ["Cara C", "Bob B"]
    assert ids(created_to=(now - timedelta(days=20)).date().isoformat())[0] == ["Alice A"]
    page = client.get("/api/v1/leads", params={"page": 2, "page_size": 2}, headers=manager_h).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_search_treats_wildcards_literally(client, db, manager_h):
    factories.make_lead(db, name="Alice A")
    response = client.get("/api/v1/leads", params={"q": "%"}, headers=manager_h)
    assert response.json()["total"] == 0


def test_invalid_query_params_are_rejected(client, manager_h):
    assert (
        client.get("/api/v1/leads", params={"page_size": 1000}, headers=manager_h).status_code
        == 422
    )
    assert (
        client.get("/api/v1/leads", params={"sort_by": "password"}, headers=manager_h).status_code
        == 422
    )
    assert client.get("/api/v1/leads", params={"unknown": 1}, headers=manager_h).status_code == 422


def test_agents_only_see_their_own_and_unassigned_leads(client, db, agent, other_agent, agent_h):
    mine = factories.make_lead(db, name="Mine", assigned_to=agent)
    free = factories.make_lead(db, name="Unassigned")
    theirs = factories.make_lead(db, name="Theirs", assigned_to=other_agent)

    names = {i["full_name"] for i in client.get("/api/v1/leads", headers=agent_h).json()["items"]}
    assert names == {"Mine", "Unassigned"}
    assert client.get(f"/api/v1/leads/{mine.id}", headers=agent_h).status_code == 200
    assert client.get(f"/api/v1/leads/{free.id}", headers=agent_h).status_code == 200
    # 404 rather than 403 so lead ids cannot be probed
    assert client.get(f"/api/v1/leads/{theirs.id}", headers=agent_h).status_code == 404
    assert client.post(f"/api/v1/leads/{theirs.id}/score", headers=agent_h).status_code == 404
    assert client.get(f"/api/v1/leads/{theirs.id}/interactions", headers=agent_h).status_code == 404


def test_agent_cannot_assign_leads_to_others(client, lead, other_agent, agent_h):
    response = client.patch(
        f"/api/v1/leads/{lead.id}", json={"assigned_to_id": other_agent.id}, headers=agent_h
    )
    assert response.status_code == 403


def test_manager_can_assign_and_delete_agents_cannot(client, lead, other_agent, manager_h, agent_h):
    assert client.delete(f"/api/v1/leads/{lead.id}", headers=agent_h).status_code == 403
    assigned = client.patch(
        f"/api/v1/leads/{lead.id}", json={"assigned_to_id": other_agent.id}, headers=manager_h
    )
    assert assigned.status_code == 200 and assigned.json()["assigned_to"]["id"] == other_agent.id
    # once reassigned, the first agent can no longer see the lead at all
    assert client.get(f"/api/v1/leads/{lead.id}", headers=agent_h).status_code == 404
    assert client.delete(f"/api/v1/leads/{lead.id}", headers=manager_h).status_code == 204
    assert client.get(f"/api/v1/leads/{lead.id}", headers=manager_h).status_code == 404


def test_status_change_to_converted_sets_converted_at(client, lead, agent_h):
    converted = client.patch(
        f"/api/v1/leads/{lead.id}", json={"status": "converted"}, headers=agent_h
    ).json()
    assert converted["status"] == "converted" and converted["converted_at"] is not None
    reopened = client.patch(
        f"/api/v1/leads/{lead.id}", json={"status": "negotiation"}, headers=agent_h
    ).json()
    assert reopened["converted_at"] is None


def test_unknown_references_are_rejected(client, agent_h):
    assert (
        client.post(
            "/api/v1/leads", json={**NEW_LEAD, "campaign_id": 999}, headers=agent_h
        ).status_code
        == 404
    )


def test_interactions_are_listed_newest_first_and_first_outreach_marks_contacted(
    client, lead, agent_h
):
    first = client.post(
        f"/api/v1/leads/{lead.id}/interactions",
        json={"type": "call", "content": "Called the customer"},
        headers=agent_h,
    )
    assert first.status_code == 201 and first.json()["direction"] == "outbound"
    note = client.post(
        f"/api/v1/leads/{lead.id}/interactions",
        json={"type": "note", "content": "Prefers evenings"},
        headers=agent_h,
    )
    assert note.json()["direction"] == "internal"
    history = client.get(f"/api/v1/leads/{lead.id}/interactions", headers=agent_h).json()
    assert [h["type"] for h in history] == ["note", "call"]
    assert client.get(f"/api/v1/leads/{lead.id}", headers=agent_h).json()["status"] == "contacted"


def test_requirement_history_is_append_only(client, lead, agent_h):
    client.post(
        f"/api/v1/leads/{lead.id}/requirements", json={"budget_max": 5000000}, headers=agent_h
    )
    client.post(
        f"/api/v1/leads/{lead.id}/requirements", json={"budget_max": 7000000}, headers=agent_h
    )
    history = client.get(f"/api/v1/leads/{lead.id}/requirements", headers=agent_h).json()
    assert [h["budget_max"] for h in history] == [7000000, 5000000]
    assert (
        client.get(f"/api/v1/leads/{lead.id}", headers=agent_h).json()["requirement"]["budget_max"]
        == 7000000
    )
