from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ScoreBand
from app.schemas.common import ORMModel


class Factor(BaseModel):
    factor: str
    value: str
    impact: float  # change in conversion probability vs. a typical lead (-1..1)
    direction: str  # "increases" | "decreases"


class PredictionOut(ORMModel):
    id: int
    lead_id: int
    probability: float
    band: ScoreBand
    model_version: str
    factors: list[Factor]
    created_at: datetime


class ThresholdMetrics(BaseModel):
    threshold: float
    precision: float
    recall: float
    f1: float
    confusion_matrix: dict[str, int]


class ModelInfo(BaseModel):
    available: bool
    version: str | None = None
    algorithm: str | None = None
    trained_at: str | None = None
    data_source: str | None = None
    roc_auc: float | None = None
    pr_auc: float | None = None
    brier_score: float | None = None
    thresholds: list[ThresholdMetrics] = []
    feature_importance: list[dict[str, Any]] = []
    cv_roc_auc: dict[str, float] = {}
    hot_threshold: float
    warm_threshold: float
    disclaimer: str | None = None
