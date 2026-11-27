"""Train, evaluate and save the lead-conversion model.

Design choices (all aimed at avoiding leakage and over-optimistic metrics):

* The held-out test set is split off *first* (stratified) and used exactly once.
* Preprocessing (imputation, one-hot encoding) lives inside the sklearn ``Pipeline``,
  so it is fitted on training folds only.
* Model selection (Random Forest vs XGBoost) uses cross-validated ROC-AUC on the
  training split, never the test split.
* Class imbalance is handled with class weights, then probabilities are calibrated
  (isotonic) so that "0.62" can be read as roughly a 62% conversion chance.

Run: ``python -m scripts.train_model``
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

from ml.explain import compute_baseline
from ml.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    TARGET,
    prepare_training_frame,
)
from ml.synthetic_data import generate_leads

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT = Path(__file__).resolve().parent / "artifacts" / "lead_model.joblib"
EVALUATION_THRESHOLDS = (0.5, 0.25)  # = the Hot and Warm band cut-offs


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median", add_indicator=True), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )


def _candidates(y_train: pd.Series, seed: int, quick: bool) -> dict[str, Pipeline]:
    trees = 80 if quick else 300
    positive = max(int(y_train.sum()), 1)
    negative = max(int((1 - y_train).sum()), 1)
    return {
        "random_forest": Pipeline(
            [
                ("prep", _preprocessor()),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=trees,
                        min_samples_leaf=5,
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=seed,
                    ),
                ),
            ]
        ),
        "xgboost": Pipeline(
            [
                ("prep", _preprocessor()),
                (
                    "clf",
                    XGBClassifier(
                        n_estimators=trees,
                        max_depth=4,
                        learning_rate=0.05,
                        subsample=0.8,
                        colsample_bytree=0.8,
                        scale_pos_weight=negative / positive,
                        eval_metric="logloss",
                        n_jobs=2,
                        random_state=seed,
                    ),
                ),
            ]
        ),
    }


def _evaluate(model: Any, x_test: pd.DataFrame, y_test: pd.Series) -> dict[str, Any]:
    proba = model.predict_proba(x_test)[:, 1]
    report: dict[str, Any] = {
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
        "brier_score": round(float(brier_score_loss(y_test, proba)), 4),
        "test_positive_rate": round(float(y_test.mean()), 4),
        "at_threshold": [],
    }
    for threshold in EVALUATION_THRESHOLDS:
        predicted = (proba >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()
        report["at_threshold"].append(
            {
                "threshold": threshold,
                "precision": round(float(precision_score(y_test, predicted, zero_division=0)), 4),
                "recall": round(float(recall_score(y_test, predicted, zero_division=0)), 4),
                "f1": round(float(f1_score(y_test, predicted, zero_division=0)), 4),
                "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            }
        )
    return report


def train_and_save(
    raw: pd.DataFrame | None = None,
    *,
    output_path: Path = DEFAULT_ARTIFACT,
    n_samples: int = 6000,
    seed: int = 42,
    quick: bool = False,
) -> dict[str, Any]:
    """Train the model, write the artifact and a metrics JSON next to it, return metrics."""
    if raw is None:
        raw = generate_leads(n_samples, seed=seed)
    frame = prepare_training_frame(raw)
    features, target = frame[FEATURE_COLUMNS], frame[TARGET].astype(int)

    # 1) Hold out the test set before anything is fitted or selected.
    x_train, x_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, stratify=target, random_state=seed
    )

    # 2) Pick the algorithm using cross-validation on the training split only.
    cv = StratifiedKFold(n_splits=5 if not quick else 3, shuffle=True, random_state=seed)
    candidates = _candidates(y_train, seed, quick)
    cv_scores: dict[str, float] = {}
    for name, pipeline in candidates.items():
        scores = cross_val_score(pipeline, x_train, y_train, cv=cv, scoring="roc_auc")
        cv_scores[name] = round(float(scores.mean()), 4)
        logger.info("CV ROC-AUC %-14s %.4f (+/- %.4f)", name, scores.mean(), scores.std())
    best_name = max(cv_scores, key=cv_scores.get)

    # 3) Refit the winner with probability calibration (also internally cross-validated).
    calibrated = CalibratedClassifierCV(
        candidates[best_name], method="isotonic" if len(x_train) >= 1000 else "sigmoid", cv=3
    )
    calibrated.fit(x_train, y_train)

    # 4) Evaluate once on the untouched test set.
    metrics = _evaluate(calibrated, x_test, y_test)
    importance = permutation_importance(
        calibrated,
        x_test,
        y_test,
        scoring="roc_auc",
        n_repeats=3 if quick else 5,
        random_state=seed,
        n_jobs=1,
    )
    metrics["permutation_importance"] = sorted(
        (
            {"feature": col, "importance": round(float(val), 4)}
            for col, val in zip(FEATURE_COLUMNS, importance.importances_mean, strict=True)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )

    trained_at = datetime.now(UTC).isoformat(timespec="seconds")
    version = f"{best_name}-{hashlib.sha1(trained_at.encode()).hexdigest()[:8]}"
    metadata = {
        "version": version,
        "algorithm": best_name,
        "trained_at": trained_at,
        "data_source": "synthetic",
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "positive_rate_train": round(float(y_train.mean()), 4),
        "cv_roc_auc": cv_scores,
        "metrics": metrics,
        "disclaimer": (
            "Trained and evaluated on SYNTHETIC data generated from hand-written rules. "
            "These metrics do not describe real-world performance."
        ),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": calibrated,
            "feature_columns": FEATURE_COLUMNS,
            "baseline": compute_baseline(x_train),
            "metadata": metadata,
        },
        output_path,
    )
    output_path.with_suffix(".metrics.json").write_text(json.dumps(metadata, indent=2))
    logger.info(
        "Saved model %s to %s (test ROC-AUC %.4f)", version, output_path, metrics["roc_auc"]
    )
    return metadata
