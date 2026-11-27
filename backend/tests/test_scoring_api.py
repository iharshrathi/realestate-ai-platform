from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import Prediction
from app.models.enums import ScoreBand
from app.services import scoring_service
from tests import factories


def _engaged_lead(db, agent):
    return factories.make_lead(
        db,
        assigned_to=agent,
        created_at=utcnow() - timedelta(days=15),
        requirement={"budget_max": 8_000_000, "preferred_location": "Baner", "purchase_timeline_days": 30, "loan_preapproved": True},
        interactions=6,
    )  # fmt: skip


def test_scoring_stores_prediction_and_refreshes_lead(client, db, agent, agent_h, trained_model):
    lead = _engaged_lead(db, agent)
    response = client.post(f"/api/v1/leads/{lead.id}/score", headers=agent_h)
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["probability"] <= 1
    assert body["band"] in {"hot", "warm", "cold"}
    assert len(body["factors"]) >= 3
    assert {"factor", "value", "impact", "direction"} <= set(body["factors"][0])

    db.expire_all()
    stored = db.scalars(select(Prediction).where(Prediction.lead_id == lead.id)).all()
    assert len(stored) == 1 and stored[0].features["preferred_location"] == "Baner"
    detail = client.get(f"/api/v1/leads/{lead.id}", headers=agent_h).json()
    assert detail["latest_probability"] == body["probability"]
    assert detail["latest_prediction"]["model_version"] == body["model_version"]

    client.post(f"/api/v1/leads/{lead.id}/score", headers=agent_h)
    history = client.get(f"/api/v1/leads/{lead.id}/predictions", headers=agent_h).json()
    assert len(history) == 2 and history[0]["id"] > history[1]["id"]  # append-only history


def test_band_thresholds_follow_settings():
    settings = get_settings()
    assert scoring_service.band_for(settings.hot_threshold) == ScoreBand.HOT
    assert scoring_service.band_for(settings.warm_threshold) == ScoreBand.WARM
    assert scoring_service.band_for(settings.warm_threshold - 0.01) == ScoreBand.COLD


def test_engaged_lead_scores_higher_than_unengaged(client, db, agent, agent_h, trained_model):
    strong = _engaged_lead(db, agent)
    weak = factories.make_lead(
        db, assigned_to=agent, created_at=utcnow() - timedelta(days=150), source="facebook_ads"
    )
    p_strong = client.post(f"/api/v1/leads/{strong.id}/score", headers=agent_h).json()[
        "probability"
    ]
    p_weak = client.post(f"/api/v1/leads/{weak.id}/score", headers=agent_h).json()["probability"]
    assert p_strong > p_weak


def test_missing_model_returns_503_not_500(client, lead, agent_h, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "model_path", tmp_path / "missing.joblib")
    response = client.post(f"/api/v1/leads/{lead.id}/score", headers=agent_h)
    assert response.status_code == 503
    assert "train" in response.json()["detail"].lower()
    info = client.get("/api/v1/model", headers=agent_h).json()
    assert info["available"] is False


def test_corrupt_model_file_returns_503(client, lead, agent_h, monkeypatch, tmp_path):
    broken = tmp_path / "broken.joblib"
    broken.write_bytes(b"not a model")
    monkeypatch.setattr(get_settings(), "model_path", broken)
    assert client.post(f"/api/v1/leads/{lead.id}/score", headers=agent_h).status_code == 503


def test_model_info_exposes_metrics_and_disclaimer(client, agent_h, trained_model):
    info = client.get("/api/v1/model", headers=agent_h).json()
    assert info["available"] is True
    assert 0.5 < info["roc_auc"] <= 1 and info["pr_auc"] > 0
    assert info["data_source"] == "synthetic" and "SYNTHETIC" in info["disclaimer"]
    assert len(info["thresholds"]) == 2 and info["feature_importance"]
    assert client.get("/api/v1/model").status_code == 401
