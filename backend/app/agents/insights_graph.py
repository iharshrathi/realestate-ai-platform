"""Sales Intelligence Agent: analyse overall performance and produce business insights.

    START -> analyse (SQL aggregates + forecast) -> insights (rules, optional LLM summary) -> END

Read-only: it never writes to business tables (only the audit log).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.runtime import AgentContext
from app.schemas.analytics import Forecast, InsightsResponse
from app.services import analytics_service


class InsightsState(TypedDict, total=False):
    overview: dict[str, Any]
    forecast: dict[str, Any]
    channels: list[dict[str, Any]]
    insights: dict[str, Any]
    errors: Annotated[list[str], operator.add]


def run_sales_intelligence(ctx: AgentContext) -> tuple[InsightsResponse, Forecast | None]:
    db, user = ctx.db, ctx.user
    forecast_holder: list[Forecast] = []

    def analyse(state: InsightsState) -> dict[str, Any]:
        forecast = analytics_service.forecast(db, user)
        forecast_holder.append(forecast)
        return {
            "overview": analytics_service.overview(db, user).model_dump(),
            "channels": [c.model_dump() for c in analytics_service.channels(db, user)],
            "forecast": forecast.model_dump(),
        }

    def insights(state: InsightsState) -> dict[str, Any]:
        response = analytics_service.insights_with_narrative(db, user)
        return {"insights": response.model_dump(mode="json")}

    graph = StateGraph(InsightsState)
    graph.add_node("analyse", ctx.node("sales_intelligence_agent", "analyse_performance", analyse))
    graph.add_node("insights", ctx.node("sales_intelligence_agent", "generate_insights", insights))
    graph.add_edge(START, "analyse")
    graph.add_edge("analyse", "insights")
    graph.add_edge("insights", END)

    final = graph.compile().invoke({"errors": []})
    response = (
        InsightsResponse.model_validate(final["insights"])
        if final.get("insights")
        else InsightsResponse(insights=[])
    )
    return response, (forecast_holder[0] if forecast_holder else None)
