<div align="center">

# LinkPulse

**A link shortener with rules, asynchronous analytics, and admin controls.**

[Live frontend](https://frontend-gamma-six-95.vercel.app) · [Live API](https://api-production-1648a.up.railway.app) · [API docs](https://api-production-1648a.up.railway.app/docs) · [Deployment guide](docs/DEPLOYMENT.md)

</div>

---

## The problem

Basic URL shorteners are key-value redirectors. That is fine for one person
and useless for a team, and it creates four operational bottlenecks:

1. **Blind traffic drops.** Growth teams lose the context of a conversion
   channel because a plain shortener cannot attribute a click to a campaign.
2. **No access governance.** A link cannot be capped by click volume, gated
   behind a password, or scheduled to retire when a promotion ends.
3. **Write-path latency spikes.** Platforms that write the visit log
   synchronously into their transactional database get slow redirects
   exactly when traffic peaks.
4. **No safety controls.** Unregulated shorteners are routinely weaponised
   for phishing and malware distribution, with no way to revoke a malicious
   link in real time.

The people who feel this are the marketing lead running a campaign across
email, social and print; the operations team answering for a partner link;
and the security engineer who has to kill a phishing link before someone
clicks it.

## The solution

LinkPulse turns a long URL into a short, governed key and then treats every
click as an event worth understanding.

```
visitor  ──►  GET /summer-deal
                    │
                    ▼
             Redis routing cache          ← resolves the link, runs the rule
                    │                       waterfall, never touches SQL
                    ├──► 302 to the destination (milliseconds)
                    └──► XADD one click event onto a Redis stream
                                              │
                                              ▼
                                    analytics worker
                                     (batches of 100)
                                              │
                                              ▼
                                        PostgreSQL
```

The redirect path never writes to the database and never reads from it. It
resolves the link from Redis, runs the rule waterfall, pushes one event onto
a stream and answers `302`. A separate worker batches those events into
PostgreSQL. Traffic spikes therefore cost the redirect path nothing, and a
single malformed event can never lose the rest of a batch.

On top of that, every link is governed: a click cap, an expiry date, an
optional password, a domain blocklist, and an admin kill-switch that stops
redirects immediately — while the historical analytics stay intact.

## Features

**For everyone**

- Fast redirects resolved from a Redis cache, with a fixed rule waterfall:
  active → not abusive → not expired → under the click cap → password challenge.
- Click analytics: totals, unique visitors, bot filtering, traffic over
  time, and device, browser and traffic-source breakdowns.
- A dashboard that keeps showing history for links that were disabled or
  have expired. Nothing is ever hard deleted.

**For signed-in users**

- A workspace with navigation between **Links**, **Campaigns**, **Import**,
  **Analytics** and **Settings**, so links, campaigns, QR codes and analytics
  live in one place.
- A two-step creation wizard: destination and alias, then the rules
  (expiry, click cap, password), with a review of the warnings before
  publishing, and a campaign to group the link under.
- A list of the links you own, with their status, their campaign and how
  close they are to their click cap, including a warning at eighty percent.
- Downloadable QR codes for every link you own, shown in the browser and
  saved as a PNG.
- CSV bulk import with per-row error reporting: a bad row is reported with
  its line number and reason, and the rest of the file still imports.
- Campaigns, so the links of one launch or one newsletter can be read
  together.
- A password challenge on protected links, carried by a short-lived,
  HMAC-signed cookie that is bound to one link.

**For administrators**

- A kill-switch that disables a link and invalidates its routing cache in
  the same request, so redirects stop on the next click.
- A domain blocklist that rejects new links pointing at prohibited hosts.
- A platform-wide link list and a platform-wide analytics overview.
- A reason recorded on every deactivation.

**Guardrails on every request**

- JWT authentication with role checks enforced on the server: `visitor`,
  `user`, `admin`.
- Owner scoping on every read, so one user can never see another's links.
- Redis sliding-window rate limiting on link creation and on password
  attempts.
- A destination URL that is checked against the blocklist before a link is
  ever created.
- Passwords hashed with bcrypt; hashes are never logged or returned.

## Tech stack

| Layer | Choice |
| --- | --- |
| API | FastAPI, Python 3.11+, async Uvicorn |
| Data access | SQLAlchemy 2 (async), asyncpg, Alembic |
| Database | PostgreSQL 16 |
| Cache and queue | Redis 7 — key-value routing cache plus Redis Streams |
| Background worker | A separate Python process consuming the stream |
| Auth | PyJWT (HS256), bcrypt |
| Frontend | React 18, Vite 5, hand-written CSS and SVG charts |
| Tests | pytest, pytest-asyncio, httpx, Vitest |
| Packaging | Docker (`python:3.12-slim`, `node:20-alpine`) |
| Hosting | Vercel (frontend), Railway (API, worker, Postgres, Redis) |

> The blueprint asked for Tailwind, Recharts and Lucide. The shipped
> front end uses hand-written CSS and hand-rolled SVG charts instead, which
> keeps the browser bundle free of UI dependencies. No feature is missing.

## Live links

| | |
| --- | --- |
| Frontend | <https://frontend-gamma-six-95.vercel.app> |
| API | <https://api-production-1648a.up.railway.app> |
| API health | <https://api-production-1648a.up.railway.app/health> |
| API docs (Swagger UI) | <https://api-production-1648a.up.railway.app/docs> |

The deployment is running the same commit as this repository, with the
database migrated, the worker running and a seeded demo workspace.

### Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Demo user | `demo@linkpulse.local` | `demo-password-123` |
| Admin | `admin@linkpulse.local` | `admin-password-123` |
| Password on `demo-protected` | — | `link-password-123` |

These are throwaway credentials for the public demo. Rotate them before
using the deployment for anything real.

## Screenshots

<img width="1917" height="896" alt="Screenshot 2026-10-20 132225" src="https://github.com/user-attachments/assets/5cf83b09-18d8-4c34-a528-887a2fbcfb04" />
<img width="1917" height="971" alt="Screenshot 2026-10-20 132213" src="https://github.com/user-attachments/assets/6225f3f8-551d-41c1-9f75-3b33a17de1f4" />




_Placeholder: link creation wizard, analytics dashboard, admin kill-switch,
CSV import error report._

## Setup

### Prerequisites

- Docker Desktop (for the container path)
- Python 3.11+ and Node.js 20+ (for the host path)

### 1. Configure the environment

```bash
cd LinkPulse-v1
cp .env.example .env          # Windows: copy .env.example .env
```

Fill in the two values that have no default:

```ini
POSTGRES_PASSWORD=<a local database password>
JWT_SECRET=<at least 24 characters>
```

Generate a real secret instead of typing one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Everything else in `.env.example` already has a working default.

### 2. Run the whole stack in Docker

```bash
docker compose up -d --build
docker compose ps
```

Compose starts PostgreSQL, Redis, a one-shot migration, the API, the
analytics worker and the front end. The API and the worker only start once
the migration has succeeded.

| Service | Address |
| --- | --- |
| API | <http://127.0.0.1:8000> (Swagger UI at `/docs`) |
| Frontend | <http://127.0.0.1:5173> |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

### 3. Or run the app on your host

```bash
# infrastructure
docker compose up -d db redis

# API
cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload

# analytics worker, in a second terminal
cd backend
python -m workers.analytics_worker

# front end, in a third terminal
cd frontend
npm install
npm run dev
```

> Use the `alembic` console script, not `python -m alembic`: the
> `backend/alembic/` folder shadows the installed package. And open the
> Vite dev server at `http://localhost:5173` rather than `127.0.0.1`, because
> it binds to IPv6.

### 4. Seed the demo data

```bash
cd backend
python -m scripts.seed_demo_data --reset
```

This creates the two accounts above, four campaigns, six links covering
every status the dashboard can show, and two weeks of click history. It is
idempotent, and `--reset` only removes the rows it created.

### 5. Verify it

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health

cd backend && python -m scripts.check_services
cd backend && python -m scripts.check_worker
cd backend && pytest -q
cd frontend && npm test
```

End-to-end smoke test against a running instance:

```bash
cd backend
LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 pytest tests/test_smoke_live.py -q
```

It registers, logs in, creates a link, solves the password challenge,
follows the redirect, reads the analytics, imports a CSV and fires the
admin kill switch. It is skipped unless `LINKPULSE_SMOKE_BASE_URL` is set.

### 6. Rehearse the demo

```bash
cd backend
python -m scripts.demo_rehearsal
```

Drives both demo scenarios against a running instance and prints how long
each step took. The minute-by-minute script is in
[`docs/DEMO_CHECKLIST.md`](docs/DEMO_CHECKLIST.md).

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/{short_code}` | The redirect. Resolves from Redis and never touches SQL |
| `GET` | `/health` | Readiness: database, Redis and worker status |
| `GET` | `/health/live` | Liveness, without touching a dependency |
| `POST` | `/api/v1/auth/register` | Create an account |
| `POST` | `/api/v1/auth/login` | Exchange credentials for a JWT |
| `GET` | `/api/v1/user/me` | The current account |
| `GET` | `/api/v1/links` | The links you own |
| `POST` | `/api/v1/links` | Create a link |
| `POST` | `/api/v1/links/bulk` | Import links from a CSV |
| `POST` | `/api/v1/links/verify-password` | Solve a link password |
| `GET` | `/api/v1/links/{short_code}/qr` | QR code for a link you own |
| `GET` | `/api/v1/campaigns` | The campaigns you own |
| `POST` | `/api/v1/campaigns` | Create a campaign |
| `GET` | `/api/v1/analytics/overview` | Your analytics |
| `GET` | `/api/v1/links/{link_id}/analytics` | Analytics for one link |
| `GET` | `/api/v1/admin/links` | Every link on the platform |
| `PATCH` | `/api/v1/admin/links/{link_id}/status` | The kill-switch |
| `GET` | `/api/v1/admin/domains` | The domain blocklist |
| `POST` | `/api/v1/admin/domains` | Block a domain |
| `GET` | `/api/v1/admin/analytics/overview` | Platform-wide analytics |

## Repository layout

```
backend/app/{core,models,routers,schemas,services}   FastAPI application
backend/workers/                                     analytics worker
backend/tests/                                       pytest suite
backend/scripts/                                     seed, rehearsal and checks
frontend/src/{api,components,pages}                  React front end
demo/links.csv                                       the CSV used in the demo
docs/                                                blueprint, deployment, demo checklist
docker-compose.yml                                   the whole local stack
```

## Further reading

- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — the provider configuration,
  the environment variables, the health checks and what a release needs.
- [`docs/DEMO_CHECKLIST.md`](docs/DEMO_CHECKLIST.md) — the five-minute demo.
- [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) — the full product and
  architecture specification.
- [`AGENTS.md`](AGENTS.md) — the working agreement for this repository.
