"""Model-agnostic, per-prediction explanations.

For each group of related features we replace the lead's values with "typical" baseline
values (training medians / modes) and measure how much the predicted probability changes.
A positive impact means the lead's actual value *raises* the probability compared with a
typical lead. It works for any model with ``predict_proba`` and needs no extra dependency.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from ml.features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES, to_frame


def _fmt_inr(value: float) -> str:
    if math.isnan(value):
        return "not provided"
    if value >= 1e7:
        return f"₹{value / 1e7:.2f} Cr"
    return f"₹{value / 1e5:.1f} L"


def _fmt_days(value: float) -> str:
    return "not provided" if math.isnan(value) else f"{value:.0f} days"


# label -> (columns perturbed together, display formatter)
FACTOR_GROUPS: dict[str, tuple[list[str], Callable[[Mapping[str, Any]], str]]] = {
    "Budget fit": (
        ["budget_inr", "budget_to_market_ratio"],
        lambda r: (
            f"{_fmt_inr(r['budget_inr'])} "
            + (
                "(no market comparison)"
                if math.isnan(r["budget_to_market_ratio"])
                else f"({r['budget_to_market_ratio']:.2f}x market)"
            )
        ),
    ),
    "Purchase timeline": (
        ["purchase_timeline_days"],
        lambda r: _fmt_days(r["purchase_timeline_days"]),
    ),
    "Interaction frequency": (
        ["interaction_count"],
        lambda r: f"{r['interaction_count']:.0f} interactions",
    ),
    "Customer engagement": (
        ["inbound_ratio"],
        lambda r: f"{r['inbound_ratio'] * 100:.0f}% customer-initiated",
    ),
    "Site visits": (["site_visits"], lambda r: f"{r['site_visits']:.0f} visit(s)"),
    "Time since last contact": (
        ["days_since_last_contact"],
        lambda r: _fmt_days(r["days_since_last_contact"]),
    ),
    "Lead age": (["lead_age_days"], lambda r: _fmt_days(r["lead_age_days"])),
    "Loan pre-approval": (
        ["loan_preapproved"],
        lambda r: "yes" if r["loan_preapproved"] else "no / unknown",
    ),
    "Lead source": (["source"], lambda r: str(r["source"]).replace("_", " ")),
    "Preferred location": (["preferred_location"], lambda r: str(r["preferred_location"])),
    "Property type": (["property_type"], lambda r: str(r["property_type"])),
}


def compute_baseline(training_features: pd.DataFrame) -> dict[str, Any]:
    """Typical value per feature: median for numbers, mode for categories."""
    baseline: dict[str, Any] = {}
    for column in NUMERIC_FEATURES:
        baseline[column] = float(training_features[column].median())
    for column in CATEGORICAL_FEATURES:
        baseline[column] = str(training_features[column].mode().iloc[0])
    return baseline


def explain_prediction(
    model: Any,
    features: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    top_k: int = 6,
) -> tuple[float, list[dict[str, Any]]]:
    """Return ``(probability, factors)`` sorted by absolute impact (probability points)."""
    row = to_frame([features])
    variants = [row]
    for columns, _ in FACTOR_GROUPS.values():
        variant = row.copy()
        for column in columns:
            variant[column] = baseline[column]
        variants.append(variant)

    probabilities = model.predict_proba(pd.concat(variants, ignore_index=True)[FEATURE_COLUMNS])[
        :, 1
    ]
    probability = float(probabilities[0])

    record = row.iloc[0].to_dict()
    factors = []
    for (label, (_, formatter)), perturbed in zip(
        FACTOR_GROUPS.items(), probabilities[1:], strict=True
    ):
        impact = probability - float(perturbed)
        factors.append(
            {
                "factor": label,
                "value": formatter(record),
                "impact": round(impact, 4),
                "direction": "increases" if impact >= 0 else "decreases",
            }
        )
    factors.sort(key=lambda f: abs(f["impact"]), reverse=True)
    return probability, factors[:top_k]
