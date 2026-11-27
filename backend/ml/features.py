"""Feature engineering shared by training and online inference.

Using one implementation for both paths prevents train/serve skew. Every feature
here is something the sales team knows *before* the outcome of the lead is known.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from ml.reference import UNKNOWN, market_price

TARGET = "converted"

NUMERIC_FEATURES: list[str] = [
    "budget_inr",
    "budget_to_market_ratio",
    "purchase_timeline_days",
    "interaction_count",
    "inbound_ratio",
    "site_visits",
    "days_since_last_contact",
    "lead_age_days",
    "loan_preapproved",
]
CATEGORICAL_FEATURES: list[str] = ["source", "preferred_location", "property_type"]
FEATURE_COLUMNS: list[str] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Raw columns produced by the synthetic generator (everything except engineered ones).
RAW_COLUMNS: list[str] = [c for c in FEATURE_COLUMNS if c != "budget_to_market_ratio"]


def budget_to_market_ratio(
    budget: float | None, location: str | None, property_type: str | None
) -> float:
    """How realistic is the budget compared with the market price? NaN if no budget."""
    if budget is None or (isinstance(budget, float) and math.isnan(budget)) or budget <= 0:
        return float("nan")
    return float(budget) / market_price(location, property_type)


def build_features(
    *,
    source: str,
    budget: float | None,
    location: str | None,
    property_type: str | None,
    timeline_days: float | None,
    interaction_count: int,
    inbound_count: int,
    outbound_count: int,
    site_visits: int,
    days_since_last_contact: float | None,
    lead_age_days: float,
    loan_preapproved: bool | None,
) -> dict[str, Any]:
    """Build the model input for a single lead from raw CRM facts."""
    location = location or UNKNOWN
    property_type = property_type or UNKNOWN
    engaged = inbound_count + outbound_count
    return {
        "source": source,
        "preferred_location": location,
        "property_type": property_type,
        "budget_inr": float(budget) if budget else float("nan"),
        "budget_to_market_ratio": budget_to_market_ratio(budget, location, property_type),
        "purchase_timeline_days": (
            float(timeline_days) if timeline_days is not None else float("nan")
        ),
        "interaction_count": int(interaction_count),
        "inbound_ratio": (inbound_count / engaged) if engaged else 0.0,
        "site_visits": int(site_visits),
        # A lead that was never contacted has been "waiting" since it was created.
        "days_since_last_contact": float(
            days_since_last_contact if days_since_last_contact is not None else lead_age_days
        ),
        "lead_age_days": float(lead_age_days),
        "loan_preapproved": 1.0 if loan_preapproved else 0.0,
    }


def to_frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Convert feature dicts to a correctly typed DataFrame (NaN for missing numbers)."""
    frame = pd.DataFrame(list(rows), columns=FEATURE_COLUMNS)
    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].fillna(UNKNOWN).astype(str)
    return frame


def prepare_training_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Add engineered columns to a raw lead table (e.g. the synthetic dataset)."""
    frame = raw.copy()
    frame["budget_to_market_ratio"] = [
        budget_to_market_ratio(
            None if pd.isna(b) else b,
            loc,
            ptype,
        )
        for b, loc, ptype in zip(
            frame["budget_inr"], frame["preferred_location"], frame["property_type"], strict=True
        )
    ]
    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].fillna(UNKNOWN).astype(str)
    return frame


def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))
