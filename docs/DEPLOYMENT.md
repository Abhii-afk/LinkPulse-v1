# LinkPulse Deployment Guide

Covers the local Docker Compose environment, the configuration every
deployment needs, the selected cloud providers, and the checks to run before
and after a release.

Nothing in this document is a live URL. Every address below is a local one.

## 1. Selected deployment providers

BLUEPRINT section 15 settles on three providers. This project uses them in
this shape:

| Component | Provider | Configuration in this repository |
| --- | --- | --- |
| Frontend (React SPA) | Vercel | `frontend/vercel.json`, Vercel Root Directory `frontend` |
| API (FastAPI) | Railway | `railway.json` at the repository root, `Dockerfile` at the root |
| Analytics worker | Railway (second service) | same `Dockerfile`, different start command |
| Cache and queue (Redis) | Railway Redis plugin | environment variables only |
| Database (PostgreSQL) | Railway Postgres plugin | environment variables only |

Render and Supabase work as well and are noted in section 6. They need the
same environment variables, nothing else changes.

```
[GitHub Repo]
     |
     +---> [Vercel]  ---> frontend/dist, static assets, SPA fallback
     |
     +---> [Railway service: api]     ---> uvicorn app.main:app
     |    [Railway service: worker]  ---> python -m workers.analytics_worker
     |    [Railway plugin: Redis]     ---> cache + click event stream
     |    [Railway plugin: Postgres]  ---> durable state
```

### What the first deployment taught us

Four things have to be right, and each of them failed before it was fixed.
They are listed here because they are not obvious from the provider
documentation.

1. **The build context is the repository root.** Railway has no option to
   change it, so a Dockerfile that copies `alembic.ini` from the context
   root only works when the Dockerfile lives in the repository root. The
   image is therefore built from the root, and `docker compose` uses the
   same context, so one file produces one image everywhere.
2. **The image command has to be in shell form.** The exec form does not
   expand variables, so a platform that assigns the port through `$PORT`
   hands the literal string to uvicorn and the service refuses to start
   with `Invalid value for '--port'`. The command is
   `sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'`.
3. **The migrations have to run inside the platform.** The database and the
   cache are reachable over the private network only, so
   `preDeployCommand: alembic upgrade head` runs the migration from the
   service container itself. Running it from a laptop needs a tunnel.
4. **The worker serves no HTTP.** It has no health check path, and its
   start command is `python -m workers.analytics_worker`. The api service
   reports the worker through the Redis heartbeat instead.

## 2. Local environment with Docker Compose

The compose file brings up the whole stack: PostgreSQL, Redis, a one-shot
migration, the API, the analytics worker and the frontend.

```bash
cp .env.example .env      # then fill in POSTGRES_PASSWORD and JWT_SECRET
docker compose up -d db redis
docker compose up -d --build      # builds api, worker and frontend
docker compose ps
```

| Service | Address | Notes |
| --- | --- | --- |
| API | http://127.0.0.1:8000 | Swagger UI at `/docs` |
| Frontend | http://127.0.0.1:5173 | serves the built bundle |
| PostgreSQL | 127.0.0.1:5432 | password from `.env` |
| Redis | 127.0.0.1:6379 | append-only file enabled |

`migrate` runs `alembic upgrade head` once and exits. `api` and `worker`
only start after it reports success, so a failed migration never leaves a
half-configured database behind.

Useful commands:

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose ps
docker compose down          # stop, keep the data
docker compose down -v       # stop and delete the volumes
```

Running the backend on the host instead of in a container:

```bash
docker compose up -d db redis
cd backend && alembic upgrade head
cd backend && uvicorn app.main:app --reload
cd backend && python -m workers.analytics_worker
```

## 3. Environment variables

`.env.example` is the full list with the fallback values. The variables that
have no safe default are:

| Variable | Why it is required |
| --- | --- |
| `POSTGRES_PASSWORD` | `docker compose` refuses to start the database without it |
| `JWT_SECRET` | At least 24 characters. The service validates its configuration on startup and refuses to boot without it |
| `VITE_API_BASE_URL` | Baked into the frontend bundle at build time, so the browser has to be told where the API lives |

Variables that usually change per environment:

| Variable | Local | Production |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://linkpulse:...@127.0.0.1:5432/linkpulse` | Neon connection string |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Railway Redis URL |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | `https://...` so cookies get the Secure flag |
| `APP_ENV` | `development` | `production` |
| `JWT_SECRET` | local value | 32 bytes or more from a secret manager |
| `LINK_SESSION_SECRET` | empty, falls back to `JWT_SECRET` | a separate key so it can be rotated on its own |
| `CORS_ALLOWED_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | the public frontend origin, for example `https://linkpulse.vercel.app` |

`CORS_ALLOWED_ORIGINS` matters more than it looks: the front end is served
from a different origin than the API, so the browser sends a preflight
request before every call. If the front end's origin is not listed, the
request is blocked before it leaves the browser and the UI reports that the
backend is unreachable even though it is running.

## 4. Health checks

| Endpoint | Purpose | Behaviour |
| --- | --- | --- |
| `GET /health/live` | Liveness | Always 200 while the process runs. It never touches PostgreSQL or Redis, so a dependency blip cannot make an orchestrator restart a healthy API. |
| `GET /health` | Readiness | 200 when PostgreSQL and Redis answer, 503 otherwise. It also reports the analytics worker. |

The readiness payload looks like this:

```json
{
  "status": "ok",
  "service": "linkpulse-api",
  "environment": "development",
  "checks": { "database": "ok", "redis": "ok", "worker": "ok" }
}
```

The worker publishes a short-lived Redis heartbeat under
`linkpulse:worker:heartbeat:<consumer name>` on every loop. `worker` is
`ok` while a heartbeat is fresh, `stale` when a worker stopped reporting and
`absent` when no worker has ever run. A missing worker does **not** make the
API unready: clicks keep buffering in the Redis stream while the worker is
away, which is the behaviour described in BLUEPRINT section 19.

## 5. Verifying a deployment

```bash
# 1. Connectivity of both backing services
cd backend && python -m scripts.check_services

# 2. The API answers its probes
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health

# 3. The analytics worker is alive
cd backend && python -m scripts.check_worker

# 4. End to end smoke test against a running instance
cd backend && LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 pytest tests/test_smoke_live.py -q
```

The smoke test covers registration, login, link creation, the redirect
itself, the analytics endpoints, CSV import and the admin kill switch. Add
`LINKPULSE_SMOKE_ADMIN_EMAIL` and `LINKPULSE_SMOKE_ADMIN_PASSWORD` to also
exercise the kill switch, otherwise that one test is skipped.

The seed and the rehearsal are described in `docs/DEMO_CHECKLIST.md`:

```bash
cd backend && python -m scripts.seed_demo_data --reset
cd backend && python -m scripts.demo_rehearsal
```

## 6. Publishing to the selected providers

These steps need an account and credentials. They have not been run from
this repository, so no hosted URL is claimed here.

### Frontend on Vercel

1. Import the repository into Vercel.
2. Set **Root Directory** to `frontend`. The Vercel configuration lives in
   `frontend/vercel.json`, so Vercel picks it up from there. It sets the
   build command, the output directory and the single page application
   fallback.
3. Set `VITE_API_BASE_URL` to the public API origin, for example
   `https://linkpulse-api.up.railway.app`. The value is baked into the
   bundle at build time, so the project has to be redeployed after it
   changes.
4. Deploy.

### API and worker on Railway

`railway.json` only carries the build configuration, because both services
are built from the same `Dockerfile` and need different start commands.

1. Create a Railway project from the repository.
2. Add the **Postgres** plugin and the **Redis** plugin.
3. Create the **api** service. Railway builds the `Dockerfile` at the
   repository root. Set the variables `DATABASE_URL`, `REDIS_URL`,
   `JWT_SECRET`, `LINK_SESSION_SECRET`, `PUBLIC_BASE_URL`, `APP_ENV=production`
   and `CORS_ALLOWED_ORIGINS`.
   Then set, in the service settings:
   * start command `sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'`
   * health check path `/health`, health check timeout `45`
   * pre-deploy command `alembic upgrade head`
4. Create the **worker** service from the same repository and the same
   Dockerfile. Set `DATABASE_URL`, `REDIS_URL` and `JWT_SECRET`. Set the
   **start command** to `python -m workers.analytics_worker` and leave the
   health check path empty, because the worker serves no HTTP.
5. Point the frontend's `VITE_API_BASE_URL` at the api service and deploy
   the frontend.

#### The database URL can be pasted as it is

Neon, Supabase and Render hand out libpq style URLs that end in
`?sslmode=require`. The asyncpg driver does not know that option and would
refuse the connection with
`connect() got an unexpected keyword argument 'sslmode'`. The application
translates the option to `ssl` before it connects, so the connection string
can be pasted exactly as the provider shows it.

#### The Railway plugin URLs are private

The plugin hands out `postgresql://postgres:...@postgres.railway.internal:5432/railway`
and `redis://:...@redis.railway.internal:6379`. Those names only resolve
inside the Railway network, which is why the migration runs as a pre-deploy
command instead of from a laptop. Change the scheme to
`postgresql+asyncpg://` because this application uses asyncpg.

### Alternatives

* **Render**: create a Web Service with the same `backend/Dockerfile`, a
  Background Worker with the command `python -m workers.analytics_worker`,
  and a private PostgreSQL instance.
* **Supabase**: use the pooled connection string as `DATABASE_URL`. It must
  stay an asyncpg URL, so keep the `postgresql+asyncpg://` scheme.

## 7. Release checklist

```bash
cd backend && pytest -q
cd frontend && npm test
cd backend && alembic upgrade head
cd backend && python -m scripts.check_services
docker compose up -d --build && docker compose ps
cd backend && LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 pytest tests/test_smoke_live.py -q
```

## 8. Remaining steps that need credentials or manual action

These cannot be completed from the repository alone:

1. Create the Vercel, Railway and database accounts and connect the
   repository.
2. Provide the production `JWT_SECRET` and `LINK_SESSION_SECRET` through a
   secret manager.
3. Run `alembic upgrade head` against the production database.
4. Set `VITE_API_BASE_URL` to the public API origin and rebuild the frontend.
5. Verify the public URL with the smoke test in section 5.
6. Decide on a real `GEOLITE2_CITY_DB_PATH`; without it the worker falls
   back to deterministic mock coordinates, which is fine for a demo.

### Deploying the demo data

The seed script needs a database connection, so on a platform with a
private network it has to run inside the platform. Repurposing the worker
service for one deployment works:

```bash
railway variables --service worker --set "JWT_SECRET=..."
railway service redeploy -s worker --from-source --yes
```

with the worker's start command set to
`python -m scripts.seed_demo_data --admin-password <password>` for that
one deployment, then set it back to `python -m workers.analytics_worker`
and redeploy. The seed is idempotent, so running it twice changes nothing.
