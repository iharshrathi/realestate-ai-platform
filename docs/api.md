# API reference

Interactive docs: `/docs` (Swagger) and `/redoc` on the running API. Machine-readable spec: [`openapi.json`](openapi.json).
All endpoints are under `/api/v1`. Authenticate with `POST /auth/login` (form fields `username` = email, `password`) and send `Authorization: Bearer <token>`.

Roles: **agent** (own + unassigned leads), **manager** (everything, analytics, user list), **admin** (also creates users).

## auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/auth/me` | Me |

## users

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/users` | List Users |
| POST | `/api/v1/users` | Create User |
| PATCH | `/api/v1/users/{user_id}` | Update User |

## leads

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/leads` | List Leads |
| POST | `/api/v1/leads` | Create Lead |
| GET | `/api/v1/leads/{lead_id}` | Get Lead |
| PATCH | `/api/v1/leads/{lead_id}` | Update Lead |
| DELETE | `/api/v1/leads/{lead_id}` | Delete Lead |
| GET | `/api/v1/leads/{lead_id}/interactions` | List Interactions |
| POST | `/api/v1/leads/{lead_id}/interactions` | Add Interaction |
| GET | `/api/v1/leads/{lead_id}/requirements` | Requirement History |
| POST | `/api/v1/leads/{lead_id}/requirements` | Add Requirement |
| POST | `/api/v1/leads/{lead_id}/score` | Score Lead |
| GET | `/api/v1/leads/{lead_id}/predictions` | Prediction History |
| GET | `/api/v1/leads/{lead_id}/recommendations` | Recommend For Lead |
| GET | `/api/v1/leads/{lead_id}/follow-ups` | Lead Follow Ups |
| POST | `/api/v1/leads/{lead_id}/follow-ups` | Create Follow Up |
| POST | `/api/v1/leads/{lead_id}/follow-ups/suggest` | Suggest Follow Up |

## follow-ups

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/follow-ups` | List Follow Ups |
| PATCH | `/api/v1/follow-ups/{follow_up_id}` | Edit Follow Up |
| POST | `/api/v1/follow-ups/{follow_up_id}/approve` | Approve Follow Up |
| POST | `/api/v1/follow-ups/{follow_up_id}/reject` | Reject Follow Up |
| POST | `/api/v1/follow-ups/{follow_up_id}/complete` | Complete Follow Up |

## properties

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/properties` | List Properties |
| POST | `/api/v1/properties` | Create Property |
| GET | `/api/v1/properties/search` | Search Properties |
| GET | `/api/v1/properties/{property_id}` | Get Property |
| PATCH | `/api/v1/properties/{property_id}` | Update Property |
| DELETE | `/api/v1/properties/{property_id}` | Delete Property |

## campaigns

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/campaigns` | List Campaigns |
| POST | `/api/v1/campaigns` | Create Campaign |
| PATCH | `/api/v1/campaigns/{campaign_id}` | Update Campaign |

## analytics

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/analytics/overview` | Overview |
| GET | `/api/v1/analytics/monthly` | Monthly |
| GET | `/api/v1/analytics/channels` | Channels |
| GET | `/api/v1/analytics/forecast` | Forecast |
| GET | `/api/v1/analytics/insights` | Insights |

## ai

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/model` | Model Info |
| POST | `/api/v1/nlp/analyze` | Analyze Text |
| POST | `/api/v1/chatbot/message` | Chatbot Message |
| POST | `/api/v1/agents/leads/{lead_id}/run` | Run Lead Agents |
| POST | `/api/v1/agents/sales-intelligence/run` | Run Sales Intelligence Agent |
| GET | `/api/v1/agents/logs` | Agent Logs |

## health

| Method | Path | Summary |
|---|---|---|
| GET | `/health` | Health |

## Example

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -d 'username=manager@example.com&password=YOUR_SEED_PASSWORD' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8000/api/v1/leads?band=hot&sort_by=latest_probability'
curl -s -X POST localhost:8000/api/v1/agents/leads/1/run -H "Authorization: Bearer $TOKEN"
```

Errors use `{"detail": ...}`; validation errors list the offending fields. Every response carries an `X-Request-ID` header.
