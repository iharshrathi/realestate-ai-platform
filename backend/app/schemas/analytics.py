from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Overview(BaseModel):
    total_leads: int
    new_leads: int
    qualified_leads: int
    converted_customers: int
    lost_leads: int
    pending_follow_ups: int
    overdue_follow_ups: int
    hot_leads: int
    conversion_rate: float  # converted / total
    synthetic_leads: int


class MonthlyPoint(BaseModel):
    month: str  # YYYY-MM
    leads: int
    converted: int
    by_source: dict[str, int]


class ChannelStats(BaseModel):
    source: str
    leads: int
    converted: int
    conversion_rate: float
    avg_score: float | None
    hot_share: float | None
    spend_inr: int
    cost_per_lead: float | None
    cost_per_conversion: float | None


class Forecast(BaseModel):
    open_leads: int
    scored_open_leads: int
    expected_conversions_open_leads: float
    expected_by_band: dict[str, float]
    next_month_leads: float | None
    next_month_conversions: float | None
    method: str
    caveat: str


class Insight(BaseModel):
    key: str
    title: str
    detail: str
    severity: Literal["info", "positive", "warning"]


class InsightsResponse(BaseModel):
    insights: list[Insight]
    narrative: str | None = None  # optional LLM summary of the insights above
    narrative_source: Literal["llm", "none"] = "none"
    data_is_synthetic: bool = False
