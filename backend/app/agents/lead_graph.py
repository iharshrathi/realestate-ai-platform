"""LangGraph workflow that processes one lead end to end.

    START -> qualification -> scoring -+-> recommendation -> follow_up -> END     (hot / warm)
                                       +-----------------> follow_up -> END       (cold / unscored)

Agents and what they may write
------------------------------
* Lead Qualification Agent  : NLP extraction -> appends a ``customer_requirements`` row.
* Lead Scoring Agent        : ML model       -> appends a ``predictions`` row, refreshes the lead's
                              cached score.
* Property Recommendation   : read-only matching against verified listings.
* Follow-Up Agent           : creates/refreshes a DRAFT follow-up. It cannot approve or send it.

Agents never change a lead's status, assignment or contact details, and never send messages.
All of that stays with humans (see ``tests/test_agents.py``). Orchestration is deterministic:
the graph, not an LLM, decides which agent runs next. LLMs are used only inside narrow, validated
steps (requirement gap-filling, message personalisation).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.runtime import AgentContext
from app.models import CustomerRequirement, Lead, Property
from app.models.enums import InteractionDirection, RequirementSource, ScoreBand
from app.schemas.agent import LeadAgentResult
from app.schemas.follow_up import FollowUpOut
from app.schemas.nlp import ExtractedRequirements
from app.schemas.prediction import PredictionOut
from app.schemas.property import Recommendation
from app.schemas.requirement import RequirementIn
from app.services import followup_service, lead_service, nlp_service, scoring_service
from app.services.recommendation_service import criteria_from_requirement, recommend


class LeadState(TypedDict, total=False):
    lead_id: int
    message: str | None
    requirement: dict[str, Any] | None
    prediction: dict[str, Any] | None
    band: str | None
    recommendations: list[dict[str, Any]]
    follow_up_id: int | None
    errors: Annotated[list[str], operator.add]


_CARRY_OVER_FIELDS = (
    "preferred_location",
    "property_type",
    "bedrooms",
    "purchase_timeline_days",
    "urgency",
    "loan_preapproved",
)


def _merge(extracted: ExtractedRequirements, existing: CustomerRequirement | None) -> RequirementIn:
    """New requirement row = freshly extracted values, falling back to the previous profile.

    A newly stated budget replaces the old budget range as a pair, so min <= max always holds.
    """
    data: dict[str, Any] = {"intent": extracted.intent}
    if extracted.budget_min is not None or extracted.budget_max is not None:
        data["budget_min"], data["budget_max"] = extracted.budget_min, extracted.budget_max
    elif existing is not None:
        data["budget_min"], data["budget_max"] = existing.budget_min, existing.budget_max
    for name in _CARRY_OVER_FIELDS:
        fresh = getattr(extracted, name)
        data[name] = fresh if fresh is not None else (getattr(existing, name) if existing else None)
    return RequirementIn(**data)


def build_lead_graph(ctx: AgentContext, lead: Lead):
    """Compile the workflow for one lead. Nodes close over ``ctx`` (DB session + acting user)."""
    db = ctx.db

    # ---- Agent 1: Lead Qualification -------------------------------------------------
    def qualification(state: LeadState) -> dict[str, Any]:
        text = state.get("message")
        if not text:
            inbound = [
                i.content
                for i in lead.interactions
                if i.direction == InteractionDirection.INBOUND and i.content
            ]
            text = "\n".join(inbound[-3:])
        existing = lead_service.current_requirement(db, lead.id)
        if not text:
            return {"requirement": None}

        locations = list(db.scalars(select(Property.location).distinct()))
        extracted = nlp_service.extract_requirements(text, locations)
        if extracted.has_requirement_data():
            lead_service.add_requirement(
                db, lead, _merge(extracted, existing), RequirementSource.NLP, raw_text=text[:5000]
            )
        return {"requirement": extracted.model_dump(mode="json")}

    # ---- Agent 2: Lead Scoring -------------------------------------------------------
    def scoring(state: LeadState) -> dict[str, Any]:
        prediction = scoring_service.score_lead(db, lead)  # raises if no model: logged as FAILED
        return {
            "prediction": PredictionOut.model_validate(prediction).model_dump(mode="json"),
            "band": prediction.band.value,
        }

    def route_after_scoring(state: LeadState) -> str:
        # Cold or unscored leads get a nurture follow-up without spending effort on matching.
        return (
            "follow_up" if state.get("band") in (None, ScoreBand.COLD.value) else "recommendation"
        )

    # ---- Agent 4: Property Recommendation (read-only) ----------------------------------
    def recommendation(state: LeadState) -> dict[str, Any]:
        requirement = lead_service.current_requirement(db, lead.id)
        recs = recommend(db, criteria_from_requirement(requirement), limit=3)
        return {"recommendations": [r.model_dump(mode="json") for r in recs]}

    # ---- Agent 3: Follow-Up (creates a DRAFT only) -------------------------------------
    def follow_up(state: LeadState) -> dict[str, Any]:
        suggestion = followup_service.suggest_follow_up(db, lead, ctx.user)
        return {"follow_up_id": suggestion.follow_up.id}

    graph = StateGraph(LeadState)
    graph.add_node(
        "qualification", ctx.node("lead_qualification_agent", "extract_requirements", qualification)
    )
    graph.add_node("scoring", ctx.node("lead_scoring_agent", "score_lead", scoring))
    graph.add_node(
        "recommendation",
        ctx.node("property_recommendation_agent", "match_properties", recommendation),
    )
    graph.add_node("follow_up", ctx.node("follow_up_agent", "draft_follow_up", follow_up))
    graph.add_edge(START, "qualification")
    graph.add_edge("qualification", "scoring")
    graph.add_conditional_edges(
        "scoring",
        route_after_scoring,
        {"recommendation": "recommendation", "follow_up": "follow_up"},
    )
    graph.add_edge("recommendation", "follow_up")
    graph.add_edge("follow_up", END)
    return graph.compile()


def run_lead_pipeline(ctx: AgentContext, lead: Lead, message: str | None = None) -> LeadAgentResult:
    graph = build_lead_graph(ctx, lead)
    final: dict[str, Any] = graph.invoke({"lead_id": lead.id, "message": message, "errors": []})

    follow_up = None
    if final.get("follow_up_id"):
        follow_up_row = followup_service.get_follow_up_for_user(
            ctx.db, final["follow_up_id"], ctx.user
        )
        follow_up = FollowUpOut.model_validate(follow_up_row)
    return LeadAgentResult(
        run_id=ctx.run_id,
        lead_id=lead.id,
        requirement=ExtractedRequirements.model_validate(final["requirement"])
        if final.get("requirement")
        else None,
        prediction=PredictionOut.model_validate(final["prediction"])
        if final.get("prediction")
        else None,
        recommendations=[
            Recommendation.model_validate(r) for r in final.get("recommendations", [])
        ],
        follow_up=follow_up,
        steps=ctx.steps,
        errors=final.get("errors", []),
    )
