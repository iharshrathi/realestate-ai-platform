import pytest

from app.models.enums import PropertyType
from app.services import nlp_service as nlp


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("My budget is 85 lakh", (None, 8_500_000)),
        ("budget 50-70 lakh", (5_000_000, 7_000_000)),
        ("between 1 and 1.5 cr", (10_000_000, 15_000_000)),
        ("under 1.2 cr", (None, 12_000_000)),
        ("looking above 1 crore", (10_000_000, None)),
        ("budget is ₹80,00,000", (None, 8_000_000)),
        ("around 90L", (None, 9_000_000)),
        ("budget 7500000", (None, 7_500_000)),
        ("2 BHK of 1200 sqft", (None, None)),  # sizes and BHK counts are not money
        ("I need it within 3 months", (None, None)),
        ("hello", (None, None)),
    ],
)
def test_budget_parsing(text, expected):
    assert nlp.parse_budget(text) == expected


@pytest.mark.parametrize(
    ("text", "days", "urgency"),
    [
        ("within 2 months", 60, "medium"),
        ("in three weeks", 21, "high"),
        ("I want to buy immediately", 7, "high"),
        ("next month", 30, "high"),
        ("within 1 year", 365, "low"),
        ("just exploring options", None, "low"),
        ("a nice 2 bhk", None, None),
    ],
)
def test_timeline_and_urgency(text, days, urgency):
    assert nlp.parse_timeline(text) == (days, urgency)


def test_location_matching_is_case_insensitive_and_canonical():
    assert nlp.parse_location("flat near BANER road") == "Baner"
    assert nlp.parse_location("somewhere in Atlantis") is None
    assert nlp.parse_location("anything in Magarpatta?", ["Magarpatta"]) == "Magarpatta"


def test_property_type_and_bedrooms():
    assert nlp.parse_property_type("need a flat") == PropertyType.APARTMENT
    assert nlp.parse_property_type("a villa or bungalow") == PropertyType.VILLA
    assert nlp.parse_property_type("buying land") == PropertyType.PLOT
    assert nlp.parse_property_type("open an office") == PropertyType.COMMERCIAL
    assert nlp.parse_property_type("hello") is None
    assert nlp.parse_bedrooms("looking for 3 BHK") == 3
    assert nlp.parse_bedrooms("2-bedroom place") == 2


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("I would like to schedule a site visit this weekend", "site_visit_request"),
        ("What is the price of the villa? any discount?", "price_enquiry"),
        ("Can I get a home loan, what's the EMI", "financing_enquiry"),
        ("Please send the brochure and floor plan", "brochure_request"),
        ("Looking to buy a flat", "purchase_enquiry"),
        (
            "I want to buy a 3 BHK flat, can we visit this weekend?",
            "site_visit_request",
        ),  # specific beats generic
        ("Looking to purchase a villa, what is the price?", "price_enquiry"),
        ("Not interested, please stop messaging me", "not_interested"),
        ("hello", "general_enquiry"),
    ],
)
def test_intent_classification(text, intent):
    assert nlp.classify_intent(text)[0] == intent


def test_full_extraction_builds_structured_profile():
    text = "Hi, I'm looking for a 3 BHK flat in Baner under 1.2 crore, planning to buy within 2 months. Loan is pre-approved."
    result = nlp.extract_requirements(text, use_llm=False)
    assert result.bedrooms == 3
    assert result.property_type == PropertyType.APARTMENT
    assert result.preferred_location == "Baner"
    assert result.budget_max == 12_000_000
    assert result.purchase_timeline_days == 60 and result.urgency == "medium"
    assert result.loan_preapproved is True
    assert result.confidence == 1.0 and result.missing_fields == []
    assert result.method == "rules"
    assert "3 BHK apartment in Baner" in result.summary and "₹1.20 Cr" in result.summary


def test_missing_fields_are_reported():
    result = nlp.extract_requirements("Looking for a villa", use_llm=False)
    assert set(result.missing_fields) == {
        "budget",
        "preferred_location",
        "bedrooms",
        "purchase_timeline_days",
    }
    assert result.confidence == 0.2


def test_contact_extraction():
    contact = nlp.extract_contact_details(
        "Hi, my name is Rohan Mehta and my number is 98765 43210, email Rohan@Example.com"
    )
    assert contact.name == "Rohan Mehta"
    assert contact.phone == "9876543210"
    assert contact.email == "rohan@example.com"
    assert nlp.extract_contact_details("I'm looking for a flat").name is None
    assert nlp.extract_contact_details("this is Priya, want a plot").name == "Priya"


def test_llm_only_fills_missing_fields_and_is_validated(monkeypatch):
    monkeypatch.setattr(
        nlp.llm,
        "safe_complete",
        lambda **_: '```json\n{"preferred_location": "Aundh", "budget_max": 1}\n```',
    )
    result = nlp.extract_requirements("a flat in Baner please", use_llm=True)
    assert result.preferred_location == "Baner"  # rules win over the LLM
    assert result.budget_max == 1 and result.method == "rules+llm"  # a missing field was filled


def test_garbage_llm_output_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(nlp.llm, "safe_complete", lambda **_: "sorry I cannot help")
    result = nlp.extract_requirements("a flat", use_llm=True)
    assert result.method == "rules"
    monkeypatch.setattr(nlp.llm, "safe_complete", lambda **_: '{"property_type": "castle"}')
    assert nlp.extract_requirements("hello", use_llm=True).method == "rules"
