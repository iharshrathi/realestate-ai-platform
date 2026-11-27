"""Synthetic real-estate lead generator.

IMPORTANT: this data is generated from hand-written rules, not from real customers.
Any model trained on it only learns those rules. Metrics computed on it say nothing
about real-world sales performance. Replace it with real, properly time-split CRM
data before drawing business conclusions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features import RAW_COLUMNS, TARGET, sigmoid
from ml.reference import (
    LOCATION_PRICE_INDEX,
    PROPERTY_TYPES,
    SOURCES,
    UNKNOWN,
    market_price,
)

TIMELINE_CHOICES = np.array([14, 30, 60, 90, 180, 365])
TIMELINE_PROBS = np.array([0.08, 0.17, 0.20, 0.20, 0.20, 0.15])
SOURCE_PROBS = [0.35, 0.30, 0.15, 0.20]
SOURCE_EFFECT = {"direct": 0.6, "website": 0.2, "newspaper": -0.2, "facebook_ads": -0.5}


def generate_leads(n: int, seed: int = 42) -> pd.DataFrame:
    """Generate ``n`` synthetic leads with a ``converted`` label.

    The label is drawn from a logistic model over lead-quality signals plus noise, so
    the problem is learnable but not trivial. Features describe the lead at scoring time
    (before the outcome is known); no feature is derived from the label.
    """
    rng = np.random.default_rng(seed)

    source = rng.choice(SOURCES, size=n, p=SOURCE_PROBS)
    location = rng.choice(list(LOCATION_PRICE_INDEX), size=n)
    property_type = rng.choice(PROPERTY_TYPES, size=n, p=[0.55, 0.15, 0.20, 0.10])

    market = np.array(
        [market_price(loc, pt) for loc, pt in zip(location, property_type, strict=True)]
    )
    budget_ratio = rng.lognormal(mean=0.0, sigma=0.35, size=n)
    budget = np.round(market * budget_ratio, -5)

    timeline = rng.choice(TIMELINE_CHOICES, size=n, p=TIMELINE_PROBS).astype(float)

    # A hidden "engagement" trait drives the behavioural signals, so they are correlated.
    engagement = rng.beta(2.0, 3.5, size=n)
    interaction_count = np.clip(rng.poisson(2 + 10 * engagement), 0, 25)
    inbound_ratio = np.where(
        interaction_count > 0, np.clip(engagement + rng.normal(0, 0.12, n), 0, 1), 0.0
    )
    site_visits = rng.binomial(np.minimum(interaction_count, 4), 0.15 + 0.5 * engagement)
    lead_age_days = rng.integers(3, 200, size=n)
    days_since_last = np.minimum(
        lead_age_days, np.round(rng.exponential(12, n) * (1.3 - engagement))
    ).astype(int)
    loan_preapproved = (rng.random(n) < 0.15 + 0.35 * engagement).astype(float)

    logit = (
        -4.0
        + 1.3 * (timeline <= 30)
        + 0.7 * ((timeline > 30) & (timeline <= 90))
        - 0.5 * (timeline >= 365)
        + 0.9 * np.minimum(site_visits, 3)
        + 2.0 * inbound_ratio
        + 0.10 * np.minimum(interaction_count, 15)
        - 0.04 * np.minimum(days_since_last, 60)
        - 1.6 * np.abs(np.log(budget_ratio))  # budgets far from market rarely close
        + 0.7 * loan_preapproved
        + np.array([SOURCE_EFFECT[s] for s in source])
        + rng.normal(0, 0.7, n)  # unobserved factors
    )
    converted = (rng.random(n) < sigmoid(logit)).astype(int)

    frame = pd.DataFrame(
        {
            "source": source,
            "preferred_location": location,
            "property_type": property_type,
            "budget_inr": budget,
            "purchase_timeline_days": timeline,
            "interaction_count": interaction_count,
            "inbound_ratio": np.round(inbound_ratio, 3),
            "site_visits": site_visits,
            "days_since_last_contact": days_since_last,
            "lead_age_days": lead_age_days,
            "loan_preapproved": loan_preapproved,
            TARGET: converted,
        }
    )

    # Real CRM data is incomplete: blank out some fields.
    frame.loc[rng.random(n) < 0.08, "budget_inr"] = np.nan
    frame.loc[rng.random(n) < 0.20, "purchase_timeline_days"] = np.nan
    frame.loc[rng.random(n) < 0.07, "preferred_location"] = UNKNOWN
    frame.loc[rng.random(n) < 0.05, "property_type"] = UNKNOWN

    frame.insert(0, "is_synthetic", True)
    return frame[["is_synthetic", *RAW_COLUMNS, TARGET]]
