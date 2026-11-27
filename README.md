# EstateIQ — AI-Powered Real Estate Lead Management & Sales Intelligence

A full-stack platform that helps a real-estate sales team decide **who to call first and what to say**:
a lead dashboard, ML lead scoring with explanations, NLP requirement extraction, human-approved AI
follow-ups, a grounded property chatbot, predictive analytics and LangGraph agents.

> **Demo data is synthetic.** Every lead, property, interaction, metric and model score you see after
> seeding is generated, clearly flagged (`is_synthetic`, a UI banner and badges), and uses
> `example.com` emails and fake phone numbers. Model metrics describe generated data, not real performance.

**Stack:** FastAPI · SQLAlchemy 2 · PostgreSQL · scikit-learn / XGBoost · LangGraph · React 18 · Tailwind · Recharts · Docker

## Features

| Area | What it does |
|---|---|
| Lead dashboard | KPIs, monthly trend, Hot/Warm/Cold mix, top leads, filterable/sortable lead table, lead timeline |
| Lead scoring | Calibrated conversion probability, Hot/Warm/Cold band, per-lead "why" factors, stored history |
| NLP | Extracts budget (lakh/crore, ranges), location, type, BHK, timeline, urgency, intent from free text |
| Follow-ups | Prioritised drafts from templates (optionally LLM-personalised). **A person approves everything; nothing is sent automatically** |
| Chatbot | Stateless RAG over available listings; saves a lead only with explicit consent |
| Analytics | Channel performance and cost, forecast of expected conversions, rule-based insights |
| Agents | LangGraph pipeline: qualify → score → recommend → draft follow-up, fully logged |
| Platform | JWT auth, roles (admin/manager/agent), rate limiting, audit logs, request IDs |

## Quick start (Docker)

```bash
cp .env.example .env        # then set SECRET_KEY, POSTGRES_PASSWORD, SEED_PASSWORD
docker compose up --build
```

UI: <http://localhost:8080> · API docs: <http://localhost:8000/docs>
Sign in as `manager@example.com`, `agent1@example.com` or `admin@example.com` with your `SEED_PASSWORD`.
With `AUTO_SEED=true` the database is filled with synthetic demo data on first start.

## Local development

Requires Python 3.12+, Node 20+. PostgreSQL is optional (SQLite is the local default).

```bash
python -m venv .venv && source .venv/bin/activate
make install            # backend + frontend dependencies
make train              # train the scoring model on synthetic data (~1 min)
make seed               # create tables + synthetic demo data
make run-api            # http://localhost:8000
make run-web            # http://localhost:5173 (proxies /api to :8000)
```

Backend settings are read from `backend/.env` (see `.env.example`). With no `SEED_PASSWORD` set in
development, demo users get the documented dev password `ChangeMe123!`; production refuses to seed
without one.

Useful commands: `make test`, `make lint`, `make format`, `make seed-reset`, `make data`.

## Project layout

```
backend/
  app/
    api/         routers (HTTP only), dependencies (auth, RBAC, DB session)
    services/    business logic: scoring, nlp, rag, follow-ups, chatbot, analytics
    agents/      LangGraph graphs + runtime wrapper (timing, logging, failure handling)
    models/      SQLAlchemy models (9 tables)     schemas/  pydantic request/response models
    core/        settings, security, rate limiting, errors, logging
  ml/            synthetic data, features, training, explanations
  scripts/       train_model, seed, generate_data, run_eda
  tests/         pytest (SQLite by default, PostgreSQL via TEST_DATABASE_URL)
frontend/        React app (Vite), nginx config for Docker
docs/            architecture, API, schema.sql, model card, EDA, openapi.json
data/            sample synthetic dataset + data card
```

More detail: [architecture and agent workflow](docs/architecture.md) · [API reference](docs/api.md) ·
[DB schema](docs/schema.sql) · [model card](docs/model_card.md) · [EDA](docs/eda_report.md) · [data card](data/README.md)

## What is ML, NLP, LLM, and an agent here?

| Piece | Kind | Notes |
|---|---|---|
| Lead scoring | Traditional ML | RF vs XGBoost chosen by cross-validation, isotonic calibration, held-out test set |
| Requirement extraction | Rules/NLP | Deterministic regex + gazetteer; LLM (if enabled) fills only missing fields and is validated |
| Property matching | Filters + weighted scoring | Budget/location are hard constraints |
| Chatbot | RAG | TF-IDF retrieval by default; `sentence-transformers` optional. If the LLM cites a listing it wasn't given, its answer is discarded for the rules reply |
| Follow-up text | Templates (+ optional LLM) | Numbers and links in LLM text must exist in the lead facts |
| Orchestration | LangGraph agents | Deterministic graph, **no free-form tool-calling loop** |

The LLM is **off by default** (`LLM_PROVIDER=none`) and every feature works without it. To enable it set
`LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

## Testing and quality

```bash
make test        # ~150 backend tests + frontend unit tests
make lint        # ruff check + format check
```

CI (`.github/workflows/ci.yml`) runs ruff, the backend suite on SQLite **and** PostgreSQL 16, and the
frontend tests and build. Agents' write boundary, role-based access, rate limits and the chatbot's
consent rule each have dedicated tests.

## Deployment notes

- Set a strong `SECRET_KEY` (≥ 32 chars; `ENVIRONMENT=production` refuses to start otherwise), a real
  `POSTGRES_PASSWORD`, and `SEED_PASSWORD` only if you want demo users.
- Run behind HTTPS. Set `TRUST_PROXY_HEADERS=true` only behind a proxy you control, otherwise rate limits
  key on the proxy's address.
- The compose file is a demo stack. For cloud, build the two images and run them on your platform of
  choice (Cloud Run, ECS, Fly, Render, Kubernetes) against a managed PostgreSQL; the frontend image's
  nginx proxies `/api` to a host named `backend` — change `frontend/nginx.conf` if yours differs.
- Set `AUTO_SEED=false` for anything but a demo.

## Limitations (please read)

- **Synthetic data only.** The model is trained on generated data; its metrics prove the pipeline, not
  business value. Retrain on real history and re-validate (`docs/model_card.md`).
- **Rate limiting is in-memory** and per process. With several replicas, use a shared store (e.g. Redis).
- **Schema is created with `create_all`**, not migrations. Add Alembic before changing a live database.
- **Model files are pickles (joblib).** Only load artifacts you trained; never from an untrusted source.
- **No outbound sending.** The app produces approved drafts; a person sends them from WhatsApp, email,
  etc. Integrating a messaging provider is deliberately out of scope.
- The Docker images and the LLM path were not exercised in the environment this was built in (no Docker
  daemon, no API key); the rest is covered by tests.
- Authentication has no refresh tokens, password reset or MFA, and the token lives in `localStorage`.

## License

MIT — see [LICENSE](LICENSE).
