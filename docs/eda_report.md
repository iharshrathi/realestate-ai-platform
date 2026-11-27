# Exploratory data analysis (synthetic data)

> **All figures below describe generated data, not real customers.** The patterns exist because the generator in `backend/ml/synthetic_data.py` was written to produce them.

Rows: **6,000** · overall conversion rate: **24.4%**

## Missing values
| column | missing |
| --- | --- |
| budget_inr | 490 |
| purchase_timeline_days | 1242 |

## Conversion by source
| source | leads | conversion_rate |
| --- | --- | --- |
| direct | 1173 | 30.8% |
| facebook_ads | 1771 | 18.6% |
| newspaper | 885 | 22.0% |
| website | 2171 | 26.8% |

## Conversion by property type
| property_type | leads | conversion_rate |
| --- | --- | --- |
| apartment | 3112 | 24.6% |
| commercial | 552 | 23.9% |
| plot | 1162 | 25.6% |
| unknown | 298 | 23.2% |
| villa | 876 | 23.1% |

## Conversion by number of site visits
| site_visits | leads | conversion_rate |
| --- | --- | --- |
| 0 | 1695 | 6.7% |
| 1 | 2132 | 18.5% |
| 2 | 1475 | 35.7% |
| 3 | 698 | 61.9% |

## Conversion by loan pre-approval
| loan_preapproved | leads | conversion_rate |
| --- | --- | --- |
| 0.0 | 4358 | 20.6% |
| 1.0 | 1642 | 34.7% |

## Conversion by purchase timeline
| timeline | leads | conversion_rate |
| --- | --- | --- |
| 31-90d | 1911 | 26.1% |
| 91-180d | 1006 | 18.1% |
| >180d | 660 | 14.2% |
| not stated | 1242 | 24.2% |
| ≤30d | 1181 | 33.2% |

## Numeric summary
| feature | mean | std | min | 50% | max |
| --- | --- | --- | --- | --- | --- |
| budget_inr | 11574591.65 | 7659301.4 | 1800000.0 | 9250000.0 | 73500000.0 |
| purchase_timeline_days | 124.82 | 110.66 | 14.0 | 90.0 | 365.0 |
| interaction_count | 5.64 | 3.07 | 0.0 | 5.0 | 22.0 |
| inbound_ratio | 0.36 | 0.22 | 0.0 | 0.34 | 1.0 |
| site_visits | 1.21 | 1.02 | 0.0 | 1.0 | 4.0 |
| days_since_last_contact | 10.7 | 11.11 | 0.0 | 7.0 | 123.0 |
| lead_age_days | 100.35 | 56.69 | 3.0 | 99.0 | 199.0 |
| loan_preapproved | 0.27 | 0.45 | 0.0 | 0.0 | 1.0 |
| converted | 0.24 | 0.43 | 0.0 | 0.0 | 1.0 |

## Correlation with conversion
| feature | correlation |
| --- | --- |
| site_visits | 0.396 |
| inbound_ratio | 0.336 |
| interaction_count | 0.294 |
| days_since_last_contact | -0.147 |
| loan_preapproved | 0.146 |
| purchase_timeline_days | -0.141 |
| budget_inr | -0.031 |
| lead_age_days | -0.023 |

## Caveats
- Correlation is not causation, and here the "causes" were put in by hand.
- Real CRM data will have different distributions, label noise and leakage risks; re-run this analysis and re-validate the model before trusting any score.
