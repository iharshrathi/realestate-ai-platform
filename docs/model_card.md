# Model card — lead conversion scorer

> **Trained and evaluated on synthetic data.** The labels come from hand-written rules in
> `backend/ml/synthetic_data.py`, so these numbers show that the pipeline works, **not** how it would
> perform on real customers. Retrain on your own CRM history and re-validate before using any score.

| | |
|---|---|
| Task | Binary classification: will a lead convert? Output is a calibrated probability |
| Candidates | Random Forest, XGBoost (class-weighted) |
| Selection | Highest 5-fold CV ROC-AUC on the **training** split only (RF 0.820, XGBoost 0.824 → XGBoost) |
| Calibration | Isotonic regression (so 0.4 means roughly 40%) |
| Data | 6,000 synthetic leads, stratified 80/20 split (test set held out before any tuning); ~24% positives |
| Bands | **Hot** ≥ 0.50 · **Warm** ≥ 0.25 · **Cold** below (configurable: `HOT_THRESHOLD`, `WARM_THRESHOLD`) |

## Test-set results (1,200 held-out synthetic leads)

| Metric | Value |
|---|---|
| ROC-AUC | 0.810 |
| PR-AUC | 0.602 (baseline = positive rate 0.244) |
| Brier score | 0.138 |

| Threshold | Precision | Recall | F1 | TP / FP / FN / TN |
|---|---|---|---|---|
| 0.50 (Hot) | 0.67 | 0.39 | 0.49 | 114 / 56 / 179 / 851 |
| 0.25 (Warm+) | 0.50 | 0.74 | 0.59 | 216 / 219 / 77 / 688 |

Reading this: a Hot lead converts about two times in three, but Hot alone misses most buyers; including
Warm finds ~74% of them at the cost of more wasted effort. Choose the threshold from the cost of a
missed buyer versus a wasted follow-up, not from the F1 column.

## Features

Interaction count, inbound ratio, site visits, days since last contact, lead age, loan pre-approval,
purchase timeline, budget, budget relative to market price for the requested area/type, source,
location and property type. Feature code is shared between training and serving
(`backend/ml/features.py`) to avoid train/serve skew. Permutation importance on the test set is led by
`site_visits` (0.105), then `inbound_ratio` (0.036) and `purchase_timeline_days` (0.029) — which is what
the generator was told to do.

## Explanations

Per-lead "why this score" uses model-agnostic occlusion: each factor group (engagement, urgency,
budget fit, …) is replaced by a typical training value and the change in probability is reported. It
explains *this model's* behaviour, not causation.

## Limitations and responsible use

- Synthetic data → no real-world validity; distributions, noise and leakage in real CRM data will differ.
- Calibration and thresholds must be re-checked after retraining; monitor drift.
- Scores support prioritisation by a salesperson. They must not be used to deny service to anyone, and the
  features deliberately exclude personal attributes (name, gender, age, religion, etc.).
- The artifact is a joblib/pickle file: **only load files you trained yourself.**
