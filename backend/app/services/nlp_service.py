"""NLP: turn unstructured customer messages into a structured requirement profile.

Method: transparent rule-based extraction (regular expressions + keyword gazetteers). This is
classic NLP, not machine learning and not an LLM. If an LLM is configured, it is only asked to
fill fields the rules could not find, and its JSON is validated before use.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from app.models.enums import PropertyType
from app.schemas.nlp import ExtractedRequirements
from app.services import llm
from ml.reference import LOCATION_PRICE_INDEX

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- budget parsing
_UNIT_VALUES = {
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "l": 1e5,
    "million": 1e6,
    "mn": 1e6,
}

_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT = r"crores?|cr|lakhs?|lacs?|million|mn"
_RANGE_RE = re.compile(
    rf"(?:₹|rs\.?|inr)?\s*(?P<a>{_NUM})\s*(?:-|–|to|and)\s*(?:₹|rs\.?|inr)?\s*(?P<b>{_NUM})"
    rf"\s*(?:(?P<unit>{_UNIT})\b|(?P<lunit>[lL])\b)",
    re.I,
)
_MONEY_RE = re.compile(
    rf"(?P<cur>₹|rs\.?|inr)?\s*(?P<num>{_NUM})(?:\s*(?P<unit>{_UNIT})\b|(?P<lunit>[lL])\b)?",
    re.I,
)
_AREA_AFTER_RE = re.compile(
    r"\s*(sq|sft|square|ft|feet|meter|metre|sqm|bhk|bed|month|week|day|year|%)", re.I
)
_MAX_CUES = (
    "under",
    "below",
    "up to",
    "upto",
    "max",
    "maximum",
    "within",
    "less than",
    "at most",
    "not more than",
    "around",
    "about",
)
_MIN_CUES = ("above", "over", "at least", "minimum", "min", "more than", "starting")


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _unit_multiplier(unit: str | None, lunit: str | None) -> float | None:
    key = (unit or lunit or "").lower()
    return _UNIT_VALUES.get(key)


def parse_budget(text: str) -> tuple[int | None, int | None]:
    """Return ``(budget_min, budget_max)`` in INR. Understands lakh/crore, ranges and cues."""
    # 1) explicit ranges such as "50-70 lakh" or "between 1 and 1.5 cr"
    range_match = _RANGE_RE.search(text)
    if range_match:
        multiplier = _unit_multiplier(range_match["unit"], range_match["lunit"])
        if multiplier:
            low, high = sorted(
                (
                    _to_number(range_match["a"]) * multiplier,
                    _to_number(range_match["b"]) * multiplier,
                )
            )
            return int(low), int(high)

    # 2) single amounts
    lowered = text.lower()
    for match in _MONEY_RE.finditer(text):
        number = _to_number(match["num"])
        multiplier = _unit_multiplier(match["unit"], match["lunit"])
        tail = text[match.end() :]
        if multiplier is None:
            # A bare number only counts as money with a currency marker or a large value.
            is_big = number >= 100_000
            if not (match["cur"] or is_big) or _AREA_AFTER_RE.match(tail):
                continue
            multiplier = 1.0
        value = int(number * multiplier)
        before = lowered[max(0, match.start() - 25) : match.start()]
        if any(cue in before for cue in _MIN_CUES):
            return value, None
        return None, value  # "under X", "around X" and plain "X" are all treated as a ceiling
    return None, None


# ------------------------------------------------------------------- timeline and urgency
_WORD_NUMBERS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
_RELATIVE_RE = re.compile(
    r"\b(?:within|in|by|after|over the next|next)\s+(?P<n>\d+|a|an|one|two|three|four|five|six|"
    r"seven|eight|nine|ten|twelve)\s*(?P<unit>day|week|month|year)s?\b",
    re.I,
)
_URGENT_RE = re.compile(
    r"\b(immediately|asap|right away|urgent(?:ly)?|at once|as soon as possible|this week(?:end)?)\b",
    re.I,
)
_NEXT_PERIOD_RE = re.compile(r"\b(?:next|this)\s+(week|month|year)\b", re.I)
_RELAXED_RE = re.compile(
    r"\b(just exploring|just browsing|no rush|not in a hurry|someday|exploring options|in the future)\b",
    re.I,
)


def parse_timeline(text: str) -> tuple[int | None, str | None]:
    """Return ``(timeline_days, urgency)``; either may be ``None`` when not stated."""
    days: int | None = None
    if match := _RELATIVE_RE.search(text):
        raw = match["n"].lower()
        count = int(raw) if raw.isdigit() else _WORD_NUMBERS[raw]
        days = count * _UNIT_DAYS[match["unit"].lower()]
    elif match := _NEXT_PERIOD_RE.search(text):
        days = _UNIT_DAYS[match[1].lower()]
    elif _URGENT_RE.search(text):
        days = 7

    urgency: str | None = None
    if _URGENT_RE.search(text):
        urgency = "high"
    elif days is not None:
        urgency = "high" if days <= 30 else "medium" if days <= 90 else "low"
    elif _RELAXED_RE.search(text):
        urgency = "low"
    return days, urgency


# ------------------------------------------------------- property type, size, location, loans
_TYPE_KEYWORDS: dict[PropertyType, tuple[str, ...]] = {
    PropertyType.APARTMENT: ("apartment", "flat", "condo", "bhk"),
    PropertyType.VILLA: ("villa", "bungalow", "independent house", "row house"),
    PropertyType.PLOT: ("plot", "land"),
    PropertyType.COMMERCIAL: ("commercial", "shop", "office", "showroom", "warehouse"),
}
_BHK_RE = re.compile(r"\b(\d)\s*-?\s*(?:bhk|bed(?:room)?s?|br)\b", re.I)
_PREAPPROVED_RE = re.compile(
    r"\b(pre-?approved|loan (?:is )?(?:approved|sanctioned)|approved (?:home )?loan)\b", re.I
)


def parse_property_type(text: str) -> PropertyType | None:
    lowered = text.lower()
    best: tuple[int, PropertyType] | None = None
    for ptype, words in _TYPE_KEYWORDS.items():
        for word in words:
            position = re.search(rf"\b{re.escape(word)}s?\b", lowered)
            if position and (best is None or position.start() < best[0]):
                best = (position.start(), ptype)
    return best[1] if best else None


def parse_bedrooms(text: str) -> int | None:
    match = _BHK_RE.search(text)
    return int(match[1]) if match else None


def parse_location(text: str, known_locations: Iterable[str] = ()) -> str | None:
    """Find the first known location mentioned. Longer names are tried first ("Hinjewadi Phase 2")."""
    candidates = sorted({*LOCATION_PRICE_INDEX, *known_locations}, key=len, reverse=True)
    best: tuple[int, str] | None = None
    for name in candidates:
        found = re.search(rf"\b{re.escape(name)}\b", text, re.I)
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), name)
    return best[1] if best else None


# ----------------------------------------------------------------------------- intent
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "site_visit_request": (
        "site visit",
        "visit",
        "see the property",
        "schedule",
        "viewing",
        "tour",
        "come and see",
    ),
    "price_enquiry": ("price", "cost", "rate", "how much", "negotiat", "discount", "quote"),
    "financing_enquiry": ("loan", "emi", "finance", "mortgage", "bank", "down payment"),
    "brochure_request": (
        "brochure",
        "floor plan",
        "send details",
        "send me details",
        "more info",
        "photos",
    ),
    "rental_enquiry": ("rent", "lease", "tenant"),
    "not_interested": (
        "not interested",
        "stop messaging",
        "unsubscribe",
        "don't call",
        "do not call",
        "remove my number",
    ),
    "purchase_enquiry": (
        "buy",
        "purchase",
        "looking for",
        "interested in",
        "invest",
        "available",
        "need a",
        "want a",
    ),
}


def classify_intent(text: str) -> tuple[str, dict[str, int]]:
    """Return the primary intent and the keyword-hit count for every matched intent."""
    lowered = text.lower()
    hits = {
        intent: sum(1 for kw in words if re.search(rf"\b{re.escape(kw)}", lowered))
        for intent, words in _INTENT_KEYWORDS.items()
    }
    hits = {intent: count for intent, count in hits.items() if count}
    if "not_interested" in hits:
        return "not_interested", hits
    # "purchase_enquiry" is the baseline. A more specific request in the same message
    # (visit, price, loan, brochure) is what the sales team must act on, so it wins.
    specific = {intent: count for intent, count in hits.items() if intent != "purchase_enquiry"}
    if specific:
        return max(specific, key=lambda intent: specific[intent]), hits
    return ("purchase_enquiry" if hits else "general_enquiry"), hits


# --------------------------------------------------------------------------- orchestration
_CORE_FIELDS = (
    "budget",
    "preferred_location",
    "property_type",
    "bedrooms",
    "purchase_timeline_days",
)


def _format_inr(value: int) -> str:
    return f"₹{value / 1e7:.2f} Cr" if value >= 1e7 else f"₹{value / 1e5:.0f} L"


def build_summary(req: ExtractedRequirements) -> str:
    """One-line, human-readable requirement profile."""
    parts: list[str] = []
    what = " ".join(
        p
        for p in (
            f"{req.bedrooms} BHK" if req.bedrooms else None,
            req.property_type.value if req.property_type else None,
        )
        if p
    )
    parts.append(f"Looking for {'a ' + what if what else 'a property'}")
    if req.preferred_location:
        parts[-1] += f" in {req.preferred_location}"
    if req.budget_min and req.budget_max:
        parts.append(f"budget {_format_inr(req.budget_min)}–{_format_inr(req.budget_max)}")
    elif req.budget_max:
        parts.append(f"budget up to {_format_inr(req.budget_max)}")
    elif req.budget_min:
        parts.append(f"budget from {_format_inr(req.budget_min)}")
    if req.purchase_timeline_days is not None:
        parts.append(f"timeline ~{req.purchase_timeline_days} days")
    if req.urgency:
        parts.append(f"urgency {req.urgency}")
    if req.loan_preapproved:
        parts.append("loan pre-approved")
    parts.append(f"intent: {req.intent.replace('_', ' ')}")
    return ", ".join(parts) + "."


def extract_requirements(
    text: str, known_locations: Iterable[str] = (), *, use_llm: bool = True
) -> ExtractedRequirements:
    """Extract a structured requirement profile from free text."""
    budget_min, budget_max = parse_budget(text)
    timeline_days, urgency = parse_timeline(text)
    intent, intents = classify_intent(text)
    result = ExtractedRequirements(
        budget_min=budget_min,
        budget_max=budget_max,
        preferred_location=parse_location(text, known_locations),
        property_type=parse_property_type(text),
        bedrooms=parse_bedrooms(text),
        purchase_timeline_days=timeline_days,
        urgency=urgency,
        loan_preapproved=True if _PREAPPROVED_RE.search(text) else None,
        intent=intent,
        intents=intents,
    )
    if use_llm:
        result = _fill_gaps_with_llm(text, result)
    _finalise(result)
    return result


def _finalise(result: ExtractedRequirements) -> None:
    present = {
        "budget": result.budget_min is not None or result.budget_max is not None,
        "preferred_location": result.preferred_location is not None,
        "property_type": result.property_type is not None,
        "bedrooms": result.bedrooms is not None,
        "purchase_timeline_days": result.purchase_timeline_days is not None,
    }
    result.missing_fields = [name for name in _CORE_FIELDS if not present[name]]
    result.confidence = round(sum(present.values()) / len(_CORE_FIELDS), 2)
    result.summary = build_summary(result)


_LLM_SYSTEM = (
    "You extract real-estate requirements from a customer message. Reply with ONE JSON object "
    "and nothing else. Use null for anything not stated. Never guess."
)
_LLM_FIELDS = (
    "budget_min",
    "budget_max",
    "preferred_location",
    "property_type",
    "bedrooms",
    "purchase_timeline_days",
)


def _fill_gaps_with_llm(text: str, rules: ExtractedRequirements) -> ExtractedRequirements:
    """Ask the LLM for fields the rules missed. Validated; rule results always win."""
    missing = [f for f in _LLM_FIELDS if getattr(rules, f) is None]
    if not missing:
        return rules
    reply = llm.safe_complete(
        system=_LLM_SYSTEM,
        prompt=(
            f"Fields: {', '.join(missing)}. Budgets are integers in INR (1 lakh = 100000, "
            "1 crore = 10000000). property_type is one of apartment, villa, plot, commercial. "
            f"purchase_timeline_days is an integer.\n\nMessage:\n{text}"
        ),
        max_tokens=300,
    )
    data = llm.parse_json_object(reply) if reply else None
    if not data:
        return rules
    try:
        candidate = ExtractedRequirements.model_validate(
            {
                **rules.model_dump(),
                **{k: v for k, v in data.items() if k in missing and v is not None},
            }
        )
    except ValidationError:
        logger.warning("LLM extraction failed validation; ignoring it")
        return rules
    candidate.method = "rules+llm"
    return candidate


# ---------------------------------------------------------------------- contact details
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\d{5}[\s-]?\d{5}(?!\d)")
_NAME_RE = re.compile(
    r"\b(?:my name is|i am|i'm|this is|name:)\s+([A-Za-z][A-Za-z.' -]{1,60})", re.I
)
_NAME_STOP = {
    "looking",
    "interested",
    "and",
    "from",
    "here",
    "in",
    "to",
    "want",
    "need",
    "searching",
    "planning",
    "a",
    "an",
    "the",
    "my",
    "at",
    "for",
    "with",
    "calling",
    "email",
    "phone",
    "mobile",
    "number",
    "budget",
}


@dataclass
class ContactDetails:
    name: str | None = None
    email: str | None = None
    phone: str | None = None


def extract_contact_details(text: str) -> ContactDetails:
    """Pull a name / e-mail / phone out of a chat message (best effort)."""
    details = ContactDetails()
    if email := _EMAIL_RE.search(text):
        details.email = email.group(0).lower()
    if phone := _PHONE_RE.search(text):
        details.phone = re.sub(r"[\s-]", "", phone.group(0))
    if name := _NAME_RE.search(text):
        words: list[str] = []
        for word in name[1].replace(",", " ").split():
            if word.lower().strip(".") in _NAME_STOP or len(words) == 3:
                break
            words.append(word.strip(".").capitalize())
        details.name = " ".join(words) or None
    return details
