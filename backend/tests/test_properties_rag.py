from app.models.enums import PropertyStatus, PropertyType
from app.schemas.property import PropertyCreate
from app.services import property_service
from app.services.rag_service import property_index
from app.services.recommendation_service import Criteria, recommend

NEW_PROPERTY = {
    "title": "Maple Grove 2 BHK",
    "location": "Wakad",
    "property_type": "apartment",
    "price_inr": 7_500_000,
    "bedrooms": 2,
    "description": "Quiet society with a lake view",
    "amenities": ["gym"],
}


def test_property_crud_and_permissions(client, manager_h, agent_h):
    assert client.post("/api/v1/properties", json=NEW_PROPERTY, headers=agent_h).status_code == 403
    created = client.post("/api/v1/properties", json=NEW_PROPERTY, headers=manager_h)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert (
        client.get(f"/api/v1/properties/{pid}", headers=agent_h).json()["title"]
        == "Maple Grove 2 BHK"
    )
    patched = client.patch(f"/api/v1/properties/{pid}", json={"status": "sold"}, headers=manager_h)
    assert patched.json()["status"] == "sold"
    assert client.delete(f"/api/v1/properties/{pid}", headers=agent_h).status_code == 403
    assert client.delete(f"/api/v1/properties/{pid}", headers=manager_h).status_code == 204
    assert client.get(f"/api/v1/properties/{pid}", headers=agent_h).status_code == 404


def test_property_validation(client, manager_h):
    for bad in (
        {**NEW_PROPERTY, "price_inr": 0},
        {**NEW_PROPERTY, "property_type": "castle"},
        {**NEW_PROPERTY, "title": "x"},
    ):
        assert client.post("/api/v1/properties", json=bad, headers=manager_h).status_code == 422


def test_property_list_filters(client, properties, agent_h):
    def count(**params):
        return client.get("/api/v1/properties", params=params, headers=agent_h).json()["total"]

    assert count() == 4
    assert count(property_type="apartment") == 2
    assert count(location="baner") == 2
    assert count(max_price=9_000_000) == 2


def test_recommendations_rank_by_fit_and_explain_why(db, properties):
    recs = recommend(
        db,
        Criteria(
            budget_max=9_000_000, location="Baner", property_type=PropertyType.APARTMENT, bedrooms=2
        ),
    )
    assert recs[0].property.title == "Orchid Park 2 BHK" and recs[0].match_score > 0.95
    assert "within budget" in recs[0].reasons and "in Baner" in recs[0].reasons
    scores = [r.match_score for r in recs]
    assert scores == sorted(scores, reverse=True)
    # the 3 BHK at 12.5M is ~39% over the 9M ceiling -> never shown
    assert "Skyline 3 BHK" not in [r.property.title for r in recs]


def test_slightly_over_budget_gets_partial_credit(db, properties):
    recs = recommend(
        db, Criteria(budget_max=11_000_000, location="Baner", property_type=PropertyType.APARTMENT)
    )
    by_title = {r.property.title: r for r in recs}
    skyline = by_title["Skyline 3 BHK"]  # 13.6% above budget
    assert any("above budget" in reason for reason in skyline.reasons)
    assert skyline.match_score < by_title["Orchid Park 2 BHK"].match_score


def test_sold_and_held_listings_are_never_recommended(db, properties):
    properties[0].status = PropertyStatus.SOLD
    properties[1].status = PropertyStatus.ON_HOLD
    db.commit()
    recs = recommend(db, Criteria(location="Baner", property_type=PropertyType.APARTMENT))
    assert recs == []


def test_listing_must_match_location_or_type(db, properties):
    recs = recommend(
        db, Criteria(budget_max=50_000_000, location="Hinjewadi", property_type=PropertyType.VILLA)
    )
    assert [r.property.title for r in recs] == ["Riverstone Villa"]  # right type, other area
    assert recommend(db, Criteria(budget_max=50_000_000, location="Hinjewadi")) == []


def test_search_endpoint(client, properties, agent_h):
    response = client.get(
        "/api/v1/properties/search",
        params={"budget_max": 9_000_000, "location": "Baner"},
        headers=agent_h,
    )
    assert (
        response.status_code == 200
        and response.json()[0]["property"]["title"] == "Orchid Park 2 BHK"
    )
    assert (
        client.get(
            "/api/v1/properties/search", params={"budget_max": -5}, headers=agent_h
        ).status_code
        == 422
    )


def test_lead_recommendations_use_current_requirement(client, db, agent, agent_h, properties):
    from tests import factories

    lead = factories.make_lead(
        db,
        assigned_to=agent,
        requirement={"budget_max": 5_000_000, "property_type": PropertyType.PLOT},
    )
    recs = client.get(f"/api/v1/leads/{lead.id}/recommendations", headers=agent_h).json()
    assert [r["property"]["title"] for r in recs] == ["Green Plot"]


# ------------------------------------------------------------------------------ retrieval
def test_retrieval_finds_relevant_listing_by_free_text(db, properties):
    hits = property_index.search(db, "villa with private garden", k=3)
    assert hits and hits[0].property.title == "Riverstone Villa"
    assert property_index.search(db, "", k=3) == []
    assert property_index.search(db, "zzzz qqqq", k=3) == []


def test_retrieval_only_indexes_available_listings(db, properties):
    properties[2].status = PropertyStatus.SOLD
    db.commit()
    assert all(
        h.property.id != properties[2].id
        for h in property_index.search(db, "villa private garden", k=5)
    )


def test_index_refreshes_when_listings_change(db, properties):
    assert property_index.search(db, "lake view quiet society", k=3) == []
    property_service.create_property(db, PropertyCreate(**NEW_PROPERTY))
    hits = property_index.search(db, "lake view quiet society", k=3)
    assert hits and hits[0].property.title == "Maple Grove 2 BHK"


def test_free_text_can_only_raise_a_score(db, properties):
    criteria = {"location": "Baner", "bedrooms": 2}  # the 3 BHK is only a partial match
    plain = {r.property.title: r.match_score for r in recommend(db, Criteria(**criteria))}
    boosted = {
        r.property.title: r.match_score
        for r in recommend(db, Criteria(**criteria, free_text="swimming pool"))
    }
    assert boosted["Skyline 3 BHK"] > plain["Skyline 3 BHK"]  # its description mentions a pool
    assert (
        boosted["Orchid Park 2 BHK"] >= plain["Orchid Park 2 BHK"] == 1.0
    )  # a perfect match never drops
