# AGENTS.md: LinkPulse

LinkPulse is a link shortener with rules, async analytics, and admin controls.
The full spec is in `docs/BLUEPRINT.md`. Read only the sections a task points to,
by section number. Do not re-read the whole file every session.

## Stack (fixed, do not swap)
- Backend: FastAPI (Python 3.11+), async SQLAlchemy, Alembic, Pydantic
- DB: PostgreSQL. Cache + queue: Redis (key-value + Redis Streams)
- Worker: separate Python process consuming the Redis stream
- Frontend: React (Vite) + Tailwind + Recharts/Tremor + Lucide
- Tests: pytest + pytest-asyncio + httpx (backend), Vitest (frontend)

## Layout
backend/app/{core,models,schemas,routers,services}, backend/workers/,
backend/tests/, frontend/src/{components,pages,api}, docker-compose.yml

## Non-negotiable rules
1. The redirect route (`GET /{short_code}`) never touches PostgreSQL on the
   hot path. Resolve from Redis, run the rule waterfall, XADD an event, return 302.
2. Rule waterfall order is fixed: active -> not abusive -> not expired ->
   under click limit -> password challenge (if set).
3. Never write click logs inside the redirect request. Only the worker writes them.
4. Soft-delete only (`is_active`, `deactivated_at`). Never hard-delete links
   or click events. Disabled/expired links keep their analytics.
5. Admin kill-switch must delete/invalidate the Redis cache key immediately.
6. Link passwords are bcrypt-hashed. Never log or return hashes.
7. RBAC: visitor / user / admin enforced by JWT dependencies, never in the frontend alone.
8. No external geolocation or bot APIs. Use a local GeoLite2 file with a mock fallback.
9. No new dependencies or cloud services without asking first.
10. Link creation and link-password attempts are rate limited per client IP
    with a Redis sliding window (30 creations per minute by default).
11. A solved link password is carried by a short-lived HMAC-signed cookie that
    is bound to one short code. A cookie that is not signed by this server
    never unlocks a link.
12. The service validates its configuration on startup. A missing or too
    short `JWT_SECRET` stops the boot instead of failing at the first login.

## How to work
- Work in small vertical slices. One slice per task. Do not start the next one.
- Before coding, state the plan in a few lines and list the files you will touch.
- Write tests alongside code. Run them. Paste the real output.
- Never claim something works unless you ran it. Never invent test results,
  latency numbers, or deployment URLs. If you could not verify, say so.
- If the spec is ambiguous or two parts conflict, stop and ask. Do not guess.
- Keep diffs reviewable. Prefer editing existing files over rewriting them.
- Commit at the end of each green slice with a clear message.

## Commands (keep this section updated as the project grows)
- Start infra: `docker compose up -d db redis`
- Start everything: `docker compose up -d --build`
- Connectivity checks: `cd backend && python -m scripts.check_services`
- Migrate: `cd backend && alembic upgrade head`
- Bootstrap admin: `cd backend && python -m scripts.bootstrap_admin --email admin@example.com`
- API: `cd backend && uvicorn app.main:app --reload`
- Worker: `cd backend && python -m workers.analytics_worker`
- Backend tests: `cd backend && pytest -q`
- Frontend: `cd frontend && npm run dev`
- Health probes: `curl http://127.0.0.1:8000/health/live` and `/health`
- Seed demo data: `cd backend && python -m scripts.seed_demo_data`
- Demo rehearsal: `cd backend && python -m scripts.demo_rehearsal`
- Live smoke test: `cd backend && LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 pytest tests/test_smoke_live.py -q`

## Definition of done for any slice
- Tests for the new behavior pass, including at least one failure case
- Existing tests still pass
- `.env.example` updated if new config was added
- AGENTS.md "Commands" updated if anything changed
- Short summary: what was built, what was verified (with output), what is still missing
