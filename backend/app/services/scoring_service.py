"""Lead scoring: load the trained model, build features from CRM data, predict, explain, persist.

Technique: traditional machine learning (calibrated Random Forest / XGBoost trained in
``ml/train.py``). No LLM is involved in scoring.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ModelNotAvailableError
from app.core.time import ensure_utc, utcnow
from app.models import Lead, LeadInteraction, Prediction
from app.models.enums import InteractionDirection, InteractionType, ScoreBand
from app.schemas.prediction import ModelInfo
from app.services import lead_service
from ml.explain import explain_prediction
from ml.features import FEATURE_COLUMNS, build_features

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    model: Any
    baseline: dict[str, Any]
    metadata: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.metadata["version"])


class ModelStore:
    """Loads the artifact lazily and reloads it if the file changes on disk.

    SECURITY: joblib files are pickles. Only ever load artifacts produced by your own training
    pipeline, never files from untrusted sources.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._loaded: LoadedModel | None = None
        self._mtime: float | None = None
        self._lock = threading.Lock()

    def get(self) -> LoadedModel:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError as exc:
            raise ModelNotAvailableError() from exc
        with self._lock:
            if self._loaded is None or mtime != self._mtime:
                try:
                    artifact = joblib.load(self.path)
                    if list(artifact["feature_columns"]) != FEATURE_COLUMNS:
                        raise ValueError("model was trained with a different feature set")
                    self._loaded = LoadedModel(
                        artifact["model"], artifact["baseline"], artifact["metadata"]
                    )
                except Exception as exc:
                    logger.exception("Could not load model artifact at %s", self.path)
                    raise ModelNotAvailableError("The model artifact could not be loaded") from exc
                self._mtime = mtime
                logger.info("Loaded lead-scoring model %s", self._loaded.version)
            return self._loaded


_store: ModelStore | None = None


def get_model_store() -> ModelStore:
    global _store
    path = get_settings().model_path
    if _store is None or _store.path != path:
        _store = ModelStore(path)
    return _store


def band_for(probability: float) -> ScoreBand:
    settings = get_settings()
    if probability >= settings.hot_threshold:
        return ScoreBand.HOT
    if probability >= settings.warm_threshold:
        return ScoreBand.WARM
    return ScoreBand.COLD


def model_info() -> ModelInfo:
    settings = get_settings()
    base = {"hot_threshold": settings.hot_threshold, "warm_threshold": settings.warm_threshold}
    try:
        loaded = get_model_store().get()
    except ModelNotAvailableError:
        return ModelInfo(available=False, **base)
    meta, metrics = loaded.metadata, loaded.metadata["metrics"]
    return ModelInfo(
        available=True,
        version=meta["version"],
        algorithm=meta["algorithm"],
        trained_at=meta["trained_at"],
        data_source=meta["data_source"],
        roc_auc=metrics["roc_auc"],
        pr_auc=metrics["pr_auc"],
        brier_score=metrics["brier_score"],
        thresholds=metrics["at_threshold"],
        feature_importance=metrics["permutation_importance"],
        cv_roc_auc=meta["cv_roc_auc"],
        disclaimer=meta.get("disclaimer"),
        **base,
    )


def _json_safe(features: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (None if isinstance(value, float) and math.isnan(value) else value)
        for key, value in features.items()
    }


def features_for_lead(db: Session, lead: Lead) -> dict[str, Any]:
    """Aggregate a lead's CRM records into model features (as of *now*)."""
    now = utcnow()
    requirement = lead_service.current_requirement(db, lead.id)
    interactions: list[LeadInteraction] = list(lead.interactions)
    contact_events = [i for i in interactions if i.direction != InteractionDirection.INTERNAL]
    inbound = sum(1 for i in contact_events if i.direction == InteractionDirection.INBOUND)
    outbound = len(contact_events) - inbound
    last_contact = max((ensure_utc(i.occurred_at) for i in contact_events), default=None)

    return build_features(
        source=lead.source.value,
        budget=requirement.budget_value if requirement else None,
        location=requirement.preferred_location if requirement else None,
        property_type=requirement.property_type.value
        if requirement and requirement.property_type
        else None,
        timeline_days=requirement.purchase_timeline_days if requirement else None,
        interaction_count=len(contact_events),
        inbound_count=inbound,
        outbound_count=outbound,
        site_visits=sum(1 for i in interactions if i.type == InteractionType.SITE_VISIT),
        days_since_last_contact=(now - last_contact).days if last_contact else None,
        lead_age_days=max((now - ensure_utc(lead.created_at)).days, 0),
        loan_preapproved=requirement.loan_preapproved if requirement else None,
    )


def score_lead(db: Session, lead: Lead) -> Prediction:
    """Score one lead, store the prediction and refresh the lead's cached score."""
    loaded = get_model_store().get()
    features = features_for_lead(db, lead)
    probability, factors = explain_prediction(loaded.model, features, loaded.baseline)
    probability = min(max(probability, 0.0), 1.0)

    prediction = Prediction(
        lead_id=lead.id,
        probability=round(probability, 4),
        band=band_for(probability),
        model_version=loaded.version,
        features=_json_safe(features),
        factors=factors,
    )
    db.add(prediction)
    lead.latest_probability = prediction.probability
    lead.latest_band = prediction.band
    lead.scored_at = utcnow()
    db.commit()
    db.refresh(prediction)
    return prediction


def latest_prediction(db: Session, lead_id: int) -> Prediction | None:
    return db.scalars(
        select(Prediction)
        .where(Prediction.lead_id == lead_id)
        .order_by(Prediction.id.desc())
        .limit(1)
    ).first()
