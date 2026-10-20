# LinkPulse

A link shortener with rules, asynchronous analytics, and admin controls.

* FastAPI backend with async SQLAlchemy, Alembic and JWT RBAC
* PostgreSQL for durable state, Redis for the routing cache and the click
  event stream
* A separate analytics worker that batches click events into PostgreSQL
* A React (Vite) front end for link creation and the analytics dashboard

## Quick start with Docker Compose

```bash
cp .env.example .env      # fill in POSTGRES_PASSWORD and JWT_SECRET
docker compose up -d --build
docker compose ps
```

| Service | Address |
| --- | --- |
| API | http://127.0.0.1:8000 (Swagger UI at `/docs`) |
| Frontend | http://127.0.0.1:5173 |
| PostgreSQL | 127.0.0.1:5432 |
| Redis | 127.0.0.1:6379 |

## Quick start on the host

```bash
cp .env.example .env
docker compose up -d db redis
cd backend && alembic upgrade head
cd backend && uvicorn app.main:app --reload
cd backend && python -m workers.analytics_worker
cd frontend && npm install && npm run dev
```

## Checks

```bash
cd backend && pytest -q
cd frontend && npm test
cd backend && python -m scripts.check_services
cd backend && LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 pytest tests/test_smoke_live.py -q
```

## Demo data and rehearsal

```bash
cd backend && python -m scripts.seed_demo_data
cd backend && python -m scripts.demo_rehearsal
```

## Documentation

* `docs/DEPLOYMENT.md` - local environment, environment variables, health
  checks, the selected cloud providers and the release checklist
* `docs/DEMO_CHECKLIST.md` - the five minute demo checklist
* `docs/BLUEPRINT.md` - the full product and architecture specification
* `AGENTS.md` - the working agreement for this repository
