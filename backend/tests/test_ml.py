"""Tests for the ML pipeline: data generation, leakage guards, evaluation and explanations."""

import math

import joblib
import numpy as np
import pandas as pd

from ml.explain import FACTOR_GROUPS, explain_prediction
from ml.features import (
    FEATURE_COLUMNS,
    RAW_COLUMNS,
    TARGET,
    build_features,
    prepare_training_frame,
    to_frame,
)
from ml.synthetic_data import generate_leads


def test_synthetic_data_is_flagged_realistic_and_reproducible():
    frame = generate_leads(3000, seed=1)
    assert frame["is_synthetic"].all()
    assert list(frame.columns) == ["is_synthetic", *RAW_COLUMNS, TARGET]
    assert 0.15 < frame[TARGET].mean() < 0.35  # imbalanced, like real funnels
    assert frame["budget_inr"].isna().any()  # missing values are injected on purpose
    assert generate_leads(100, seed=5).equals(generate_leads(100, seed=5))
    assert not generate_leads(100, seed=5).equals(generate_leads(100, seed=6))


def test_no_feature_is_derived_from_the_label():
    """The target must not be (or leak through) any feature column."""
    assert TARGET not in FEATURE_COLUMNS
    frame = prepare_training_frame(generate_leads(4000, seed=2))
    correlations = frame[FEATURE_COLUMNS].select_dtypes("number").corrwith(frame[TARGET]).abs()
    assert correlations.max() < 0.6  # a leaked feature would correlate near 1


def test_online_and_training_features_are_identical():
    """Guards against train/serve skew: both paths must produce the same feature values."""
    raw = generate_leads(50, seed=9)
    train_frame = prepare_training_frame(raw)
    row = raw.iloc[0]
    online = build_features(
        source=row.source,
        budget=None if pd.isna(row.budget_inr) else row.budget_inr,
        location=row.preferred_location,
        property_type=row.property_type,
        timeline_days=None if pd.isna(row.purchase_timeline_days) else row.purchase_timeline_days,
        interaction_count=row.interaction_count,
        inbound_count=round(row.inbound_ratio * row.interaction_count),
        outbound_count=row.interaction_count - round(row.inbound_ratio * row.interaction_count),
        site_visits=row.site_visits,
        days_since_last_contact=row.days_since_last_contact,
        lead_age_days=row.lead_age_days,
        loan_preapproved=bool(row.loan_preapproved),
    )
    online_frame = to_frame([online])
    for column in (
        "budget_to_market_ratio",
        "purchase_timeline_days",
        "site_visits",
        "loan_preapproved",
    ):
        expected, actual = train_frame.iloc[0][column], online_frame.iloc[0][column]
        assert (math.isnan(expected) and math.isnan(actual)) or math.isclose(
            expected, actual, rel_tol=1e-9
        )


def test_missing_values_survive_feature_building():
    features = build_features(
        source="direct", budget=None, location=None, property_type=None, timeline_days=None,
        interaction_count=0, inbound_count=0, outbound_count=0, site_visits=0,
        days_since_last_contact=None, lead_age_days=12, loan_preapproved=None,
    )  # fmt: skip
    assert math.isnan(features["budget_inr"]) and math.isnan(features["budget_to_market_ratio"])
    assert features["preferred_location"] == "unknown"
    assert features["days_since_last_contact"] == 12  # never contacted => waiting since creation
    assert features["inbound_ratio"] == 0.0


def test_training_artifact_and_honest_evaluation(trained_model):
    artifact = joblib.load(trained_model)
    meta = artifact["metadata"]
    assert meta["data_source"] == "synthetic" and "SYNTHETIC" in meta["disclaimer"]
    assert meta["algorithm"] in {"random_forest", "xgboost"}
    assert set(meta["cv_roc_auc"]) == {"random_forest", "xgboost"}
    # 80/20 stratified split with the test set untouched during selection
    assert meta["n_test"] == round(0.2 * (meta["n_train"] + meta["n_test"]))
    assert abs(meta["positive_rate_train"] - meta["metrics"]["test_positive_rate"]) < 0.03

    metrics = meta["metrics"]
    assert 0.7 < metrics["roc_auc"] < 0.99  # learnable, but not suspiciously perfect
    assert {t["threshold"] for t in metrics["at_threshold"]} == {0.5, 0.25}
    for entry in metrics["at_threshold"]:
        assert {"precision", "recall", "f1", "confusion_matrix"} <= set(entry)
    assert len(metrics["permutation_importance"]) == len(FEATURE_COLUMNS)
    assert trained_model.with_suffix(".metrics.json").exists()


def test_probabilities_are_calibrated_enough(trained_model):
    artifact = joblib.load(trained_model)
    fresh = prepare_training_frame(generate_leads(3000, seed=99))
    proba = artifact["model"].predict_proba(fresh[FEATURE_COLUMNS])[:, 1]
    assert abs(proba.mean() - fresh[TARGET].mean()) < 0.05  # mean prediction ~ base rate


def test_predictions_respond_sensibly_to_lead_quality(trained_model):
    model = joblib.load(trained_model)["model"]

    def lead(**overrides):
        base = {
            "source": "direct", "budget": 8_000_000, "location": "Baner", "property_type": "apartment",
            "timeline_days": 30, "interaction_count": 8, "inbound_count": 6, "outbound_count": 2,
            "site_visits": 2, "days_since_last_contact": 2, "lead_age_days": 20, "loan_preapproved": True,
        }  # fmt: skip
        return build_features(**{**base, **overrides})

    strong = lead()
    weak = lead(source="facebook_ads", timeline_days=365, interaction_count=1, inbound_count=0,
                outbound_count=1, site_visits=0, days_since_last_contact=60, loan_preapproved=False)  # fmt: skip
    p_strong, p_weak = model.predict_proba(to_frame([strong, weak]))[:, 1]
    assert p_strong > p_weak + 0.25


def test_explanations_are_consistent(trained_model):
    artifact = joblib.load(trained_model)
    features = build_features(
        source="direct", budget=8_000_000, location="Baner", property_type="apartment", timeline_days=30,
        interaction_count=8, inbound_count=6, outbound_count=2, site_visits=3, days_since_last_contact=1,
        lead_age_days=20, loan_preapproved=True,
    )  # fmt: skip
    probability, factors = explain_prediction(
        artifact["model"], features, artifact["baseline"], top_k=20
    )
    assert 0 <= probability <= 1
    assert len(factors) == len(FACTOR_GROUPS)
    impacts = [abs(f["impact"]) for f in factors]
    assert impacts == sorted(impacts, reverse=True)
    top = factors[0]
    assert top["direction"] == ("increases" if top["impact"] >= 0 else "decreases")
    assert any(f["factor"] == "Site visits" and f["impact"] > 0 for f in factors)  # 3 visits help
    assert np.isfinite([f["impact"] for f in factors]).all()
