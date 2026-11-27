# Sample dataset

`synthetic_leads.csv` — 1,000 **synthetic** leads (seed 42, ~26% converted) with the model's feature
columns plus the `converted` label and an `is_synthetic` flag that is always `True`.

Regenerate: `cd backend && python -m scripts.generate_data --rows 1000 --seed 42`

| Column | Meaning |
|---|---|
| source | website, facebook_ads, newspaper, direct |
| preferred_location, property_type | requirement; `unknown` when not stated |
| budget_inr, purchase_timeline_days | blank when not stated |
| interaction_count, inbound_ratio | engagement volume, and share of interactions started by the customer |
| site_visits, days_since_last_contact, lead_age_days | funnel progress and recency |
| loan_preapproved | 1 / 0, blank if unknown |
| converted | target: 1 if the lead bought |

No real person, phone number or email appears anywhere in this repository; demo contacts use
`example.com` addresses and `+910000…` numbers. See `docs/eda_report.md` for an analysis.
